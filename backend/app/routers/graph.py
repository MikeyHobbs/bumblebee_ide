"""Router for graph query endpoints."""

from __future__ import annotations

import logging

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.graph.client import get_graph
from app.models.exceptions import GraphQueryError, NodeNotFoundError

logger = logging.getLogger(__name__)

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


def _node_to_response(node) -> GraphNodeResponse:  # type: ignore[no-untyped-def]
    """Convert a FalkorDB node to a response model."""
    labels = node.labels if hasattr(node, "labels") else []
    label = labels[0] if labels else "Unknown"
    props: dict[str, str | int | bool | None] = {}
    if hasattr(node, "properties"):
        for k, v in node.properties.items():
            if isinstance(v, (str, int, bool)) or v is None:
                props[k] = v
            else:
                props[k] = str(v)
    node_id = props.get("name", str(node.id if hasattr(node, "id") else ""))
    return GraphNodeResponse(id=str(node_id), label=label, properties=props)


@router.get("/graph/nodes", response_model=list[GraphNodeResponse])
async def get_all_nodes(
    label: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[GraphNodeResponse]:
    """Get all nodes, optionally filtered by label."""
    try:
        graph = get_graph()
        if label:
            cypher = f"MATCH (n:{label}) RETURN n SKIP $offset LIMIT $limit"
        else:
            cypher = "MATCH (n) RETURN n SKIP $offset LIMIT $limit"
        result = graph.query(cypher, params={"offset": offset, "limit": limit})
        nodes: list[GraphNodeResponse] = []
        for row in result.result_set:
            node = row[0]
            nodes.append(_node_to_response(node))
        return nodes
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {exc}") from exc


@router.get("/graph/node/{node_id}", response_model=GraphNodeResponse)
async def get_node(node_id: str) -> GraphNodeResponse:
    """Get a single node by name."""
    try:
        graph = get_graph()
        result = graph.query(
            "MATCH (n) WHERE n.name = $name RETURN n LIMIT 1",
            params={"name": node_id},
        )
        if not result.result_set:
            raise NodeNotFoundError(node_id)
        node = result.result_set[0][0]
        return _node_to_response(node)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}") from None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {exc}") from exc


@router.post("/query", response_model=GraphQueryResponse)
async def execute_query(request: GraphQueryRequest) -> GraphQueryResponse:
    """Execute a raw Cypher query against the graph."""
    try:
        graph = get_graph()
        result = graph.query(request.cypher)
        nodes: list[GraphNodeResponse] = []
        edges: list[GraphEdgeResponse] = []
        raw_results: list[list[str | int | None]] = []

        for row in result.result_set:
            raw_row: list[str | int | None] = []
            for item in row:
                if hasattr(item, "labels"):
                    nodes.append(_node_to_response(item))
                    raw_row.append(str(item.properties.get("name", "")))
                elif hasattr(item, "relation"):
                    edge_type = item.relation if isinstance(item.relation, str) else str(item.relation)
                    props: dict[str, str | int | bool | None] = {}
                    if hasattr(item, "properties"):
                        for k, v in item.properties.items():
                            if isinstance(v, (str, int, bool)) or v is None:
                                props[k] = v
                            else:
                                props[k] = str(v)
                    edges.append(GraphEdgeResponse(
                        type=edge_type,
                        source=str(item.src_node) if hasattr(item, "src_node") else "",
                        target=str(item.dest_node) if hasattr(item, "dest_node") else "",
                        properties=props,
                    ))
                    raw_row.append(edge_type)
                elif isinstance(item, (str, int)):
                    raw_row.append(item)
                elif item is None:
                    raw_row.append(None)
                else:
                    raw_row.append(str(item))
            raw_results.append(raw_row)

        return GraphQueryResponse(nodes=nodes, edges=edges, raw_results=raw_results)
    except Exception as exc:
        raise GraphQueryError(str(exc)) from exc
