"""Router for Logic Pack retrieval endpoints."""

from __future__ import annotations

import logging

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query

from app.graph.client import get_graph
from app.graph.logic_pack import (
    build_call_chain_pack,
    build_class_hierarchy_pack,
    build_function_flow_pack,
    build_impact_pack,
    build_mutation_timeline_pack,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["logic-pack"])


class LogicPackNode(BaseModel):
    """A node in a Logic Pack subgraph."""

    id: str
    label: str
    properties: dict[str, str | int | bool | None]


class LogicPackEdge(BaseModel):
    """An edge in a Logic Pack subgraph."""

    type: str
    source: str
    target: str
    properties: dict[str, str | int | bool | None]


class LogicPackResponse(BaseModel):
    """A Logic Pack: a pre-processed subgraph for LLM consumption."""

    nodes: list[LogicPackNode]
    edges: list[LogicPackEdge]
    snippets: dict[str, str]


@router.get("/logic-pack/{node_id}", response_model=LogicPackResponse)
async def get_logic_pack(
    node_id: str,
    type: str = Query("call_chain", description="Pack type: call_chain, mutation_timeline, impact, class_hierarchy, function_flow"),
    hops: int = Query(2, description="Traversal depth"),
) -> LogicPackResponse:
    """Get a Logic Pack subgraph centered on a node.

    Args:
        node_id: Qualified name of the center node.
        type: Type of Logic Pack to build.
        hops: Traversal depth for call_chain packs.

    Returns:
        LogicPackResponse with nodes, edges, and code snippets.
    """
    try:
        if type == "call_chain":
            pack = build_call_chain_pack(node_id, hops)
        elif type == "mutation_timeline":
            pack = build_mutation_timeline_pack(node_id)
        elif type == "impact":
            pack = build_impact_pack(node_id)
        elif type == "class_hierarchy":
            pack = build_class_hierarchy_pack(node_id)
        elif type == "function_flow":
            pack = build_function_flow_pack(node_id)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown pack type: {type}")

        return LogicPackResponse(
            nodes=[LogicPackNode(**n) for n in pack["nodes"]],
            edges=[LogicPackEdge(**e) for e in pack["edges"]],
            snippets=pack["snippets"],
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Logic pack query failed for %s", node_id)
        raise HTTPException(status_code=500, detail=f"Logic pack query failed: {exc}") from exc
