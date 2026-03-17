"""REST API endpoints for VFS projection (TICKET-841)."""

from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.services import vfs_engine

router = APIRouter(prefix="/api/v1/vfs", tags=["vfs"])


class ProjectRequest(BaseModel):
    """Request body for VFS projection."""

    output_dir: str = ".bumblebee/vfs"


class SyncRequest(BaseModel):
    """Request body for VFS-to-graph sync."""

    path: str


class ProjectionReportResponse(BaseModel):
    """Response for projection operations."""

    files_written: int
    modules_projected: int
    errors: list[str]


class SyncReportResponse(BaseModel):
    """Response for sync operations."""

    nodes_updated: int
    nodes_created: int
    nodes_deprecated: int
    errors: list[str]


@router.get("/{module_path:path}", response_class=PlainTextResponse)
def get_vfs_module(module_path: str) -> str:
    """Get projected Python source for a module."""
    source = vfs_engine.project_module(module_path)
    if not source:
        raise HTTPException(status_code=404, detail=f"No nodes found for module: {module_path}")
    return source


@router.get("/node/{node_id}", response_class=PlainTextResponse)
def get_vfs_node(node_id: str) -> str:
    """Get projected source for a single LogicNode."""
    source = vfs_engine.project_node(node_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
    return source


@router.post("/project", response_model=ProjectionReportResponse)
def project_all(data: ProjectRequest) -> ProjectionReportResponse:
    """Trigger full VFS projection."""
    report = vfs_engine.project_all(data.output_dir)
    return ProjectionReportResponse(
        files_written=report.files_written,
        modules_projected=report.modules_projected,
        errors=report.errors,
    )


@router.post("/sync", response_model=SyncReportResponse)
def sync_vfs(data: SyncRequest) -> SyncReportResponse:
    """Sync VFS files back to the graph (reverse pipeline)."""
    report = vfs_engine.sync_vfs_to_graph(data.path)
    return SyncReportResponse(
        nodes_updated=report.nodes_updated,
        nodes_created=report.nodes_created,
        nodes_deprecated=report.nodes_deprecated,
        errors=report.errors,
    )
