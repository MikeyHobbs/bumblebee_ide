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

    return {
        "id": props.get("id", ""),
        "shape_hash": props.get("shape_hash", ""),
        "kind": props.get("kind", ""),
        "base_type": props.get("base_type", ""),
        "definition": definition,
        "created_at": props.get("created_at", ""),
    }
