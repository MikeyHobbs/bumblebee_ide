"""Router for variable timeline and search endpoints."""

from __future__ import annotations

import logging

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query

from app.graph.client import get_graph
from app.graph import queries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["variables"])


class TimelineEntryResponse(BaseModel):
    """A single entry in a mutation timeline."""

    edge_type: str
    function_name: str
    variable_name: str
    line: int
    seq: int
    properties: dict[str, str | int | bool | None]


class TimelineResponse(BaseModel):
    """Full mutation timeline for a variable."""

    variable: dict[str, str | int | None]
    origin: TimelineEntryResponse | None
    mutations: list[TimelineEntryResponse]
    reads: list[TimelineEntryResponse]
    passes: list[TimelineEntryResponse]
    returns: list[TimelineEntryResponse]
    feeds: list[TimelineEntryResponse]
    terminal: TimelineEntryResponse | None


class VariableSearchResult(BaseModel):
    """A single variable search result."""

    name: str
    scope: str
    origin_line: int
    origin_func: str
    type_hint: str | None
    module_path: str


@router.get("/variables/{variable_id}/timeline", response_model=TimelineResponse)
async def get_variable_timeline(variable_id: str) -> TimelineResponse:
    """Get the full mutation timeline for a variable.

    The variable_id should be the fully qualified variable name
    (e.g., "module.function.variable_name").
    """
    try:
        graph = get_graph()

        # Get the variable node
        var_result = graph.query(queries.GET_VARIABLE_BY_NAME, params={"name": variable_id})
        if not var_result.result_set:
            raise HTTPException(status_code=404, detail=f"Variable not found: {variable_id}")

        var_node = var_result.result_set[0][0]
        var_props = var_node.properties if hasattr(var_node, "properties") else {}

        variable_info: dict[str, str | int | None] = {
            "name": var_props.get("name"),
            "scope": var_props.get("scope"),
            "origin_line": var_props.get("origin_line"),
            "origin_func": var_props.get("origin_func"),
            "type_hint": var_props.get("type_hint") or None,
        }

        # Query all edges involving this variable
        origin: TimelineEntryResponse | None = None
        mutations: list[TimelineEntryResponse] = []
        reads: list[TimelineEntryResponse] = []
        passes: list[TimelineEntryResponse] = []
        returns: list[TimelineEntryResponse] = []
        feeds: list[TimelineEntryResponse] = []

        # ASSIGNS edges
        assigns_result = graph.query(
            "MATCH (f:Function)-[a:ASSIGNS]->(v:Variable {name: $name}) RETURN f.name, a",
            params={"name": variable_id},
        )
        for row in assigns_result.result_set:
            func_name = row[0]
            edge = row[1]
            props = edge.properties if hasattr(edge, "properties") else {}
            entry = TimelineEntryResponse(
                edge_type="ASSIGNS",
                function_name=func_name or "",
                variable_name=variable_id,
                line=int(props.get("line", 0) or 0),
                seq=int(props.get("seq", 0) or 0),
                properties=_sanitize_props(props),
            )
            if origin is None:
                origin = entry
            mutations.append(entry)

        # MUTATES edges
        mutates_result = graph.query(
            "MATCH (f:Function)-[m:MUTATES]->(v:Variable {name: $name}) RETURN f.name, m",
            params={"name": variable_id},
        )
        for row in mutates_result.result_set:
            func_name = row[0]
            edge = row[1]
            props = edge.properties if hasattr(edge, "properties") else {}
            mutations.append(TimelineEntryResponse(
                edge_type="MUTATES",
                function_name=func_name or "",
                variable_name=variable_id,
                line=int(props.get("line", 0) or 0),
                seq=int(props.get("seq", 0) or 0),
                properties=_sanitize_props(props),
            ))

        # READS edges
        reads_result = graph.query(
            "MATCH (f:Function)-[r:READS]->(v:Variable {name: $name}) RETURN f.name, r",
            params={"name": variable_id},
        )
        for row in reads_result.result_set:
            func_name = row[0]
            edge = row[1]
            props = edge.properties if hasattr(edge, "properties") else {}
            reads.append(TimelineEntryResponse(
                edge_type="READS",
                function_name=func_name or "",
                variable_name=variable_id,
                line=int(props.get("line", 0) or 0),
                seq=int(props.get("seq", 0) or 0),
                properties=_sanitize_props(props),
            ))

        # RETURNS edges
        returns_result = graph.query(
            "MATCH (f:Function)-[r:RETURNS]->(v:Variable {name: $name}) RETURN f.name, r",
            params={"name": variable_id},
        )
        for row in returns_result.result_set:
            func_name = row[0]
            edge = row[1]
            props = edge.properties if hasattr(edge, "properties") else {}
            returns.append(TimelineEntryResponse(
                edge_type="RETURNS",
                function_name=func_name or "",
                variable_name=variable_id,
                line=int(props.get("line", 0) or 0),
                seq=int(props.get("seq", 0) or 0),
                properties=_sanitize_props(props),
            ))

        # PASSES_TO edges (outgoing)
        passes_result = graph.query(
            "MATCH (v:Variable {name: $name})-[p:PASSES_TO]->(t:Variable) RETURN t.name, p",
            params={"name": variable_id},
        )
        for row in passes_result.result_set:
            target_name = row[0]
            edge = row[1]
            props = edge.properties if hasattr(edge, "properties") else {}
            passes.append(TimelineEntryResponse(
                edge_type="PASSES_TO",
                function_name="",
                variable_name=target_name or "",
                line=int(props.get("call_line", 0) or 0),
                seq=int(props.get("seq", 0) or 0),
                properties=_sanitize_props(props),
            ))

        # FEEDS edges (incoming)
        feeds_result = graph.query(
            "MATCH (src:Variable)-[fd:FEEDS]->(v:Variable {name: $name}) RETURN src.name, fd",
            params={"name": variable_id},
        )
        for row in feeds_result.result_set:
            source_name = row[0]
            edge = row[1]
            props = edge.properties if hasattr(edge, "properties") else {}
            feeds.append(TimelineEntryResponse(
                edge_type="FEEDS",
                function_name="",
                variable_name=source_name or "",
                line=int(props.get("line", 0) or 0),
                seq=int(props.get("seq", 0) or 0),
                properties=_sanitize_props(props),
            ))

        # Sort
        mutations.sort(key=lambda e: (e.function_name, e.seq))
        reads.sort(key=lambda e: (e.function_name, e.seq))
        returns.sort(key=lambda e: (e.function_name, e.seq))
        passes.sort(key=lambda e: e.seq)
        feeds.sort(key=lambda e: e.seq)

        # Terminal: last interaction
        all_entries = mutations + reads + returns
        terminal = max(all_entries, key=lambda e: (e.function_name, e.seq)) if all_entries else None

        return TimelineResponse(
            variable=variable_info,
            origin=origin,
            mutations=mutations,
            reads=reads,
            passes=passes,
            returns=returns,
            feeds=feeds,
            terminal=terminal,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Timeline query failed: {exc}") from exc


@router.get("/variables/search", response_model=list[VariableSearchResult])
async def search_variables(
    name: str = Query(..., description="Variable name to search for"),
    scope: str | None = Query(None, description="Optional scope filter"),
) -> list[VariableSearchResult]:
    """Search for variables by name, optionally filtered by scope."""
    try:
        graph = get_graph()
        if scope:
            result = graph.query(queries.SEARCH_VARIABLES_WITH_SCOPE, params={"name": name, "scope": scope})
        else:
            result = graph.query(queries.SEARCH_VARIABLES, params={"name": name})

        results: list[VariableSearchResult] = []
        for row in result.result_set:
            node = row[0]
            props = node.properties if hasattr(node, "properties") else {}
            results.append(VariableSearchResult(
                name=props.get("name", ""),
                scope=props.get("scope", ""),
                origin_line=int(props.get("origin_line", 0) or 0),
                origin_func=props.get("origin_func", ""),
                type_hint=props.get("type_hint") or None,
                module_path=props.get("module_path", ""),
            ))
        return results
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Variable search failed: {exc}") from exc


def _sanitize_props(props: dict) -> dict[str, str | int | bool | None]:  # type: ignore[type-arg]
    """Sanitize edge properties for JSON response."""
    result: dict[str, str | int | bool | None] = {}
    for k, v in props.items():
        if isinstance(v, (str, int, bool)) or v is None:
            result[k] = v
        else:
            result[k] = str(v)
    return result
