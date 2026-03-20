"""Graph-aware autocomplete suggestions endpoint (TICKET-910).

Unified POST endpoint that accepts a trigger type + context and returns
ranked completion suggestions from the graph database.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.graph.client import get_graph
from app.graph import logic_queries as lq

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/suggestions", tags=["suggestions"])


class CompletionRequest(BaseModel):
    """Request body for the unified suggestions endpoint."""

    trigger: str = Field(description="Trigger type: variable_consumer, member_access, import, general")
    variable_name: str | None = None
    type_hint: str | None = None
    object_name: str | None = None
    module_prefix: str | None = None
    query: str | None = None
    scope_node_ids: list[str] | None = None
    limit: int = Field(default=15, le=50)


class CompletionItem(BaseModel):
    """A single completion suggestion."""

    label: str
    kind: str
    detail: str
    documentation: str
    insert_text: str
    sort_key: str
    node_id: str
    module_path: str


def _build_snippet(name: str, params_raw: Any) -> str:
    """Build a Monaco snippet string from function name and params field.

    Produces e.g. ``authenticate(${1:email}, ${2:password})``.
    """
    params: list[dict[str, Any]] = []
    if isinstance(params_raw, str):
        try:
            params = json.loads(params_raw)
        except (json.JSONDecodeError, TypeError):
            pass
    elif isinstance(params_raw, list):
        params = params_raw

    if not params:
        return f"{name}()"

    # Filter out 'self' and 'cls' params
    filtered = [p for p in params if isinstance(p, dict) and p.get("name") not in ("self", "cls")]
    if not filtered:
        return f"{name}()"

    placeholders = []
    for i, p in enumerate(filtered, 1):
        pname = p.get("name", f"arg{i}")
        placeholders.append(f"${{{i}:{pname}}}")

    return f"{name}({', '.join(placeholders)})"


def _node_to_completion(props: dict[str, Any], kind_override: str | None = None, sort_prefix: str = "b") -> CompletionItem:
    """Convert graph node properties to a CompletionItem."""
    name = props.get("name", "")
    short_name = name.split(".")[-1] if "." in name else name
    node_kind = kind_override or props.get("kind", "function")
    signature = props.get("signature", "")
    module_path = props.get("module_path", "")
    return_type = props.get("return_type", "")
    params_raw = props.get("params", "[]")

    detail = signature if signature else short_name
    doc_parts = []
    if module_path:
        doc_parts.append(f"**Module:** `{module_path}`")
    if return_type:
        doc_parts.append(f"**Returns:** `{return_type}`")
    docstring = props.get("docstring", "")
    if docstring:
        doc_parts.append(docstring)

    insert_text = _build_snippet(short_name, params_raw) if node_kind in ("function", "method") else short_name

    return CompletionItem(
        label=short_name,
        kind=node_kind,
        detail=detail,
        documentation="\n\n".join(doc_parts),
        insert_text=insert_text,
        sort_key=f"{sort_prefix}_{short_name}",
        node_id=props.get("id", ""),
        module_path=module_path,
    )


def _extract_props(row_item: Any) -> dict[str, Any]:
    """Extract properties dict from a FalkorDB result row item."""
    if hasattr(row_item, "properties"):
        return row_item.properties
    if isinstance(row_item, dict):
        return row_item
    return {}


@router.post("/complete")
async def complete(req: CompletionRequest) -> list[CompletionItem]:
    """Unified graph-aware autocomplete endpoint.

    Dispatches to different graph queries based on the trigger type.

    Args:
        req: Completion request with trigger type and context params.

    Returns:
        Ranked list of CompletionItems.
    """
    graph = get_graph()
    items: list[CompletionItem] = []

    try:
        if req.trigger == "variable_consumer":
            items = _handle_variable_consumer(graph, req)
        elif req.trigger == "member_access":
            items = _handle_member_access(graph, req)
        elif req.trigger == "import":
            items = _handle_import(graph, req)
        elif req.trigger == "general":
            items = _handle_general(graph, req)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown trigger type: {req.trigger}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Suggestion query failed: %s", exc)
        return []

    return items[:req.limit]


def _handle_variable_consumer(graph: Any, req: CompletionRequest) -> list[CompletionItem]:
    """Find functions that accept a given variable as input."""
    items: list[CompletionItem] = []
    variable_name = req.variable_name or ""
    if not variable_name:
        return items

    # Step 1: Try to find the variable and use TypeShape-based consumer discovery
    try:
        var_result = graph.query(
            lq.SEARCH_VARIABLES_BY_NAME,
            params={"name": variable_name, "scope": "", "limit": 5},
        )
        for var_row in var_result.result_set:
            var_props = _extract_props(var_row[0])
            var_id = var_props.get("id", "")
            if not var_id:
                continue

            consumer_result = graph.query(
                lq.FIND_CONSUMERS_FOR_VARIABLE,
                params={"variable_id": var_id},
            )
            for row in consumer_result.result_set:
                props = _extract_props(row[0])
                if props.get("id"):
                    items.append(_node_to_completion(props, sort_prefix="a"))
    except Exception:
        logger.debug("TypeShape consumer lookup failed, falling back to param name match")

    # Step 2: Fallback — name-based param matching
    if not items:
        try:
            result = graph.query(
                lq.FIND_NODES_BY_PARAM_NAME,
                params={"param_name": variable_name, "limit": req.limit},
            )
            for row in result.result_set:
                props = {
                    "id": row[0],
                    "name": row[1],
                    "params": row[2],
                    "signature": row[3],
                    "return_type": row[4],
                    "kind": "function",
                    "module_path": "",
                }
                items.append(_node_to_completion(props, sort_prefix="b"))
        except Exception:
            logger.debug("Param name fallback also failed")

    # Deduplicate by node_id
    seen: set[str] = set()
    deduped: list[CompletionItem] = []
    for item in items:
        if item.node_id not in seen:
            seen.add(item.node_id)
            deduped.append(item)
    return deduped


def _handle_member_access(graph: Any, req: CompletionRequest) -> list[CompletionItem]:
    """Find methods/attributes of a class when user types `obj.`."""
    items: list[CompletionItem] = []
    class_name = req.object_name or ""
    if not class_name:
        return items

    result = graph.query(
        lq.FIND_CLASS_MEMBERS,
        params={"class_name": class_name, "limit": req.limit},
    )
    for row in result.result_set:
        props = {
            "id": row[0],
            "name": row[1],
            "kind": row[2],
            "signature": row[3],
            "return_type": row[4],
            "module_path": row[5],
        }
        # For member access, use short name without class prefix
        name = props["name"]
        short = name.split(".")[-1] if "." in name else name
        props["name"] = short
        kind = "method" if props["kind"] == "function" else props["kind"]
        items.append(_node_to_completion(props, kind_override=kind, sort_prefix="a"))

    return items


def _handle_import(graph: Any, req: CompletionRequest) -> list[CompletionItem]:
    """Find available functions/classes in a module by prefix."""
    items: list[CompletionItem] = []
    prefix = req.module_prefix or ""
    if not prefix:
        return items

    result = graph.query(
        lq.FIND_MODULES_BY_PREFIX,
        params={"prefix": prefix, "limit": req.limit},
    )
    for row in result.result_set:
        props = {
            "id": row[0],
            "name": row[1],
            "kind": row[2],
            "signature": row[3],
            "module_path": row[4],
        }
        items.append(_node_to_completion(props, sort_prefix="a"))

    return items


def _handle_general(graph: Any, req: CompletionRequest) -> list[CompletionItem]:
    """General search — any matching function/class by name substring."""
    items: list[CompletionItem] = []
    query = req.query or ""
    if not query:
        return items

    result = graph.query(
        lq.FIND_LOGIC_NODES,
        params={"query": query, "kind": "", "offset": 0, "limit": req.limit},
    )
    for row in result.result_set:
        props = _extract_props(row[0])
        if props.get("id"):
            items.append(_node_to_completion(props, sort_prefix="b"))

    return items
