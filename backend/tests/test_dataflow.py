"""Tests for PASSES_TO and FEEDS edge extraction (TICKET-203/205)."""

from __future__ import annotations

import os

from app.services.parsing.ast_parser import parse_file
from app.services.parsing.relationship_extractor import extract_relationships
from app.services.parsing.variable_extractor import extract_variables
from app.services.parsing.dataflow_extractor import extract_dataflow


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sample_repo")


def _load_fixture(filename: str) -> str:
    """Load a fixture file's content."""
    with open(os.path.join(FIXTURES_DIR, filename), encoding="utf-8") as f:
        return f.read()


def _get_dataflow(filename: str):  # type: ignore[no-untyped-def]
    """Parse a fixture and extract all data flow edges."""
    source = _load_fixture(filename)
    result = parse_file(source, filename)
    rel_edges = extract_relationships(source, filename, result.nodes)
    var_result = extract_variables(source, filename, result.nodes)
    return extract_dataflow(source, filename, result.nodes, rel_edges, var_result.nodes, var_result.edges)


class TestPassesTo:
    """Test PASSES_TO edge extraction."""

    def test_positional_arg_passes_to(self) -> None:
        """Positional argument should create PASSES_TO edge."""
        result = _get_dataflow("dataflow.py")
        passes = [e for e in result.edges if e.edge_type == "PASSES_TO"]
        # pipeline: x is passed to transformer(x) -> maps to data param
        x_to_data = [
            e for e in passes
            if e.source_name == "dataflow.pipeline.x"
            and e.target_name == "dataflow.transformer.data"
        ]
        assert len(x_to_data) >= 1

    def test_keyword_arg_passes_to(self) -> None:
        """Keyword argument should create PASSES_TO edge with correct keyword."""
        result = _get_dataflow("dataflow.py")
        passes = [e for e in result.edges if e.edge_type == "PASSES_TO"]
        # keyword_passing: transformer(data=val)
        kw_passes = [
            e for e in passes
            if e.source_name == "dataflow.keyword_passing.val"
            and e.target_name == "dataflow.transformer.data"
        ]
        assert len(kw_passes) >= 1
        if kw_passes:
            assert kw_passes[0].properties.get("arg_keyword") == "data"

    def test_chain_passes_to(self) -> None:
        """A -> B -> C chain should have PASSES_TO at each hop."""
        result = _get_dataflow("dataflow.py")
        passes = [e for e in result.edges if e.edge_type == "PASSES_TO"]
        # pipeline: y passed to consumer(y) -> maps to value param
        y_to_value = [
            e for e in passes
            if e.source_name == "dataflow.pipeline.y"
            and e.target_name == "dataflow.consumer.value"
        ]
        assert len(y_to_value) >= 1

    def test_passes_to_has_call_line(self) -> None:
        """PASSES_TO edges should have call_line property."""
        result = _get_dataflow("dataflow.py")
        passes = [e for e in result.edges if e.edge_type == "PASSES_TO"]
        for edge in passes:
            assert edge.properties.get("call_line") is not None

    def test_passes_to_has_arg_position(self) -> None:
        """PASSES_TO edges should have arg_position property."""
        result = _get_dataflow("dataflow.py")
        passes = [e for e in result.edges if e.edge_type == "PASSES_TO"]
        for edge in passes:
            assert "arg_position" in edge.properties


class TestFeeds:
    """Test FEEDS edge extraction."""

    def test_assignment_feeds(self) -> None:
        """Reading a variable in RHS of assignment should create FEEDS edge."""
        result = _get_dataflow("dataflow.py")
        feeds = [e for e in result.edges if e.edge_type == "FEEDS"]
        # c = a + b -> a FEEDS c, b FEEDS c
        a_to_c = [
            e for e in feeds
            if e.source_name == "dataflow.feeds_example.a"
            and e.target_name == "dataflow.feeds_example.c"
        ]
        assert len(a_to_c) >= 1

    def test_feeds_both_operands(self) -> None:
        """Both operands in 'c = a + b' should FEED into c."""
        result = _get_dataflow("dataflow.py")
        feeds = [e for e in result.edges if e.edge_type == "FEEDS"]
        feeds_to_c = [
            e for e in feeds
            if e.target_name == "dataflow.feeds_example.c"
        ]
        sources = {e.source_name for e in feeds_to_c}
        assert "dataflow.feeds_example.a" in sources
        assert "dataflow.feeds_example.b" in sources

    def test_chained_feeds(self) -> None:
        """c = a + b; d = c * 2 -> c FEEDS d."""
        result = _get_dataflow("dataflow.py")
        feeds = [e for e in result.edges if e.edge_type == "FEEDS"]
        c_to_d = [
            e for e in feeds
            if e.source_name == "dataflow.feeds_example.c"
            and e.target_name == "dataflow.feeds_example.d"
        ]
        assert len(c_to_d) >= 1

    def test_mutation_feeds(self) -> None:
        """items.append(new_item) -> new_item FEEDS items."""
        result = _get_dataflow("dataflow.py")
        feeds = [e for e in result.edges if e.edge_type == "FEEDS"]
        item_feeds = [
            e for e in feeds
            if e.source_name == "dataflow.mutation_feeds.new_item"
            and e.target_name == "dataflow.mutation_feeds.items"
        ]
        assert len(item_feeds) >= 1

    def test_feeds_via_property(self) -> None:
        """FEEDS edges should have a 'via' property."""
        result = _get_dataflow("dataflow.py")
        feeds = [e for e in result.edges if e.edge_type == "FEEDS"]
        for edge in feeds:
            assert "via" in edge.properties

    def test_no_self_feed(self) -> None:
        """A variable should not FEED itself."""
        result = _get_dataflow("dataflow.py")
        feeds = [e for e in result.edges if e.edge_type == "FEEDS"]
        for edge in feeds:
            assert edge.source_name != edge.target_name
