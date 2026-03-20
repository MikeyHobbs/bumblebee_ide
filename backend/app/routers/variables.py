"""REST API endpoints for variables and mutation timelines (TICKET-813)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.models.exceptions import NodeNotFoundError
from app.models.logic_models import MutationTimeline, VariableResponse
from app.services.crud import variable_timeline_service

router = APIRouter(prefix="/api/v1/variables", tags=["variables"])


@router.get("/{variable_id}/timeline", response_model=MutationTimeline)
def get_variable_timeline(variable_id: str) -> MutationTimeline:
    """Get the full mutation timeline for a variable."""
    try:
        return variable_timeline_service.get_variable_timeline(variable_id)
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/search", response_model=list[VariableResponse])
def search_variables(
    name: str = Query(..., description="Variable name (partial match)"),
    scope: str | None = Query(None, description="Scope filter (partial match)"),
) -> list[VariableResponse]:
    """Search for variables by name and optional scope."""
    from app.graph.client import get_graph  # pylint: disable=import-outside-toplevel
    from app.graph import logic_queries as lq  # pylint: disable=import-outside-toplevel

    graph = get_graph()
    result = graph.query(
        lq.SEARCH_VARIABLES_BY_NAME,
        params={"name": name, "scope": scope or "", "limit": 50},
    )
    return [variable_timeline_service._variable_from_graph(row[0]) for row in result.result_set]


@router.get("/trace", response_model=list[MutationTimeline])
def trace_variable(
    name: str = Query(..., description="Variable name"),
    scope: str | None = Query(None, description="Scope filter"),
) -> list[MutationTimeline]:
    """Trace a variable — find it and return mutation timelines."""
    return variable_timeline_service.trace_variable(name, scope)


@router.get("/{node_id}/impact", response_model=list[dict[str, Any]])
def get_impact(node_id: str) -> list[dict[str, Any]]:
    """Impact analysis: find all downstream consumers of variables mutated by this node."""
    return variable_timeline_service.get_impact(node_id)
