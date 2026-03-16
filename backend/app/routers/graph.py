"""Router for graph query endpoints."""

from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1", tags=["graph"])


class GraphNodeResponse(BaseModel):
    """A single graph node."""

    id: str
    label: str
    properties: dict[str, str | int | bool | None]


class GraphEdgeResponse(BaseModel):
    """A single graph edge."""

    type: str
    source: str
    target: str
    properties: dict[str, str | int | bool | None]


class GraphQueryRequest(BaseModel):
    """Request body for raw Cypher queries."""

    cypher: str


class GraphQueryResponse(BaseModel):
    """Response from a Cypher query."""

    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
    raw_results: list[list[str | int | None]]


@router.get("/graph/nodes", response_model=list[GraphNodeResponse])
async def get_all_nodes(
    label: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[GraphNodeResponse]:
    """Get all nodes, optionally filtered by label."""
    raise HTTPException(
        status_code=501,
        detail="Graph query requires FalkorDB. Use POST /api/v1/index first.",
    )


@router.get("/graph/node/{node_id}", response_model=GraphNodeResponse)
async def get_node(node_id: str) -> GraphNodeResponse:
    """Get a single node by ID."""
    raise HTTPException(
        status_code=501,
        detail="Graph query requires FalkorDB.",
    )


@router.post("/query", response_model=GraphQueryResponse)
async def execute_query(request: GraphQueryRequest) -> GraphQueryResponse:
    """Execute a raw Cypher query against the graph."""
    raise HTTPException(
        status_code=501,
        detail="Graph query requires FalkorDB.",
    )
