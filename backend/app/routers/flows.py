"""REST API endpoints for Flows and gap analysis (TICKET-852)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.models.exceptions import NodeNotFoundError
from app.models.logic_models import (
    FlowCreate,
    FlowHierarchy,
    FlowResponse,
    FlowUpdate,
    GapReport,
    LogicNodeResponse,
)
from app.services.crud import flow_service
from app.services.analysis import gap_analysis

router = APIRouter(prefix="/api/v1", tags=["flows"])


# --- Flow endpoints ---


@router.post("/flows", status_code=201, response_model=FlowResponse)
def create_flow(data: FlowCreate) -> FlowResponse:
    """Create a new flow."""
    return flow_service.create_flow(data)


@router.get("/flows/{flow_id}", response_model=FlowResponse)
def get_flow(flow_id: str) -> FlowResponse:
    """Get a flow by UUID."""
    try:
        return flow_service.get_flow(flow_id)
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/flows", response_model=list[FlowResponse])
def list_flows() -> list[FlowResponse]:
    """List all flows."""
    return flow_service.list_flows()


@router.patch("/flows/{flow_id}", response_model=FlowResponse)
def update_flow(flow_id: str, data: FlowUpdate) -> FlowResponse:
    """Update a flow."""
    try:
        return flow_service.update_flow(flow_id, data)
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/flows/{flow_id}", status_code=204)
def delete_flow(flow_id: str) -> None:
    """Delete a flow."""
    try:
        flow_service.delete_flow(flow_id)
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/flows/{flow_id}/sub-flows", response_model=FlowResponse)
def add_sub_flow(
    flow_id: str,
    child_flow_id: str = Query(..., description="UUID of the child flow"),
    step_order: int = Query(0, description="Position in the parent flow"),
) -> FlowResponse:
    """Add a sub-flow to a parent flow."""
    try:
        return flow_service.add_sub_flow(flow_id, child_flow_id, step_order)
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/flows/{flow_id}/sub-flows/{child_flow_id}", response_model=FlowResponse)
def remove_sub_flow(flow_id: str, child_flow_id: str) -> FlowResponse:
    """Remove a sub-flow from a parent flow."""
    try:
        return flow_service.remove_sub_flow(flow_id, child_flow_id)
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/flows/{flow_id}/promote", response_model=LogicNodeResponse)
def promote_flow(flow_id: str) -> LogicNodeResponse:
    """Promote a flow to a callable LogicNode (flow_function)."""
    try:
        return flow_service.promote_flow_to_node(flow_id)
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/flows/{flow_id}/hierarchy", response_model=FlowHierarchy)
def get_flow_hierarchy(flow_id: str) -> FlowHierarchy:
    """Get the full flow hierarchy (recursive)."""
    try:
        return flow_service.get_flow_hierarchy(flow_id)
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/flows/discover", response_model=list[dict[str, Any]])
def discover_flows(
    entry_node_id: str = Query(..., description="UUID of the entry LogicNode"),
    max_depth: int = Query(10, ge=1, le=50),
) -> list[dict[str, Any]]:
    """Auto-discover flow patterns from an entry point."""
    return flow_service.discover_flows(entry_node_id, max_depth)


# --- Gap analysis endpoints ---


@router.get("/gaps/dead-ends", response_model=list[LogicNodeResponse])
def get_dead_ends(scope: str | None = Query(None)) -> list[LogicNodeResponse]:
    """Find dead-end LogicNodes."""
    return gap_analysis.find_dead_ends(scope)


@router.get("/gaps/orphans", response_model=list[LogicNodeResponse])
def get_orphans(scope: str | None = Query(None)) -> list[LogicNodeResponse]:
    """Find orphan LogicNodes."""
    return gap_analysis.find_orphans(scope)


@router.get("/gaps/missing-error-handling", response_model=list[dict[str, Any]])
def get_missing_error_handling(scope: str | None = Query(None)) -> list[dict[str, Any]]:
    """Find missing error handling."""
    return gap_analysis.find_missing_error_handling(scope)


@router.get("/gaps/circular-deps", response_model=list[list[str]])
def get_circular_deps(scope: str | None = Query(None)) -> list[list[str]]:
    """Find circular dependencies."""
    return gap_analysis.find_circular_deps(scope)


@router.get("/gaps/untested-mutations", response_model=list[dict[str, Any]])
def get_untested_mutations(scope: str | None = Query(None)) -> list[dict[str, Any]]:
    """Find untested mutations."""
    return gap_analysis.find_untested_mutations(scope)


@router.get("/gaps/report", response_model=GapReport)
def get_gap_report(scope: str | None = Query(None)) -> GapReport:
    """Full gap analysis report."""
    return gap_analysis.get_full_report(scope)
