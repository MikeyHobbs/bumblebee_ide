"""Edge CRUD service (TICKET-811).

Operations for creating, removing, and querying edges between nodes.
"""

from __future__ import annotations

from typing import Any

from app.graph.client import get_graph
from app.graph import logic_queries as lq
from app.models.exceptions import EdgeNotFoundError, NodeNotFoundError
from app.models.logic_models import EdgeCreate, EdgeResponse, EdgeType


def get_all_edges(limit: int = 1000) -> list[EdgeResponse]:
    """Return all edges in the graph, up to the given limit.

    Args:
        limit: Maximum number of edges to return.

    Returns:
        List of EdgeResponse objects.
    """
    graph = get_graph()
    result = graph.query(lq.GET_ALL_EDGES)
    edges: list[EdgeResponse] = []
    for row in result.result_set:
        if len(edges) >= limit:
            break
        edge_type_str = row[0]
        source_id = row[1]
        target_id = row[2]
        if not isinstance(source_id, str) or not isinstance(target_id, str):
            continue
        try:
            et = EdgeType(edge_type_str)
        except ValueError:
            continue
        edges.append(EdgeResponse(
            type=et,
            source=source_id,
            target=target_id,
            properties=row[3] if len(row) > 3 and isinstance(row[3], dict) else {},
        ))
    return edges


def add_edge(data: EdgeCreate) -> EdgeResponse:
    """Create a typed edge between two nodes.

    Validates source and target exist, then creates the edge with properties.
    Idempotent — adding a duplicate edge is a no-op.

    Args:
        data: Edge creation parameters.

    Returns:
        EdgeResponse for the created edge.

    Raises:
        NodeNotFoundError: If source or target node doesn't exist.
        ValueError: If edge type is not recognized.
    """
    edge_type_str = data.edge_type.value
    query = lq.EDGE_MERGE_QUERIES.get(edge_type_str)
    if query is None:
        raise ValueError(f"Unknown edge type: {edge_type_str}")

    graph = get_graph()

    result = graph.query(
        query,
        params={
            "source_id": data.source_id,
            "target_id": data.target_id,
            "properties": data.properties,
        },
    )

    if not result.result_set:
        raise NodeNotFoundError(f"{data.source_id} or {data.target_id}")

    return EdgeResponse(
        type=data.edge_type,
        source=data.source_id,
        target=data.target_id,
        properties=data.properties,
    )


def remove_edge(source_id: str, target_id: str, edge_type: str) -> None:
    """Delete an edge between two nodes.

    Args:
        source_id: UUID of the source node.
        target_id: UUID of the target node.
        edge_type: The edge type string (e.g., "CALLS").

    Raises:
        EdgeNotFoundError: If the edge doesn't exist.
    """
    graph = get_graph()
    query = lq.DELETE_EDGE_TEMPLATE.format(edge_type=edge_type)

    result = graph.query(
        query,
        params={"source_id": source_id, "target_id": target_id},
    )

    if result.relationships_deleted == 0:
        raise EdgeNotFoundError(source_id, target_id, edge_type)


def get_edges(
    node_id: str,
    direction: str = "both",
    edge_types: list[str] | None = None,
) -> list[EdgeResponse]:
    """Get edges for a node, optionally filtered by direction and type.

    Args:
        node_id: UUID of the node.
        direction: One of "outgoing", "incoming", or "both".
        edge_types: Optional list of edge type strings to filter by.

    Returns:
        List of EdgeResponse objects.
    """
    graph = get_graph()
    types_list = edge_types or []
    edges: list[EdgeResponse] = []

    if direction in ("outgoing", "both"):
        result = graph.query(
            lq.GET_OUTGOING_EDGES,
            params={"node_id": node_id, "edge_types": types_list},
        )
        for row in result.result_set:
            edges.append(EdgeResponse(
                type=EdgeType(row[0]),
                source=row[1],
                target=row[2],
                properties=row[3] if len(row) > 3 and isinstance(row[3], dict) else {},
            ))

    if direction in ("incoming", "both"):
        result = graph.query(
            lq.GET_INCOMING_EDGES,
            params={"node_id": node_id, "edge_types": types_list},
        )
        for row in result.result_set:
            edges.append(EdgeResponse(
                type=EdgeType(row[0]),
                source=row[1],
                target=row[2],
                properties=row[3] if len(row) > 3 and isinstance(row[3], dict) else {},
            ))

    return edges


def get_dependencies(
    node_id: str,
    depth: int = 2,
    edge_types: list[str] | None = None,
) -> list[EdgeResponse]:
    """Multi-hop outgoing traversal for dependencies.

    Args:
        node_id: UUID of the root LogicNode.
        depth: Maximum hop count.
        edge_types: Not currently used in the Cypher query (traverses CALLS|DEPENDS_ON|IMPLEMENTS|VALIDATES|TRANSFORMS).

    Returns:
        List of EdgeResponse objects along the dependency paths.
    """
    graph = get_graph()
    result = graph.query(
        lq.GET_DEPENDENCIES,
        params={"node_id": node_id, "depth": depth},
    )

    edges: list[EdgeResponse] = []
    if result.result_set:
        for row in result.result_set:
            # Parse edges from result
            raw_edges = row[2] if len(row) > 2 else []
            if isinstance(raw_edges, list):
                for edge_data in raw_edges:
                    if hasattr(edge_data, "properties"):
                        props = edge_data.properties
                        edges.append(EdgeResponse(
                            type=EdgeType(edge_data.relation if hasattr(edge_data, "relation") else "CALLS"),
                            source=props.get("source", ""),
                            target=props.get("target", ""),
                            properties=props,
                        ))
    return edges


def get_dependents(
    node_id: str,
    depth: int = 2,
) -> list[EdgeResponse]:
    """Multi-hop incoming traversal for dependents.

    Args:
        node_id: UUID of the root LogicNode.
        depth: Maximum hop count.

    Returns:
        List of EdgeResponse objects along the dependent paths.
    """
    graph = get_graph()
    result = graph.query(
        lq.GET_DEPENDENTS,
        params={"node_id": node_id, "depth": depth},
    )

    edges: list[EdgeResponse] = []
    if result.result_set:
        for row in result.result_set:
            raw_edges = row[2] if len(row) > 2 else []
            if isinstance(raw_edges, list):
                for edge_data in raw_edges:
                    if hasattr(edge_data, "properties"):
                        props = edge_data.properties
                        edges.append(EdgeResponse(
                            type=EdgeType(edge_data.relation if hasattr(edge_data, "relation") else "CALLS"),
                            source=props.get("source", ""),
                            target=props.get("target", ""),
                            properties=props,
                        ))
    return edges
