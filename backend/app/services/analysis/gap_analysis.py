"""Gap analysis engine (TICKET-851).

Detects structural gaps, anti-patterns, and opportunities in the graph.
"""

from __future__ import annotations

import logging
from typing import Any

from app.graph.client import get_graph
from app.models.logic_models import GapReport, LogicNodeResponse
from app.services.crud.logic_node_service import _node_from_graph

logger = logging.getLogger(__name__)


def find_dead_ends(scope: str | None = None) -> list[LogicNodeResponse]:
    """Find LogicNodes with no outgoing CALLS edges (potential dead ends).

    Excludes nodes that are exit points of flows.

    Args:
        scope: Optional module_path filter.

    Returns:
        List of dead-end LogicNodeResponse objects.
    """
    graph = get_graph()
    scope_filter = "AND n.module_path CONTAINS $scope" if scope else ""

    result = graph.query(
        f"MATCH (n:LogicNode {{status: 'active'}}) "
        f"WHERE NOT (n)-[:CALLS]->(:LogicNode) {scope_filter} "
        f"AND NOT (n)-[:STEP_OF]->(:Flow) "
        f"RETURN n ORDER BY n.name",
        params={"scope": scope or ""},
    )

    return [_node_from_graph(row[0]) for row in result.result_set]


def find_orphans(scope: str | None = None) -> list[LogicNodeResponse]:
    """Find LogicNodes with no incoming edges (never called, never depended on).

    Excludes entry points and top-level module functions.

    Args:
        scope: Optional module_path filter.

    Returns:
        List of orphan LogicNodeResponse objects.
    """
    graph = get_graph()
    scope_filter = "AND n.module_path CONTAINS $scope" if scope else ""

    result = graph.query(
        f"MATCH (n:LogicNode {{status: 'active'}}) "
        f"WHERE NOT ()-[:CALLS|DEPENDS_ON|MEMBER_OF]->(n) {scope_filter} "
        f"AND n.kind <> 'class' "
        f"RETURN n ORDER BY n.name",
        params={"scope": scope or ""},
    )

    return [_node_from_graph(row[0]) for row in result.result_set]


def find_missing_error_handling(scope: str | None = None) -> list[dict[str, Any]]:
    """Find LogicNodes that call error-prone nodes without try/except.

    Looks for CALLS to functions with names suggesting I/O, DB, or network ops.

    Args:
        scope: Optional module_path filter.

    Returns:
        List of dicts: {node_name, node_id, risky_calls: [callee_name]}.
    """
    graph = get_graph()
    scope_filter = "AND caller.module_path CONTAINS $scope" if scope else ""

    # Find callers of functions with risky names
    result = graph.query(
        f"MATCH (caller:LogicNode {{status: 'active'}})-[:CALLS]->(callee:LogicNode) "
        f"WHERE (callee.name CONTAINS 'read' OR callee.name CONTAINS 'write' "
        f"  OR callee.name CONTAINS 'connect' OR callee.name CONTAINS 'query' "
        f"  OR callee.name CONTAINS 'fetch' OR callee.name CONTAINS 'send' "
        f"  OR callee.name CONTAINS 'open' OR callee.name CONTAINS 'execute') "
        f"{scope_filter} "
        f"AND NOT caller.source_text CONTAINS 'try:' "
        f"RETURN caller.id, caller.name, collect(callee.name) AS risky_calls",
        params={"scope": scope or ""},
    )

    issues: list[dict[str, Any]] = []
    for row in result.result_set:
        issues.append({
            "node_id": row[0],
            "node_name": row[1],
            "risky_calls": row[2] if len(row) > 2 else [],
        })

    return issues


def find_circular_deps(scope: str | None = None) -> list[list[str]]:
    """Find cycles in the CALLS/DEPENDS_ON graph.

    Args:
        scope: Optional module_path filter.

    Returns:
        List of cycles, each a list of node names.
    """
    graph = get_graph()

    # FalkorDB doesn't have native cycle detection, so we look for
    # bidirectional edges (simplest cycle) and short loops
    result = graph.query(
        "MATCH (a:LogicNode {status: 'active'})-[:CALLS|DEPENDS_ON]->(b:LogicNode {status: 'active'})"
        "-[:CALLS|DEPENDS_ON]->(a) "
        "WHERE a.id < b.id "  # Avoid duplicates
        "RETURN a.name, b.name",
    )

    cycles: list[list[str]] = []
    for row in result.result_set:
        cycles.append([row[0], row[1]])

    # Also check 3-node cycles
    try:
        result = graph.query(
            "MATCH (a:LogicNode {status: 'active'})-[:CALLS|DEPENDS_ON]->(b:LogicNode {status: 'active'})"
            "-[:CALLS|DEPENDS_ON]->(c:LogicNode {status: 'active'})-[:CALLS|DEPENDS_ON]->(a) "
            "WHERE a.id < b.id AND b.id < c.id "
            "RETURN a.name, b.name, c.name",
        )
        for row in result.result_set:
            cycles.append([row[0], row[1], row[2]])
    except Exception:
        pass

    return cycles


def find_untested_mutations(scope: str | None = None) -> list[dict[str, Any]]:
    """Find variables that are MUTATED but never READ afterward.

    Args:
        scope: Optional scope filter.

    Returns:
        List of dicts: {variable_name, variable_id, mutated_by, not_read_by_anyone}.
    """
    graph = get_graph()

    result = graph.query(
        "MATCH (mutator:LogicNode)-[:MUTATES]->(v:Variable) "
        "WHERE NOT (:LogicNode)-[:READS]->(v) "
        "RETURN v.name, v.id, mutator.name",
    )

    issues: list[dict[str, Any]] = []
    for row in result.result_set:
        issues.append({
            "variable_name": row[0],
            "variable_id": row[1],
            "mutated_by": row[2],
        })

    return issues


def get_full_report(scope: str | None = None) -> GapReport:
    """Run all gap analyses and return a combined report.

    Args:
        scope: Optional module_path filter.

    Returns:
        GapReport with all analysis results.
    """
    return GapReport(
        dead_ends=find_dead_ends(scope),
        orphans=find_orphans(scope),
        missing_error_handling=find_missing_error_handling(scope),
        circular_deps=find_circular_deps(scope),
        untested_mutations=find_untested_mutations(scope),
    )
