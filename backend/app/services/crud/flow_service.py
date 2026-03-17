"""Flow service with hierarchy and promotion (TICKET-850).

CRUD operations for Flows, sub-flow management, flow promotion to LogicNodes,
and auto-discovery.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.graph.client import get_graph
from app.graph import logic_queries as lq
from app.models.exceptions import NodeNotFoundError
from app.models.logic_models import (
    FlowCreate,
    FlowHierarchy,
    FlowResponse,
    FlowUpdate,
    LogicNodeCreate,
    LogicNodeKind,
    LogicNodeResponse,
)
from app.services.analysis.hash_identity import generate_node_id

logger = logging.getLogger(__name__)


def _flow_from_graph(record: Any) -> FlowResponse:
    """Convert a FalkorDB Flow node to a FlowResponse."""
    props = record.properties if hasattr(record, "properties") else record

    def _parse_list(val: Any) -> list[str]:
        if isinstance(val, list):
            return val
        if isinstance(val, str) and val:
            try:
                parsed = json.loads(val)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    def _parse_dt(val: Any) -> datetime:
        if isinstance(val, datetime):
            return val
        if isinstance(val, str) and val:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        return datetime.now(timezone.utc)

    return FlowResponse(
        id=props.get("id", ""),
        name=props.get("name", ""),
        description=props.get("description") or None,
        entry_point=props.get("entry_point", ""),
        exit_points=_parse_list(props.get("exit_points")),
        node_ids=_parse_list(props.get("node_ids")),
        sub_flow_ids=_parse_list(props.get("sub_flow_ids")),
        parent_flow_id=props.get("parent_flow_id") or None,
        promoted_node_id=props.get("promoted_node_id") or None,
        created_at=_parse_dt(props.get("created_at")),
        updated_at=_parse_dt(props.get("updated_at")),
    )


def create_flow(data: FlowCreate) -> FlowResponse:
    """Create a new Flow in the graph with STEP_OF edges.

    Args:
        data: Flow creation parameters.

    Returns:
        Created FlowResponse.
    """
    graph = get_graph()
    now = datetime.now(timezone.utc).isoformat()
    flow_id = generate_node_id()

    graph.query(
        lq.MERGE_FLOW,
        params={
            "id": flow_id,
            "name": data.name,
            "description": data.description or "",
            "entry_point": data.entry_point,
            "exit_points": json.dumps(data.exit_points),
            "node_ids": json.dumps(data.node_ids),
            "sub_flow_ids": json.dumps(data.sub_flow_ids),
            "parent_flow_id": data.parent_flow_id or "",
            "promoted_node_id": "",
            "created_at": now,
            "updated_at": now,
        },
    )

    # Create STEP_OF edges
    for order, node_id in enumerate(data.node_ids):
        try:
            graph.query(
                lq.EDGE_MERGE_QUERIES["STEP_OF"],
                params={
                    "source_id": node_id,
                    "target_id": flow_id,
                    "properties": {"step_order": order},
                },
            )
        except Exception:
            pass

    # Create CONTAINS_FLOW edges for sub-flows
    for order, sub_id in enumerate(data.sub_flow_ids):
        try:
            graph.query(
                lq.EDGE_MERGE_QUERIES["CONTAINS_FLOW"],
                params={
                    "source_id": flow_id,
                    "target_id": sub_id,
                    "properties": {"step_order": order},
                },
            )
        except Exception:
            pass

    # Set parent_flow_id on parent if specified
    if data.parent_flow_id:
        try:
            graph.query(
                lq.EDGE_MERGE_QUERIES["CONTAINS_FLOW"],
                params={
                    "source_id": data.parent_flow_id,
                    "target_id": flow_id,
                    "properties": {"step_order": 0},
                },
            )
        except Exception:
            pass

    return get_flow(flow_id)


def get_flow(flow_id: str) -> FlowResponse:
    """Fetch a Flow by UUID.

    Args:
        flow_id: The UUID of the Flow.

    Returns:
        FlowResponse.

    Raises:
        NodeNotFoundError: If no flow with the given ID exists.
    """
    graph = get_graph()
    result = graph.query(lq.GET_FLOW_BY_ID, params={"id": flow_id})

    if not result.result_set:
        raise NodeNotFoundError(flow_id)

    return _flow_from_graph(result.result_set[0][0])


def list_flows() -> list[FlowResponse]:
    """List all flows.

    Returns:
        List of FlowResponse objects.
    """
    graph = get_graph()
    result = graph.query(lq.GET_ALL_FLOWS)
    return [_flow_from_graph(row[0]) for row in result.result_set]


def update_flow(flow_id: str, data: FlowUpdate) -> FlowResponse:
    """Update a Flow.

    Args:
        flow_id: UUID of the Flow.
        data: Fields to update.

    Returns:
        Updated FlowResponse.
    """
    existing = get_flow(flow_id)
    graph = get_graph()
    now = datetime.now(timezone.utc).isoformat()

    name = data.name if data.name is not None else existing.name
    description = data.description if data.description is not None else existing.description
    node_ids = data.node_ids if data.node_ids is not None else existing.node_ids
    entry_point = data.entry_point if data.entry_point is not None else existing.entry_point
    exit_points = data.exit_points if data.exit_points is not None else existing.exit_points

    graph.query(
        lq.MERGE_FLOW,
        params={
            "id": flow_id,
            "name": name,
            "description": description or "",
            "entry_point": entry_point,
            "exit_points": json.dumps(exit_points),
            "node_ids": json.dumps(node_ids),
            "sub_flow_ids": json.dumps(existing.sub_flow_ids),
            "parent_flow_id": existing.parent_flow_id or "",
            "promoted_node_id": existing.promoted_node_id or "",
            "created_at": existing.created_at.isoformat(),
            "updated_at": now,
        },
    )

    # Rebuild STEP_OF edges if node_ids changed
    if data.node_ids is not None:
        # Remove old STEP_OF edges
        try:
            graph.query(
                "MATCH (n:LogicNode)-[r:STEP_OF]->(f:Flow {id: $flow_id}) DELETE r",
                params={"flow_id": flow_id},
            )
        except Exception:
            pass

        for order, nid in enumerate(node_ids):
            try:
                graph.query(
                    lq.EDGE_MERGE_QUERIES["STEP_OF"],
                    params={
                        "source_id": nid,
                        "target_id": flow_id,
                        "properties": {"step_order": order},
                    },
                )
            except Exception:
                pass

    return get_flow(flow_id)


def delete_flow(flow_id: str) -> None:
    """Delete a Flow and its STEP_OF/CONTAINS_FLOW edges.

    Args:
        flow_id: UUID of the Flow.
    """
    get_flow(flow_id)  # Verify exists
    graph = get_graph()
    graph.query(lq.DELETE_FLOW, params={"id": flow_id})


def add_sub_flow(parent_flow_id: str, child_flow_id: str, step_order: int = 0) -> FlowResponse:
    """Add a sub-flow to a parent flow.

    Args:
        parent_flow_id: UUID of the parent flow.
        child_flow_id: UUID of the child flow.
        step_order: Position of the sub-flow in the parent.

    Returns:
        Updated parent FlowResponse.
    """
    parent = get_flow(parent_flow_id)
    get_flow(child_flow_id)  # Verify child exists

    graph = get_graph()
    now = datetime.now(timezone.utc).isoformat()

    # Add to sub_flow_ids
    sub_ids = list(parent.sub_flow_ids)
    if child_flow_id not in sub_ids:
        sub_ids.append(child_flow_id)

    graph.query(
        lq.MERGE_FLOW,
        params={
            "id": parent_flow_id,
            "name": parent.name,
            "description": parent.description or "",
            "entry_point": parent.entry_point,
            "exit_points": json.dumps(parent.exit_points),
            "node_ids": json.dumps(parent.node_ids),
            "sub_flow_ids": json.dumps(sub_ids),
            "parent_flow_id": parent.parent_flow_id or "",
            "promoted_node_id": parent.promoted_node_id or "",
            "created_at": parent.created_at.isoformat(),
            "updated_at": now,
        },
    )

    # Create CONTAINS_FLOW edge
    graph.query(
        lq.EDGE_MERGE_QUERIES["CONTAINS_FLOW"],
        params={
            "source_id": parent_flow_id,
            "target_id": child_flow_id,
            "properties": {"step_order": step_order},
        },
    )

    # Update child's parent_flow_id
    child = get_flow(child_flow_id)
    graph.query(
        lq.MERGE_FLOW,
        params={
            "id": child_flow_id,
            "name": child.name,
            "description": child.description or "",
            "entry_point": child.entry_point,
            "exit_points": json.dumps(child.exit_points),
            "node_ids": json.dumps(child.node_ids),
            "sub_flow_ids": json.dumps(child.sub_flow_ids),
            "parent_flow_id": parent_flow_id,
            "promoted_node_id": child.promoted_node_id or "",
            "created_at": child.created_at.isoformat(),
            "updated_at": now,
        },
    )

    return get_flow(parent_flow_id)


def remove_sub_flow(parent_flow_id: str, child_flow_id: str) -> FlowResponse:
    """Remove a sub-flow from a parent flow.

    Args:
        parent_flow_id: UUID of the parent flow.
        child_flow_id: UUID of the child flow.

    Returns:
        Updated parent FlowResponse.
    """
    parent = get_flow(parent_flow_id)
    graph = get_graph()
    now = datetime.now(timezone.utc).isoformat()

    sub_ids = [sid for sid in parent.sub_flow_ids if sid != child_flow_id]

    graph.query(
        lq.MERGE_FLOW,
        params={
            "id": parent_flow_id,
            "name": parent.name,
            "description": parent.description or "",
            "entry_point": parent.entry_point,
            "exit_points": json.dumps(parent.exit_points),
            "node_ids": json.dumps(parent.node_ids),
            "sub_flow_ids": json.dumps(sub_ids),
            "parent_flow_id": parent.parent_flow_id or "",
            "promoted_node_id": parent.promoted_node_id or "",
            "created_at": parent.created_at.isoformat(),
            "updated_at": now,
        },
    )

    # Remove CONTAINS_FLOW edge
    try:
        graph.query(
            "MATCH (p:Flow {id: $parent_id})-[r:CONTAINS_FLOW]->(c:Flow {id: $child_id}) DELETE r",
            params={"parent_id": parent_flow_id, "child_id": child_flow_id},
        )
    except Exception:
        pass

    return get_flow(parent_flow_id)


def promote_flow_to_node(flow_id: str) -> LogicNodeResponse:
    """Promote a Flow to a callable LogicNode (flow_function).

    Creates a LogicNode whose source_text calls all constituent LogicNodes
    in order. Creates CALLS edges from the new node to each step.

    Args:
        flow_id: UUID of the Flow to promote.

    Returns:
        The created LogicNodeResponse.
    """
    from app.services.crud.logic_node_service import create_node  # pylint: disable=import-outside-toplevel

    flow = get_flow(flow_id)
    graph = get_graph()
    now = datetime.now(timezone.utc).isoformat()

    # Build source text that calls all steps
    func_name = flow.name.replace("-", "_").replace(" ", "_")
    step_calls: list[str] = []

    for node_id in flow.node_ids:
        try:
            result = graph.query(lq.GET_LOGIC_NODE_BY_ID, params={"id": node_id})
            if result.result_set:
                props = result.result_set[0][0].properties
                short_name = props.get("name", "").rsplit(".", 1)[-1]
                step_calls.append(f"    {short_name}()")
        except Exception:
            step_calls.append(f"    # step {node_id}")

    source = f"def {func_name}():\n"
    if flow.description:
        source += f'    """{flow.description}"""\n'
    source += "\n".join(step_calls) if step_calls else "    pass"

    node_data = LogicNodeCreate(
        name=func_name,
        kind=LogicNodeKind.FLOW_FUNCTION,
        source_text=source,
        module_path="",
        semantic_intent=flow.description,
        tags=["flow", "auto-promoted"],
    )

    node_resp = create_node(node_data)

    # Create CALLS edges to each step
    for node_id in flow.node_ids:
        try:
            graph.query(
                lq.EDGE_MERGE_QUERIES["CALLS"],
                params={
                    "source_id": node_resp.id,
                    "target_id": node_id,
                    "properties": {},
                },
            )
        except Exception:
            pass

    # Update flow with promoted_node_id
    graph.query(
        lq.MERGE_FLOW,
        params={
            "id": flow_id,
            "name": flow.name,
            "description": flow.description or "",
            "entry_point": flow.entry_point,
            "exit_points": json.dumps(flow.exit_points),
            "node_ids": json.dumps(flow.node_ids),
            "sub_flow_ids": json.dumps(flow.sub_flow_ids),
            "parent_flow_id": flow.parent_flow_id or "",
            "promoted_node_id": node_resp.id,
            "created_at": flow.created_at.isoformat(),
            "updated_at": now,
        },
    )

    # Create PROMOTED_TO edge
    graph.query(
        lq.EDGE_MERGE_QUERIES["PROMOTED_TO"],
        params={"source_id": flow_id, "target_id": node_resp.id},
    )

    return node_resp


def get_flow_hierarchy(flow_id: str) -> FlowHierarchy:
    """Get the full flow hierarchy (recursive).

    Args:
        flow_id: UUID of the root flow.

    Returns:
        FlowHierarchy tree.
    """
    root = get_flow(flow_id)

    def _build(flow: FlowResponse, depth: int) -> FlowHierarchy:
        children: list[FlowHierarchy] = []
        for sub_id in flow.sub_flow_ids:
            try:
                sub = get_flow(sub_id)
                children.append(_build(sub, depth + 1))
            except NodeNotFoundError:
                pass
        return FlowHierarchy(flow=flow, children=children, depth=depth)

    return _build(root, 0)


def discover_flows(entry_node_id: str, max_depth: int = 10) -> list[dict[str, Any]]:
    """Auto-discover flow patterns starting from an entry point.

    Follows CALLS edges to find linear and branching paths.

    Args:
        entry_node_id: UUID of the entry LogicNode.
        max_depth: Maximum call depth to explore.

    Returns:
        List of suggested flow dicts: {name, node_ids, entry_point, exit_points}.
    """
    graph = get_graph()
    suggestions: list[dict[str, Any]] = []

    try:
        result = graph.query(
            "MATCH path = (entry:LogicNode {id: $entry_id})-[:CALLS*1..$depth]->(n:LogicNode) "
            "WHERE n.status = 'active' "
            "RETURN [node IN nodes(path) | node.id] AS node_ids, "
            "       [node IN nodes(path) | node.name] AS node_names",
            params={"entry_id": entry_node_id, "depth": max_depth},
        )

        # Group unique paths
        seen: set[str] = set()
        for row in result.result_set:
            node_ids = row[0] if row else []
            node_names = row[1] if len(row) > 1 else []
            path_key = "->".join(node_ids)
            if path_key in seen:
                continue
            seen.add(path_key)

            if len(node_ids) >= 2:
                entry_name = node_names[0].rsplit(".", 1)[-1] if node_names else "unknown"
                suggestions.append({
                    "name": f"flow_{entry_name}",
                    "node_ids": node_ids,
                    "entry_point": node_ids[0],
                    "exit_points": [node_ids[-1]],
                    "node_names": node_names,
                })
    except Exception as exc:
        logger.error("Flow discovery error: %s", exc)

    return suggestions
