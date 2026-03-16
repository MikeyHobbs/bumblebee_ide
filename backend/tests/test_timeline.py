"""Tests for mutation timeline query (TICKET-204)."""

from __future__ import annotations

import os

from app.services.ast_parser import parse_file
from app.services.relationship_extractor import extract_relationships
from app.services.variable_extractor import extract_variables
from app.services.dataflow_extractor import extract_dataflow
from app.graph.timeline import build_timeline_from_extractions, search_variables


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sample_repo")


def _load_fixture(filename: str) -> str:
    """Load a fixture file's content."""
    with open(os.path.join(FIXTURES_DIR, filename), encoding="utf-8") as f:
        return f.read()


def _build_full_extractions(filename: str):  # type: ignore[no-untyped-def]
    """Run the full extraction pipeline on a fixture file."""
    source = _load_fixture(filename)
    result = parse_file(source, filename)
    rel_edges = extract_relationships(source, filename, result.nodes)
    var_result = extract_variables(source, filename, result.nodes)
    df_result = extract_dataflow(source, filename, result.nodes, rel_edges, var_result.nodes, var_result.edges)
    return result.nodes, var_result.nodes, var_result.edges, df_result.edges


class TestBuildTimeline:
    """Test building mutation timelines from extraction results."""

    def test_simple_variable_timeline(self) -> None:
        """A variable with assigns, reads, and return should produce a complete timeline."""
        nodes, var_nodes, var_edges, df_edges = _build_full_extractions("dataflow.py")
        timeline = build_timeline_from_extractions(
            "dataflow.feeds_example.a", var_nodes, var_edges, df_edges
        )
        assert timeline is not None
        assert timeline.variable["name"] == "dataflow.feeds_example.a"
        assert timeline.origin is not None

    def test_timeline_has_mutations(self) -> None:
        """Timeline should include all ASSIGNS/MUTATES interactions."""
        nodes, var_nodes, var_edges, df_edges = _build_full_extractions("variables.py")
        timeline = build_timeline_from_extractions(
            "variables.Account.balance", var_nodes, var_edges, df_edges
        )
        assert timeline is not None
        assert len(timeline.mutations) >= 2  # __init__ assign + deposit/withdraw augmented assigns

    def test_timeline_has_reads(self) -> None:
        """Timeline should include READS interactions."""
        nodes, var_nodes, var_edges, df_edges = _build_full_extractions("variables.py")
        timeline = build_timeline_from_extractions(
            "variables.Account.balance", var_nodes, var_edges, df_edges
        )
        assert timeline is not None
        assert len(timeline.reads) >= 1

    def test_timeline_has_returns(self) -> None:
        """Timeline should include RETURNS interactions."""
        nodes, var_nodes, var_edges, df_edges = _build_full_extractions("variables.py")
        timeline = build_timeline_from_extractions(
            "variables.Account.balance", var_nodes, var_edges, df_edges
        )
        assert timeline is not None
        assert len(timeline.returns) >= 1

    def test_timeline_has_feeds(self) -> None:
        """Timeline should include FEEDS interactions."""
        nodes, var_nodes, var_edges, df_edges = _build_full_extractions("dataflow.py")
        timeline = build_timeline_from_extractions(
            "dataflow.feeds_example.a", var_nodes, var_edges, df_edges
        )
        assert timeline is not None
        assert len(timeline.feeds) >= 1

    def test_passes_to_chain_in_timeline(self) -> None:
        """Timeline should follow PASSES_TO chains across functions."""
        nodes, var_nodes, var_edges, df_edges = _build_full_extractions("dataflow.py")
        timeline = build_timeline_from_extractions(
            "dataflow.pipeline.x", var_nodes, var_edges, df_edges
        )
        assert timeline is not None
        assert len(timeline.passes) >= 1

    def test_timeline_mutations_sorted(self) -> None:
        """Mutations should be sorted by function name and seq."""
        nodes, var_nodes, var_edges, df_edges = _build_full_extractions("variables.py")
        timeline = build_timeline_from_extractions(
            "variables.Account.balance", var_nodes, var_edges, df_edges
        )
        assert timeline is not None
        for i in range(len(timeline.mutations) - 1):
            a = timeline.mutations[i]
            b = timeline.mutations[i + 1]
            assert (a.function_name, a.seq) <= (b.function_name, b.seq)

    def test_timeline_has_terminal(self) -> None:
        """Timeline should identify a terminal interaction."""
        nodes, var_nodes, var_edges, df_edges = _build_full_extractions("dataflow.py")
        timeline = build_timeline_from_extractions(
            "dataflow.feeds_example.d", var_nodes, var_edges, df_edges
        )
        assert timeline is not None
        assert timeline.terminal is not None

    def test_nonexistent_variable_returns_none(self) -> None:
        """Querying a nonexistent variable should return None."""
        nodes, var_nodes, var_edges, df_edges = _build_full_extractions("dataflow.py")
        timeline = build_timeline_from_extractions(
            "dataflow.nonexistent.var", var_nodes, var_edges, df_edges
        )
        assert timeline is None

    def test_conditional_context_in_timeline(self) -> None:
        """Timeline entries should include control_context and branch."""
        nodes, var_nodes, var_edges, df_edges = _build_full_extractions("variables.py")
        timeline = build_timeline_from_extractions(
            "variables.process_items.count", var_nodes, var_edges, df_edges
        )
        assert timeline is not None
        # count is assigned inside an if block
        conditional = [
            m for m in timeline.mutations
            if m.properties.get("control_context")
        ]
        assert len(conditional) >= 1


