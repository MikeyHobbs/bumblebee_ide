"""REST API endpoints for edges (TICKET-813)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models.exceptions import EdgeNotFoundError, NodeNotFoundError
from app.models.logic_models import EdgeCreate, EdgeResponse
from app.services import edge_service
from app.graph.client import get_graph
from app.graph import logic_queries as lq


class NodeVariable(BaseModel):
    """Variable connected to a LogicNode."""

    id: str
    name: str
    type_hint: str | None = None
    is_parameter: bool = False
    is_attribute: bool = False
    edge_type: str

router = APIRouter(prefix="/api/v1", tags=["edges"])


@router.get("/graph-overview")
def get_graph_overview() -> dict:
    """Lightweight graph overview for the knowledge-graph canvas.

    Returns minimal node fields (id, kind, name, module_path) and all
    inter-node edges for high-level kinds. No source_text is included,
    keeping the payload small (~10x smaller than the full node list).
    """
    kinds = ["function", "method", "class", "flow_function"]
    graph = get_graph()
    node_rows = graph.query(lq.GRAPH_OVERVIEW_NODES, params={"kinds": kinds})
    edge_rows = graph.query(lq.GRAPH_OVERVIEW_EDGES, params={"kinds": kinds})
    nodes = [
        {"id": str(r[0]), "kind": str(r[1]), "name": str(r[2]), "module_path": str(r[3])}
        for r in node_rows.result_set
    ]
    edges = [
        {"type": str(r[0]), "source": str(r[1]), "target": str(r[2])}
        for r in edge_rows.result_set
    ]
    return {"nodes": nodes, "edges": edges}


@router.get("/edges/all", response_model=list[EdgeResponse])
def list_all_edges(
    limit: int = Query(1000, ge=1, le=5000),
) -> list[EdgeResponse]:
    """Return all edges in the graph (for knowledge graph view)."""
    return edge_service.get_all_edges(limit=limit)


@router.post("/edges", status_code=201, response_model=EdgeResponse)
def add_edge(data: EdgeCreate) -> EdgeResponse:
    """Add an edge between two nodes."""
    try:
        return edge_service.add_edge(data)
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/edges", status_code=204)
def remove_edge(
    source: str = Query(..., description="Source node UUID"),
    target: str = Query(..., description="Target node UUID"),
    type: str = Query(..., description="Edge type"),
) -> None:
    """Remove an edge between two nodes."""
    try:
        edge_service.remove_edge(source, target, type)
    except EdgeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/nodes/{node_id}/edges", response_model=list[EdgeResponse])
def get_node_edges(
    node_id: str,
    direction: str = Query("both", description="outgoing, incoming, or both"),
    types: str | None = Query(None, description="Comma-separated edge types"),
) -> list[EdgeResponse]:
    """Get edges for a node."""
    edge_types = types.split(",") if types else None
    return edge_service.get_edges(node_id, direction=direction, edge_types=edge_types)


@router.get("/nodes/{node_id}/variables", response_model=list[NodeVariable])
def get_node_variables(node_id: str) -> list[NodeVariable]:
    """Get variable nodes connected to a LogicNode."""
    graph = get_graph()
    result = graph.query(lq.GET_VARIABLES_FOR_NODE, params={"node_id": node_id})
    variables: list[NodeVariable] = []
    for row in result.result_set:
        variables.append(NodeVariable(
            id=str(row[0]),
            name=str(row[1]),
            type_hint=str(row[2]) if row[2] else None,
            is_parameter=bool(row[3]) if row[3] is not None else False,
            is_attribute=bool(row[4]) if row[4] is not None else False,
            edge_type=str(row[5]),
        ))
    return variables


@router.get("/nodes/{node_id}/dependencies", response_model=list[EdgeResponse])
def get_dependencies(
    node_id: str,
    depth: int = Query(2, ge=1, le=10),
    edge_types: str | None = Query(None, description="Comma-separated edge types"),
) -> list[EdgeResponse]:
    """Get dependency subgraph (outgoing)."""
    types_list = edge_types.split(",") if edge_types else None
    return edge_service.get_dependencies(node_id, depth=depth, edge_types=types_list)


@router.get("/nodes/{node_id}/dependents", response_model=list[EdgeResponse])
def get_dependents(
    node_id: str,
    depth: int = Query(2, ge=1, le=10),
) -> list[EdgeResponse]:
    """Get dependent subgraph (incoming)."""
    return edge_service.get_dependents(node_id, depth=depth)
