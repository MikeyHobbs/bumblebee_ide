"""REST API endpoints for LogicNodes (TICKET-813)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.exceptions import NodeNotFoundError
from app.models.logic_models import (
    LogicNodeCreate,
    LogicNodeResponse,
    LogicNodeUpdate,
)
from app.services.crud import logic_node_service

router = APIRouter(prefix="/api/v1/nodes", tags=["logic-nodes"])


@router.post("", status_code=201, response_model=LogicNodeResponse)
def create_node(data: LogicNodeCreate) -> LogicNodeResponse:
    """Create a new LogicNode."""
    return logic_node_service.create_node(data)


@router.get("/{node_id}", response_model=LogicNodeResponse)
def get_node(node_id: str) -> LogicNodeResponse:
    """Get a LogicNode by UUID."""
    try:
        return logic_node_service.get_node(node_id)
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=list[LogicNodeResponse])
def list_nodes(
    query: str = Query("", description="Search by name or semantic intent"),
    kind: str | None = Query(None, description="Filter by kind"),
    limit: int = Query(50, ge=1, le=10000),
    offset: int = Query(0, ge=0),
) -> list[LogicNodeResponse]:
    """Search/list LogicNodes."""
    return logic_node_service.find_nodes(query=query, kind=kind, limit=limit, offset=offset)


@router.patch("/{node_id}", response_model=LogicNodeResponse)
def update_node(node_id: str, data: LogicNodeUpdate) -> LogicNodeResponse:
    """Update a LogicNode in-place."""
    try:
        return logic_node_service.update_node(node_id, data)
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{node_id}", status_code=204)
def deprecate_node(
    node_id: str,
    replacement_id: str | None = Query(None, description="UUID of replacement node"),
) -> None:
    """Deprecate a LogicNode (soft delete)."""
    try:
        logic_node_service.deprecate_node(node_id, replacement_id)
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