class TestSearchVariables:
    """Test variable search functionality."""

    def test_search_by_name(self) -> None:
        """Search should find variables matching a name."""
        _, var_nodes, _, _ = _build_full_extractions("variables.py")
        results = search_variables("balance", var_nodes)
        assert len(results) >= 1
        assert any("balance" in v.name for v in results)

    def test_search_by_scope(self) -> None:
        """Search with scope filter should narrow results."""
        _, var_nodes, _, _ = _build_full_extractions("variables.py")
        results = search_variables("result", var_nodes, scope="process_items")
        assert len(results) >= 1
        assert all("process_items" in v.scope for v in results)

    def test_search_no_results(self) -> None:
        """Search for nonexistent variable should return empty list."""
        _, var_nodes, _, _ = _build_full_extractions("variables.py")
        results = search_variables("zzz_nonexistent", var_nodes)
        assert len(results) == 0


class TestEndToEndPipeline:
    """End-to-end test: index sample repo → query timeline → verify full lifecycle."""

    def test_full_pipeline_balance(self) -> None:
        """Full pipeline test for self.balance across multiple methods."""
        nodes, var_nodes, var_edges, df_edges = _build_full_extractions("variables.py")

        timeline = build_timeline_from_extractions(
            "variables.Account.balance", var_nodes, var_edges, df_edges
        )
        assert timeline is not None

        # Variable info
        assert timeline.variable["name"] == "variables.Account.balance"
        assert timeline.variable["origin_func"] == "variables.Account.__init__"

        # Origin: first assignment in __init__
        assert timeline.origin is not None
        assert timeline.origin.function_name == "variables.Account.__init__"

        # Mutations should include assigns from __init__, deposit, withdraw
        funcs_with_mutations = {m.function_name for m in timeline.mutations}
        assert "variables.Account.__init__" in funcs_with_mutations
        assert "variables.Account.deposit" in funcs_with_mutations

        # Returns from deposit and withdraw
        assert len(timeline.returns) >= 1

    def test_full_pipeline_dataflow(self) -> None:
        """Full pipeline test for data flow with FEEDS and PASSES_TO."""
        nodes, var_nodes, var_edges, df_edges = _build_full_extractions("dataflow.py")

        # Test feeds_example.c which should have FEEDS from a and b
        timeline = build_timeline_from_extractions(
            "dataflow.feeds_example.c", var_nodes, var_edges, df_edges
        )
        assert timeline is not None
        assert len(timeline.feeds) >= 1

        # Test pipeline.x which should have PASSES_TO to transformer.data
        timeline_x = build_timeline_from_extractions(
            "dataflow.pipeline.x", var_nodes, var_edges, df_edges
        )
        assert timeline_x is not None
        assert len(timeline_x.passes) >= 1
