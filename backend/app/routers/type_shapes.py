"""TypeShape discovery API endpoints (TICKET-965).

Exposes structural type matching queries: find functions that can consume a
variable, find functions that produce what another function needs, and search
shapes by structural attributes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.graph.client import get_graph
from app.graph import logic_queries as lq

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/type-shapes", tags=["type-shapes"])


@router.get("/{variable_id}/consumers")
async def get_consumers_for_variable(variable_id: str) -> list[dict[str, Any]]:
    """Find functions that can consume a given variable based on its TypeShape.

    Args:
        variable_id: UUID of the variable node.

    Returns:
        List of LogicNode dicts that accept a compatible shape.
    """
    graph = get_graph()
    try:
        result = graph.query(
            lq.FIND_CONSUMERS_FOR_VARIABLE,
            params={"variable_id": variable_id},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    nodes = []
    for row in result.result_set:
        node = row[0]
        props = node.properties if hasattr(node, "properties") else node
        nodes.append({
            "id": props.get("id", ""),
            "name": props.get("name", ""),
            "kind": props.get("kind", ""),
            "module_path": props.get("module_path", ""),
            "signature": props.get("signature", ""),
        })
    return nodes


@router.get("/{variable_id}/consumer-subgraph")
async def get_consumer_subgraph(variable_id: str) -> dict[str, Any]:
    """Return the full TypeShape subgraph for a variable's consumers.

    Returns TypeShape hub nodes, consumer LogicNodes, and the edges between them
    so the frontend can render the structural matching path on the canvas.

    When the variable's TypeShape is a hint type (e.g. ``pd.DataFrame``) and
    the graph traversal finds no consumers via COMPATIBLE_WITH edges, a
    fallback search finds functions that ACCEPT any structural TypeShape —
    bridging the typed/duck-typed boundary.

    Args:
        variable_id: UUID of the variable node.

    Returns:
        Dict with type_shapes, consumers, and edges lists.
    """
    graph = get_graph()
    try:
        result = graph.query(
            lq.FIND_CONSUMER_SUBGRAPH_FOR_VARIABLE,
            params={"variable_id": variable_id},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    type_shapes: dict[str, dict[str, Any]] = {}
    consumers: dict[str, dict[str, Any]] = {}
    # Track best confidence per consumer: exact > structural > weak
    consumer_confidence: dict[str, str] = {}
    edges: list[dict[str, str]] = []

    for row in result.result_set:
        ts_id = str(row[0]) if row[0] else ""
        ts_base = str(row[1]) if row[1] else ""
        ts_def = str(row[2]) if row[2] else ""
        shape_id = str(row[3]) if row[3] else ""
        shape_base = str(row[4]) if row[4] else ""
        shape_def = str(row[5]) if row[5] else ""
        row_consumers = row[6] if row[6] else []

        # Primary TypeShape
        if ts_id and ts_id not in type_shapes:
            type_shapes[ts_id] = {"id": ts_id, "base_type": ts_base, "definition": ts_def}
            edges.append({"source": variable_id, "target": ts_id, "type": "HAS_SHAPE"})

        # Compatible shape (may be same as primary)
        if shape_id and shape_id not in type_shapes:
            type_shapes[shape_id] = {"id": shape_id, "base_type": shape_base, "definition": shape_def}
            if shape_id != ts_id:
                edges.append({"source": ts_id, "target": shape_id, "type": "COMPATIBLE_WITH"})

        # Compute confidence for consumers of this shape
        if shape_id == ts_id:
            confidence = "exact"
        else:
            # Check if this is a generalization (generic hint → bare hint)
            confidence = "structural"
            try:
                primary_def = json.loads(ts_def) if ts_def else {}
                matched_def = json.loads(shape_def) if shape_def else {}
                if (
                    primary_def.get("kind") == "hint"
                    and matched_def.get("kind") == "hint"
                    and "[" in primary_def.get("type", "")
                    and "[" not in matched_def.get("type", "")
                ):
                    confidence = "weak"
                elif (
                    primary_def.get("kind") == "hint"
                    and matched_def.get("kind") == "structural"
                ):
                    confidence = "weak"
            except (json.JSONDecodeError, TypeError):
                pass

        # Consumer functions for this shape
        for c in row_consumers:
            cid = c.get("id", "") if isinstance(c, dict) else ""
            if not cid:
                continue
            if cid not in consumers:
                consumers[cid] = c
            # Keep highest confidence: exact > structural > weak
            _rank = {"exact": 3, "structural": 2, "weak": 1}
            prev = consumer_confidence.get(cid, "")
            if _rank.get(confidence, 0) > _rank.get(prev, 0):
                consumer_confidence[cid] = confidence
            edges.append({"source": cid, "target": shape_id, "type": "ACCEPTS"})

    # Attach confidence to each consumer
    consumer_list = []
    for c in consumers.values():
        cid = c.get("id", "")
        c_with_conf = {**c, "confidence": consumer_confidence.get(cid, "structural")}
        consumer_list.append(c_with_conf)

    return {
        "type_shapes": list(type_shapes.values()),
        "consumers": consumer_list,
        "edges": edges,
    }


@router.get("/{node_id}/producers")
async def get_producers_for_node(node_id: str) -> list[dict[str, Any]]:
    """Find functions that produce what a given function needs.

    Args:
        node_id: UUID of the LogicNode.

    Returns:
        List of LogicNode dicts that produce compatible shapes.
    """
    graph = get_graph()
    try:
        result = graph.query(
            lq.FIND_PRODUCERS_FOR_NODE,
            params={"node_id": node_id},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    nodes = []
    for row in result.result_set:
        node = row[0]
        props = node.properties if hasattr(node, "properties") else node
        nodes.append({
            "id": props.get("id", ""),
            "name": props.get("name", ""),
            "kind": props.get("kind", ""),
            "module_path": props.get("module_path", ""),
            "signature": props.get("signature", ""),
        })
    return nodes


@router.get("/search")
async def search_type_shapes(
    attrs: str | None = Query(default=None, description="Comma-separated attribute names"),
    subscripts: str | None = Query(default=None, description="Comma-separated subscript keys"),
    methods: str | None = Query(default=None, description="Comma-separated method names"),
    limit: int = Query(default=20, le=100),
) -> list[dict[str, Any]]:
    """Search TypeShape nodes by structural attributes.

    Args:
        attrs: Comma-separated attribute names to search for.
        subscripts: Comma-separated subscript keys to search for.
        methods: Comma-separated method names to search for.
        limit: Maximum results.

    Returns:
        List of matching TypeShape dicts.
    """
    # Build a search query string from the parameters
    search_terms = []
    if attrs:
        search_terms.extend(attrs.split(","))
    if subscripts:
        search_terms.extend(subscripts.split(","))
    if methods:
        search_terms.extend(methods.split(","))

    if not search_terms:
        raise HTTPException(status_code=400, detail="At least one of attrs, subscripts, or methods required")

    graph = get_graph()

    # Use the first term as the CONTAINS query, then filter in Python
    query_str = search_terms[0].strip()
    try:
        result = graph.query(
            lq.SEARCH_TYPE_SHAPES,
            params={"query": query_str, "limit": limit * 3},  # Over-fetch for post-filtering
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    shapes = []
    for row in result.result_set:
        node = row[0]
        props = node.properties if hasattr(node, "properties") else node

        definition_str = props.get("definition", "{}")
        try:
            definition = json.loads(definition_str) if isinstance(definition_str, str) else definition_str
        except (json.JSONDecodeError, TypeError):
            definition = {}

        # Post-filter: all search terms must appear in the definition
        def_attrs = set(definition.get("attrs", []))
        def_subscripts = set(definition.get("subscripts", []))
        def_methods = set(definition.get("methods", []))
        all_keys = def_attrs | def_subscripts | def_methods

        if all(term.strip() in all_keys for term in search_terms):
            shapes.append({
                "id": props.get("id", ""),
                "shape_hash": props.get("shape_hash", ""),
                "kind": props.get("kind", ""),
                "base_type": props.get("base_type", ""),
                "definition": definition,
                "created_at": props.get("created_at", ""),
            })

        if len(shapes) >= limit:
            break

    return shapes


@router.get("/detail/{shape_id}")
async def get_type_shape(shape_id: str) -> dict[str, Any]:
    """Get a TypeShape by its ID.

    Args:
        shape_id: UUID of the TypeShape node.

    Returns:
        TypeShape dict with full details.
    """
    graph = get_graph()
    try:
        result = graph.query(
            lq.GET_TYPE_SHAPE_BY_ID,
            params={"id": shape_id},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not result.result_set:
        raise HTTPException(status_code=404, detail=f"TypeShape {shape_id} not found")

    node = result.result_set[0][0]
    props = node.properties if hasattr(node, "properties") else node

    definition_str = props.get("definition", "{}")
    try:
        definition = json.loads(definition_str) if isinstance(definition_str, str) else definition_str
    except (json.JSONDecodeError, TypeError):
        definition = {}

    # Fetch connections (variables, accepting/producing functions, compatible shapes)
    connections: dict[str, Any] = {
        "variables": [],
        "accepting_functions": [],
        "producing_functions": [],
        "compatible_shapes": [],
    }
    try:
        conn_result = graph.query(
            lq.GET_TYPE_SHAPE_CONNECTIONS,
            params={"id": shape_id},
        )
        if conn_result.result_set:
            row = conn_result.result_set[0]
            connections["variables"] = [v for v in (row[0] or []) if isinstance(v, dict) and v.get("id")]
            connections["accepting_functions"] = [f for f in (row[1] or []) if isinstance(f, dict) and f.get("id")]
            connections["producing_functions"] = [f for f in (row[2] or []) if isinstance(f, dict) and f.get("id")]
            connections["compatible_shapes"] = [s for s in (row[3] or []) if isinstance(s, dict) and s.get("id")]
    except Exception as exc:
        logger.warning("Failed to fetch TypeShape connections: %s", exc)

    return {
        "id": props.get("id", ""),
        "shape_hash": props.get("shape_hash", ""),
        "kind": props.get("kind", ""),
        "base_type": props.get("base_type", ""),
        "definition": definition,
        "created_at": props.get("created_at", ""),
        "connections": connections,
    }
