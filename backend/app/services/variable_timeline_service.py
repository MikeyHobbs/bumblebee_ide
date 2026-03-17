"""Variable timeline service (TICKET-812).

Implements the mutation timeline query and variable tracing — Bumblebee's
killer feature.
"""

from __future__ import annotations

from typing import Any

from app.graph.client import get_graph
from app.graph import logic_queries as lq
from app.models.exceptions import NodeNotFoundError
from app.models.logic_models import (
    EdgeResponse,
    EdgeType,
    LogicNodeResponse,
    MutationTimeline,
    VariableResponse,
)
from app.services.logic_node_service import _node_from_graph, _parse_datetime


def _variable_from_graph(record: Any) -> VariableResponse:
    """Convert a FalkorDB Variable node to a VariableResponse.

    Args:
        record: A FalkorDB node result.

    Returns:
        VariableResponse.
    """
    props = record.properties if hasattr(record, "properties") else record

    return VariableResponse(
        id=props.get("id", ""),
        name=props.get("name", ""),
        scope=props.get("scope", ""),
        origin_node_id=props.get("origin_node_id", ""),
        origin_line=props.get("origin_line"),
        type_hint=props.get("type_hint") or None,
        is_parameter=bool(props.get("is_parameter", False)),
        is_attribute=bool(props.get("is_attribute", False)),
        created_at=_parse_datetime(props.get("created_at", "")),
    )


def get_variable(variable_id: str) -> VariableResponse:
    """Fetch a Variable by UUID.

    Args:
        variable_id: The UUID of the Variable.

    Returns:
        VariableResponse.

    Raises:
        NodeNotFoundError: If no variable with the given ID exists.
    """
    graph = get_graph()
    result = graph.query(lq.GET_VARIABLE_BY_ID, params={"id": variable_id})

    if not result.result_set:
        raise NodeNotFoundError(variable_id)

    return _variable_from_graph(result.result_set[0][0])


def get_variable_timeline(variable_id: str) -> MutationTimeline:
    """Get the full mutation timeline for a variable.

    Executes the mutation timeline Cypher query from schema.md Section 6.1.
    Returns the complete lifecycle: origin → mutations → reads → passes → feeds.

    Args:
        variable_id: UUID of the Variable to trace.

    Returns:
        MutationTimeline with all edges and endpoint nodes.

    Raises:
        NodeNotFoundError: If the variable doesn't exist.
    """
    variable = get_variable(variable_id)

    graph = get_graph()
    result = graph.query(lq.MUTATION_TIMELINE, params={"variable_id": variable_id})

    timeline = MutationTimeline(variable=variable)

    if not result.result_set:
        return timeline

    for row in result.result_set:
        # Row structure matches MUTATION_TIMELINE query RETURN clause:
        # v, origin, a, mutator, m, reader, r, returner, ret,
        # downstream, p, upstream, p2, feeder, f, fed, f2

        # Origin (ASSIGNS with is_rebind=false)
        origin_node = row[1] if len(row) > 1 and row[1] else None
        assigns_edge = row[2] if len(row) > 2 and row[2] else None
        if origin_node and assigns_edge:
            timeline.origin = _node_from_graph(origin_node)
            timeline.assigns.append(EdgeResponse(
                type=EdgeType.ASSIGNS,
                source=_get_node_id(origin_node),
                target=variable_id,
                properties=_edge_props(assigns_edge),
            ))

        # Mutations
        mutator_node = row[3] if len(row) > 3 and row[3] else None
        mutates_edge = row[4] if len(row) > 4 and row[4] else None
        if mutator_node and mutates_edge:
            timeline.mutations.append(EdgeResponse(
                type=EdgeType.MUTATES,
                source=_get_node_id(mutator_node),
                target=variable_id,
                properties=_edge_props(mutates_edge),
            ))

        # Reads
        reader_node = row[5] if len(row) > 5 and row[5] else None
        reads_edge = row[6] if len(row) > 6 and row[6] else None
        if reader_node and reads_edge:
            timeline.reads.append(EdgeResponse(
                type=EdgeType.READS,
                source=_get_node_id(reader_node),
                target=variable_id,
                properties=_edge_props(reads_edge),
            ))

        # Returns
        returner_node = row[7] if len(row) > 7 and row[7] else None
        returns_edge = row[8] if len(row) > 8 and row[8] else None
        if returner_node and returns_edge:
            timeline.returns.append(EdgeResponse(
                type=EdgeType.RETURNS,
                source=_get_node_id(returner_node),
                target=variable_id,
                properties=_edge_props(returns_edge),
            ))

        # PASSES_TO (outgoing: this variable passes to downstream)
        downstream_var = row[9] if len(row) > 9 and row[9] else None
        passes_edge = row[10] if len(row) > 10 and row[10] else None
        if downstream_var and passes_edge:
            timeline.passes.append(EdgeResponse(
                type=EdgeType.PASSES_TO,
                source=variable_id,
                target=_get_node_id(downstream_var),
                properties=_edge_props(passes_edge),
            ))

        # PASSES_TO (incoming: upstream passes to this variable)
        upstream_var = row[11] if len(row) > 11 and row[11] else None
        passes_in_edge = row[12] if len(row) > 12 and row[12] else None
        if upstream_var and passes_in_edge:
            timeline.passes.append(EdgeResponse(
                type=EdgeType.PASSES_TO,
                source=_get_node_id(upstream_var),
                target=variable_id,
                properties=_edge_props(passes_in_edge),
            ))

        # FEEDS (incoming)
        feeder_var = row[13] if len(row) > 13 and row[13] else None
        feeds_edge = row[14] if len(row) > 14 and row[14] else None
        if feeder_var and feeds_edge:
            timeline.feeds.append(EdgeResponse(
                type=EdgeType.FEEDS,
                source=_get_node_id(feeder_var),
                target=variable_id,
                properties=_edge_props(feeds_edge),
            ))

        # FEEDS (outgoing)
        fed_var = row[15] if len(row) > 15 and row[15] else None
        feeds_out_edge = row[16] if len(row) > 16 and row[16] else None
        if fed_var and feeds_out_edge:
            timeline.feeds.append(EdgeResponse(
                type=EdgeType.FEEDS,
                source=variable_id,
                target=_get_node_id(fed_var),
                properties=_edge_props(feeds_out_edge),
            ))

    # Determine terminal: last reader or last consumer with no outgoing
    if timeline.reads:
        last_read = timeline.reads[-1]
        try:
            terminal = _node_from_graph_by_id(last_read.source)
            timeline.terminal = terminal
        except Exception:  # pylint: disable=broad-except
            pass

    return timeline


