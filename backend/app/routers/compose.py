"""REST API endpoints for VFS Compose (TICKET-912, TICKET-913).

Provides parse and save endpoints for the compose editor surface.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.graph.client import get_graph
from app.graph import logic_queries as lq
from app.models.compose_models import (
    ComposeParseReport,
    ComposeParseRequest,
    ComposeParseResponse,
    ComposeSaveRequest,
    ComposeSaveResponse,
    ImpactedNode,
    ParsedNodeInfo,
)
from app.models.logic_models import LogicNodeUpdate
from app.services.persistence.import_pipeline import import_file
from app.services.crud.logic_node_service import get_node, update_node

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/compose", tags=["compose"])


@router.post("/parse", status_code=200, response_model=ComposeParseResponse)
async def compose_parse(data: ComposeParseRequest) -> ComposeParseResponse:
    """Parse source code and import into the graph.

    Reuses the full import pipeline to create/update LogicNodes, Variables,
    and edges from the provided source code.

    Args:
        data: Source code and module path for the compose buffer.

    Returns:
        Parse report with created node and variable IDs.
    """
    try:
        report = import_file(
            file_path=data.module_path,
            source=data.source,
            abs_path=data.module_path,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Parse failed: {exc}") from exc

    # Query graph for nodes with this module_path to get their IDs and names
    graph = get_graph()
    nodes: list[ParsedNodeInfo] = []
    variable_ids: list[str] = []

    try:
        result = graph.query(
            "MATCH (n:LogicNode {module_path: $mp, status: 'active'}) RETURN n.id, n.name",
            params={"mp": data.module_path},
        )
        nodes = [ParsedNodeInfo(id=str(row[0]), name=str(row[1])) for row in result.result_set]
    except Exception:
        pass

    try:
        result = graph.query(
            "MATCH (n:LogicNode {module_path: $mp, status: 'active'})"
            "-[:ASSIGNS|READS|RETURNS]->(v:Variable) RETURN DISTINCT v.id",
            params={"mp": data.module_path},
        )
        variable_ids = [str(row[0]) for row in result.result_set]
    except Exception:
        pass

    # Broadcast graph:updated via WebSocket
    try:
        from app.routers.websocket import broadcast  # pylint: disable=import-outside-toplevel
        asyncio.ensure_future(broadcast("graph:updated", {"affected_modules": [data.module_path]}))
    except Exception:
        pass

    return ComposeParseResponse(
        report=ComposeParseReport(
            nodes_created=report.nodes_created,
            nodes_updated=report.nodes_updated,
            edges_created=report.edges_created,
            variables_created=report.variables_created,
            errors=report.errors,
        ),
        nodes=nodes,
        variable_ids=variable_ids,
    )


@router.post("/save", status_code=200, response_model=ComposeSaveResponse)
async def compose_save(data: ComposeSaveRequest) -> ComposeSaveResponse:
    """Save updated source code for an existing LogicNode.

    Updates the node in the graph, runs impact analysis to find affected
    consumers, and broadcasts update events.

    Args:
        data: Node ID and new source code.

    Returns:
        Updated node and list of impacted nodes.
    """
    try:
        existing = get_node(data.node_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Node not found: {data.node_id}") from exc

    try:
        updated = update_node(data.node_id, LogicNodeUpdate(source_text=data.source))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Update failed: {exc}") from exc

    # Impact analysis: find consumers of mutated variables
    impacted: list[ImpactedNode] = []
    graph = get_graph()

    try:
        result = graph.query(lq.IMPACT_ANALYSIS, params={"node_id": data.node_id})
        for row in result.result_set:
            variable_name = str(row[0]) if row[0] else "unknown"
            consumers = row[2] if len(row) > 2 else []
            if isinstance(consumers, list):
                for consumer in consumers:
                    if isinstance(consumer, dict):
                        impacted.append(ImpactedNode(
                            id=str(consumer.get("id", "")),
                            name=str(consumer.get("name", "")),
                            reason=f"reads mutated variable '{variable_name}'",
                        ))
    except Exception:
        logger.debug("Impact analysis query failed", exc_info=True)

    # Find callers (for signature change detection)
    try:
        result = graph.query(lq.FIND_CALLERS, params={"node_id": data.node_id})
        for row in result.result_set:
            caller_id = str(row[0]) if row[0] else ""
            caller_name = str(row[1]) if len(row) > 1 else ""
            if caller_id and not any(n.id == caller_id for n in impacted):
                impacted.append(ImpactedNode(
                    id=caller_id,
                    name=caller_name,
                    reason="calls this function",
                ))
    except Exception:
        logger.debug("Find callers query failed", exc_info=True)

    # Broadcast events
    try:
        from app.routers.websocket import broadcast  # pylint: disable=import-outside-toplevel
        asyncio.ensure_future(broadcast("graph:updated", {"affected_modules": [existing.module_path]}))
        asyncio.ensure_future(broadcast("node:pulse", {"node_id": data.node_id}))
    except Exception:
        pass

    return ComposeSaveResponse(
        updated_node=updated,
        impacted_nodes=impacted,
    )
