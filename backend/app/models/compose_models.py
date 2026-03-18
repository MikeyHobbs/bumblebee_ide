"""Pydantic models for the VFS Compose endpoints (TICKET-912, TICKET-913)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.logic_models import LogicNodeResponse


class ComposeParseRequest(BaseModel):
    """Request body for POST /api/v1/compose/parse."""

    source: str
    module_path: str


class ComposeParseReport(BaseModel):
    """Import report subset returned by the parse endpoint."""

    nodes_created: int = 0
    nodes_updated: int = 0
    edges_created: int = 0
    variables_created: int = 0
    errors: list[str] = Field(default_factory=list)


class ParsedNodeInfo(BaseModel):
    """A node created/found during compose parse."""

    id: str
    name: str


class ComposeParseResponse(BaseModel):
    """Response for POST /api/v1/compose/parse."""

    report: ComposeParseReport
    nodes: list[ParsedNodeInfo] = Field(default_factory=list)
    variable_ids: list[str] = Field(default_factory=list)


class ComposeSaveRequest(BaseModel):
    """Request body for POST /api/v1/compose/save."""

    node_id: str
    source: str


class ImpactedNode(BaseModel):
    """A node affected by a save operation."""

    id: str
    name: str
    reason: str


class ComposeSaveResponse(BaseModel):
    """Response for POST /api/v1/compose/save."""

    updated_node: LogicNodeResponse
    impacted_nodes: list[ImpactedNode] = Field(default_factory=list)