def trace_variable(name: str, scope: str | None = None) -> list[MutationTimeline]:
    """Find variables by name and return mutation timelines for each.

    Args:
        name: Variable name to search for (partial match).
        scope: Optional scope filter (partial match).

    Returns:
        List of MutationTimeline objects, one per matching variable.
    """
    graph = get_graph()
    result = graph.query(
        lq.SEARCH_VARIABLES_BY_NAME,
        params={"name": name, "scope": scope or "", "limit": 50},
    )

    timelines: list[MutationTimeline] = []
    for row in result.result_set:
        var_resp = _variable_from_graph(row[0])
        try:
            timeline = get_variable_timeline(var_resp.id)
            timelines.append(timeline)
        except Exception:  # pylint: disable=broad-except
            # Variable may have been cleaned up
            timelines.append(MutationTimeline(variable=var_resp))

    return timelines


def get_impact(node_id: str) -> list[dict[str, Any]]:
    """Impact analysis: for a LogicNode, find all variables it mutates and their consumers.

    Args:
        node_id: UUID of the LogicNode.

    Returns:
        List of dicts: {variable: str, variable_id: str, affected_consumers: [{id, name}]}.
    """
    graph = get_graph()
    result = graph.query(lq.IMPACT_ANALYSIS, params={"node_id": node_id})

    impacts: list[dict[str, Any]] = []
    for row in result.result_set:
        variable_name = row[0] if row else ""
        variable_id = row[1] if len(row) > 1 else ""
        consumers = row[2] if len(row) > 2 and isinstance(row[2], list) else []

        impacts.append({
            "variable": variable_name,
            "variable_id": variable_id,
            "affected_consumers": consumers,
        })

    return impacts


def _get_node_id(record: Any) -> str:
    """Extract the id property from a graph record."""
    if hasattr(record, "properties"):
        return str(record.properties.get("id", ""))
    if isinstance(record, dict):
        return str(record.get("id", ""))
    return ""


def _edge_props(record: Any) -> dict[str, Any]:
    """Extract properties from an edge record."""
    if hasattr(record, "properties"):
        return dict(record.properties)
    if isinstance(record, dict):
        return dict(record)
    return {}


def _node_from_graph_by_id(node_id: str) -> LogicNodeResponse:
    """Fetch a LogicNode by ID for timeline terminal detection."""
    from app.services.logic_node_service import get_node  # pylint: disable=import-outside-toplevel

    return get_node(node_id)
