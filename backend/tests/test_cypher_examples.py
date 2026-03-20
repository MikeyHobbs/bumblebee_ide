"""Tests that every Cypher example in the schema description returns results.

Runs each few-shot example against the live FalkorDB graph to verify
the prompts teach the LLM correct query patterns. Requires FalkorDB
running with sample_app imported.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from app.graph.client import get_graph, init_client
from app.graph.schema_description import FEW_SHOT_EXAMPLES, CYPHER_SYSTEM_PROMPT


def _extract_cypher_blocks(text: str) -> list[tuple[str, str]]:
    """Extract (label, cypher) pairs from the few-shot examples text.

    Each example has a line like '1. "question"' followed by indented Cypher.
    """
    blocks: list[tuple[str, str]] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        # Match numbered example header: '1. "What does register_user call?"'
        header_match = re.match(r'^\d+\.\s+"(.+)"', lines[i].strip())
        if header_match:
            label = header_match.group(1)
            cypher_lines: list[str] = []
            i += 1
            # Collect indented lines as cypher
            while i < len(lines) and (lines[i].startswith("   ") or lines[i].strip() == ""):
                stripped = lines[i].strip()
                if stripped:
                    cypher_lines.append(stripped)
                i += 1
            if cypher_lines:
                blocks.append((label, " ".join(cypher_lines)))
        else:
            i += 1
    return blocks


@pytest.fixture(scope="module", autouse=True)
def _init_graph():
    """Initialize the FalkorDB client for the test module."""
    try:
        init_client()
        g = get_graph()
        # Quick check that the graph has data
        result = g.query("MATCH (n:LogicNode) RETURN count(n)")
        count = result.result_set[0][0] if result.result_set else 0
        if count == 0:
            pytest.skip("FalkorDB graph is empty — import sample_app first")
    except Exception as exc:
        pytest.skip(f"FalkorDB not available: {exc}")


class TestFewShotExamples:
    """Verify that each few-shot Cypher example returns non-empty results."""

    @pytest.fixture(autouse=True)
    def _graph(self) -> None:
        self.graph = get_graph()

    @pytest.mark.parametrize(
        "label,cypher",
        _extract_cypher_blocks(FEW_SHOT_EXAMPLES),
        ids=[b[0][:50] for b in _extract_cypher_blocks(FEW_SHOT_EXAMPLES)],
    )
    def test_example_returns_results(self, label: str, cypher: str) -> None:
        """Each few-shot example should return at least one row."""
        result = self.graph.query(cypher)
        assert len(result.result_set) > 0, (
            f"Example '{label}' returned 0 rows.\nCypher: {cypher}"
        )


class TestCommonNlPatterns:
    """Test Cypher patterns for common NL questions against live data."""

    @pytest.fixture(autouse=True)
    def _graph(self) -> None:
        self.graph = get_graph()

    def test_what_does_x_call(self) -> None:
        """'What does register_user call?' pattern."""
        result = self.graph.query(
            "MATCH (f:LogicNode)-[:CALLS]->(g:LogicNode) "
            "WHERE f.name CONTAINS 'register_user' "
            "RETURN g.name"
        )
        assert len(result.result_set) >= 1
        callees = {row[0] for row in result.result_set}
        assert any("validate_email" in c for c in callees)

    def test_trace_data_flow_from_run(self) -> None:
        """'Trace data flow from run' pattern."""
        result = self.graph.query(
            "MATCH (v:Variable)-[:PASSES_TO]->(p:Variable) "
            "WHERE v.scope CONTAINS 'run' "
            "RETURN v.name, p.name"
        )
        assert len(result.result_set) >= 1

    def test_what_methods_belong_to_class(self) -> None:
        """'What methods belong to OrderRepository?' pattern."""
        result = self.graph.query(
            "MATCH (m:LogicNode)-[:MEMBER_OF]->(c:LogicNode {kind: 'class'}) "
            "WHERE c.name CONTAINS 'OrderRepository' "
            "RETURN m.name"
        )
        assert len(result.result_set) >= 1

    def test_show_inheritance(self) -> None:
        """'Show the inheritance tree' pattern."""
        result = self.graph.query(
            "MATCH (child:LogicNode)-[:INHERITS]->(parent:LogicNode) "
            "RETURN child.name, parent.name"
        )
        assert len(result.result_set) >= 1

    def test_what_functions_accept_event(self) -> None:
        """'What functions accept an Event type?' pattern."""
        result = self.graph.query(
            "MATCH (fn:LogicNode)-[:ACCEPTS]->(ts:TypeShape) "
            "WHERE ts.base_type CONTAINS 'Event' "
            "RETURN fn.name, ts.kind"
        )
        assert len(result.result_set) >= 1

    def test_cross_file_calls(self) -> None:
        """'Show cross-file calls' pattern."""
        result = self.graph.query(
            "MATCH (a:LogicNode)-[:CALLS]->(b:LogicNode) "
            "WHERE a.module_path <> b.module_path "
            "RETURN a.name, b.name LIMIT 5"
        )
        assert len(result.result_set) >= 1

    def test_high_fanout(self) -> None:
        """'Functions with high fan-out' pattern."""
        result = self.graph.query(
            "MATCH (n:LogicNode)-[r:CALLS]->() "
            "WITH n, count(r) AS calls "
            "WHERE calls > 2 "
            "RETURN n.name, calls ORDER BY calls DESC LIMIT 5"
        )
        assert len(result.result_set) >= 1

    def test_what_does_x_return(self) -> None:
        """'What does parse_input return?' pattern."""
        result = self.graph.query(
            "MATCH (f:LogicNode)-[:RETURNS]->(v:Variable) "
            "WHERE f.name CONTAINS 'parse_input' "
            "RETURN f.name, v.name"
        )
        assert len(result.result_set) >= 1

    def test_what_does_x_mutate(self) -> None:
        """'What variables does matrix_flatten mutate?' pattern."""
        result = self.graph.query(
            "MATCH (f:LogicNode)-[:MUTATES]->(v:Variable) "
            "WHERE f.name CONTAINS 'matrix_flatten' "
            "RETURN v.name"
        )
        assert len(result.result_set) >= 1

    def test_feeds_intra_function(self) -> None:
        """'Show intra-function data flow' pattern."""
        result = self.graph.query(
            "MATCH (v1:Variable)-[:FEEDS]->(v2:Variable) "
            "RETURN v1.name, v2.name LIMIT 5"
        )
        assert len(result.result_set) >= 1

    def test_all_classes(self) -> None:
        """'Show me all classes' pattern."""
        result = self.graph.query(
            "MATCH (n:LogicNode {kind: 'class'}) RETURN n.name"
        )
        assert len(result.result_set) >= 1

    def test_assigns(self) -> None:
        """'What does run assign?' pattern."""
        result = self.graph.query(
            "MATCH (f:LogicNode)-[:ASSIGNS]->(v:Variable) "
            "WHERE f.name CONTAINS 'run' "
            "RETURN v.name LIMIT 5"
        )
        assert len(result.result_set) >= 1

    def test_contains_matching_never_exact(self) -> None:
        """Exact name match should fail for unqualified names — proves CONTAINS is needed."""
        result = self.graph.query(
            "MATCH (n:LogicNode {name: 'register_user'}) RETURN n.name"
        )
        assert len(result.result_set) == 0, (
            "Exact match 'register_user' should return 0 — names are module-qualified"
        )

    def test_scope_based_passes_to_join(self) -> None:
        """CALLS + PASSES_TO joined via Variable.scope."""
        result = self.graph.query(
            "MATCH (caller:LogicNode)-[:CALLS]->(callee:LogicNode), "
            "      (arg:Variable)-[:PASSES_TO]->(param:Variable) "
            "WHERE caller.name = 'ingestion_flow.run' "
            "  AND arg.scope = caller.name "
            "  AND param.scope = callee.name "
            "RETURN caller.name, callee.name, arg.name, param.name"
        )
        assert len(result.result_set) >= 1
