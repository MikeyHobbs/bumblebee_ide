"""Mutation timeline query: traces a variable's full lifecycle through the graph."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.parsing.ast_parser import ParsedNode
from app.services.parsing.variable_extractor import VariableNode, VariableEdge
from app.services.parsing.relationship_extractor import RelationshipEdge
from app.services.parsing.dataflow_extractor import DataFlowEdge


@dataclass
class TimelineEntry:
    """A single entry in a variable's mutation timeline.

    Attributes:
        edge_type: The interaction type (ASSIGNS, MUTATES, READS, PASSES_TO, RETURNS, FEEDS).
        function_name: The function where this interaction occurs.
        variable_name: The variable involved.
        line: Line number of the interaction.
        seq: Execution order within the function.
        properties: Full edge properties.
    """

    edge_type: str
    function_name: str
    variable_name: str
    line: int
    seq: int
    properties: dict[str, str | int | bool | None] = field(default_factory=dict)


@dataclass
class MutationTimeline:
    """Full lifecycle of a variable.

    Attributes:
        variable: The target variable node info.
        origin: The initial assignment details.
        mutations: All MUTATES interactions.
        reads: All READS interactions.
        passes: All PASSES_TO interactions.
        returns: All RETURNS interactions.
        feeds: All FEEDS interactions.
        terminal: The last interaction, if identifiable.
    """

    variable: dict[str, str | int | None]
    origin: TimelineEntry | None
    mutations: list[TimelineEntry]
    reads: list[TimelineEntry]
    passes: list[TimelineEntry]
    returns: list[TimelineEntry]
    feeds: list[TimelineEntry]
    terminal: TimelineEntry | None


def build_timeline_from_extractions(
    target_variable: str,
    variable_nodes: list[VariableNode],
    variable_edges: list[VariableEdge],
    dataflow_edges: list[DataFlowEdge],
) -> MutationTimeline | None:
    """Build a mutation timeline for a variable from extraction results.

    This is the in-memory version that works without a graph database,
    useful for testing and for single-file analysis.

    Args:
        target_variable: Qualified name of the target variable.
        variable_nodes: All variable nodes.
        variable_edges: All variable interaction edges.
        dataflow_edges: All PASSES_TO and FEEDS edges.

    Returns:
        MutationTimeline for the variable, or None if not found.
    """
    var_node = None
    for vn in variable_nodes:
        if vn.name == target_variable:
            var_node = vn
            break

    if var_node is None:
        return None

    # Collect all edges involving this variable (and any it passes to)
    tracked_vars = {target_variable}

    # Follow PASSES_TO chains
    passes_to_edges = [e for e in dataflow_edges if e.edge_type == "PASSES_TO"]
    changed = True
    while changed:
        changed = False
        for edge in passes_to_edges:
            if edge.source_name in tracked_vars and edge.target_name not in tracked_vars:
                tracked_vars.add(edge.target_name)
                changed = True

    # Collect timeline entries
    origin: TimelineEntry | None = None
    mutations: list[TimelineEntry] = []
    reads: list[TimelineEntry] = []
    returns: list[TimelineEntry] = []
    passes: list[TimelineEntry] = []
    feeds: list[TimelineEntry] = []

    for edge in variable_edges:
        if edge.target_name not in tracked_vars:
            continue

        entry = TimelineEntry(
            edge_type=edge.edge_type,
            function_name=edge.source_name,
            variable_name=edge.target_name,
            line=int(edge.properties.get("line", 0) or 0),
            seq=int(edge.properties.get("seq", 0) or 0),
            properties=dict(edge.properties),
        )

        if edge.edge_type == "ASSIGNS":
            if origin is None or (not edge.properties.get("is_rebind")):
                if origin is None:
                    origin = entry
            mutations.append(entry)  # Include assigns in the full timeline
        elif edge.edge_type == "MUTATES":
            mutations.append(entry)
        elif edge.edge_type == "READS":
            reads.append(entry)
        elif edge.edge_type == "RETURNS":
            returns.append(entry)

    for edge in dataflow_edges:
        if edge.source_name in tracked_vars or edge.target_name in tracked_vars:
            entry = TimelineEntry(
                edge_type=edge.edge_type,
                function_name="",
                variable_name=edge.target_name if edge.edge_type == "FEEDS" else edge.source_name,
                line=int(edge.properties.get("line", 0) or 0) if "line" in edge.properties else 0,
                seq=int(edge.properties.get("seq", 0) or 0),
                properties=dict(edge.properties),
            )

            if edge.edge_type == "PASSES_TO":
                passes.append(entry)
            elif edge.edge_type == "FEEDS":
                feeds.append(entry)

    # Sort by seq within each category
    mutations.sort(key=lambda e: (e.function_name, e.seq))
    reads.sort(key=lambda e: (e.function_name, e.seq))
    returns.sort(key=lambda e: (e.function_name, e.seq))
    passes.sort(key=lambda e: e.seq)
    feeds.sort(key=lambda e: e.seq)

    # Terminal: last interaction
    all_entries = mutations + reads + returns
    terminal = max(all_entries, key=lambda e: (e.function_name, e.seq)) if all_entries else None

    return MutationTimeline(
        variable={
            "name": var_node.name,
            "scope": var_node.scope,
            "origin_line": var_node.origin_line,
            "origin_func": var_node.origin_func,
            "type_hint": var_node.type_hint,
        },
        origin=origin,
        mutations=mutations,
        reads=reads,
        passes=passes,
        returns=returns,
        feeds=feeds,
        terminal=terminal,
    )


def search_variables(
    query_name: str,
    variable_nodes: list[VariableNode],
    scope: str | None = None,
) -> list[VariableNode]:
    """Search for variables by name, optionally filtered by scope.

    Args:
        query_name: Variable name to search for (partial match).
        variable_nodes: All variable nodes.
        scope: Optional scope filter.

    Returns:
        List of matching VariableNode instances.
    """
    results = []
    for var in variable_nodes:
        short_name = var.name.rsplit(".", 1)[-1]
        if query_name in short_name or query_name in var.name:
            if scope is None or scope in var.scope:
                results.append(var)
    return results
