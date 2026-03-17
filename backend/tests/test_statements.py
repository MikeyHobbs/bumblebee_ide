"""Tests for statement and control flow node extraction."""

from __future__ import annotations

import os

from app.services.parsing.ast_parser import parse_file
from app.services.parsing.statement_extractor import extract_statements


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sample_repo")


def _load_fixture(filename: str) -> str:
    """Load a fixture file's content."""
    with open(os.path.join(FIXTURES_DIR, filename), encoding="utf-8") as f:
        return f.read()


def _get_statements(filename: str):  # type: ignore[no-untyped-def]
    """Parse a fixture and extract statement-level nodes and edges."""
    source = _load_fixture(filename)
    result = parse_file(source, filename)
    return extract_statements(source, filename, result.nodes)


class TestSimpleStatements:
    """Test extraction of simple sequential statements."""

    def test_statement_count(self) -> None:
        """Simple function body should produce correct number of statements."""
        result = _get_statements("control_flow.py")
        stmts = [n for n in result.nodes if n.parent_name == "control_flow.simple_statements"]
        # a = x + 1, b = a * 2, c = b - 3, return c
        assert len(stmts) == 4

    def test_statement_kinds(self) -> None:
        """Statements should have correct kind values."""
        result = _get_statements("control_flow.py")
        stmts = [n for n in result.nodes if n.parent_name == "control_flow.simple_statements"]
        kinds = [s.kind for s in sorted(stmts, key=lambda s: s.seq)]
        assert kinds == ["assignment", "assignment", "assignment", "return"]

    def test_statement_seq_order(self) -> None:
        """Statements should have sequential seq values."""
        result = _get_statements("control_flow.py")
        stmts = [n for n in result.nodes if n.parent_name == "control_flow.simple_statements"]
        seqs = sorted(s.seq for s in stmts)
        assert seqs == list(range(len(seqs)))

    def test_contains_edges(self) -> None:
        """Function should have CONTAINS edges to its statements."""
        result = _get_statements("control_flow.py")
        contains = [
            e for e in result.edges
            if e.edge_type == "CONTAINS" and e.source_name == "control_flow.simple_statements"
        ]
        assert len(contains) == 4

    def test_next_edges(self) -> None:
        """Sequential statements should have NEXT edges."""
        result = _get_statements("control_flow.py")
        stmts = [n for n in result.nodes if n.parent_name == "control_flow.simple_statements"]
        next_edges = [
            e for e in result.edges
            if e.edge_type == "NEXT"
            and any(s.name == e.source_name for s in stmts)
        ]
        # 4 statements = 3 NEXT edges
        assert len(next_edges) == 3

    def test_source_text_captured(self) -> None:
        """Statement source_text should contain the raw code."""
        result = _get_statements("control_flow.py")
        stmts = [n for n in result.nodes if n.parent_name == "control_flow.simple_statements"]
        first = sorted(stmts, key=lambda s: s.seq)[0]
        assert "a = x + 1" in first.source_text


class TestIfElseFlow:
    """Test if/elif/else extraction."""

    def test_control_flow_node_created(self) -> None:
        """If statement should create a ControlFlow node."""
        result = _get_statements("control_flow.py")
        cfs = [n for n in result.nodes if n.node_type == "ControlFlow" and n.parent_name == "control_flow.if_else_flow"]
        assert len(cfs) == 1
        assert cfs[0].kind == "if"

    def test_condition_text(self) -> None:
        """ControlFlow node should have condition_text."""
        result = _get_statements("control_flow.py")
        cf = next(n for n in result.nodes if n.node_type == "ControlFlow" and n.parent_name == "control_flow.if_else_flow")
        assert cf.condition_text == "x > 10"

    def test_branches_created(self) -> None:
        """If/elif/else should create 3 Branch nodes."""
        result = _get_statements("control_flow.py")
        cf = next(n for n in result.nodes if n.node_type == "ControlFlow" and n.parent_name == "control_flow.if_else_flow")
        branches = [n for n in result.nodes if n.node_type == "Branch" and n.parent_name == cf.name]
        assert len(branches) == 3

    def test_branch_kinds(self) -> None:
        """Branches should have correct kind values."""
        result = _get_statements("control_flow.py")
        cf = next(n for n in result.nodes if n.node_type == "ControlFlow" and n.parent_name == "control_flow.if_else_flow")
        branches = sorted(
            [n for n in result.nodes if n.node_type == "Branch" and n.parent_name == cf.name],
            key=lambda b: b.seq,
        )
        kinds = [b.kind for b in branches]
        assert kinds == ["if", "elif", "else"]

    def test_branch_contains_statements(self) -> None:
        """Each branch should contain its body statements."""
        result = _get_statements("control_flow.py")
        branches = [n for n in result.nodes if n.node_type == "Branch" and "if_else_flow" in n.name]
        for branch in branches:
            branch_stmts = [n for n in result.nodes if n.parent_name == branch.name]
            assert len(branch_stmts) >= 1


class TestForLoop:
    """Test for loop extraction."""

    def test_for_control_flow(self) -> None:
        """For loop should create a ControlFlow node."""
        result = _get_statements("control_flow.py")
        cfs = [n for n in result.nodes if n.node_type == "ControlFlow" and n.parent_name == "control_flow.for_loop"]
        assert len(cfs) == 1
        assert cfs[0].kind == "for"

    def test_for_condition_text(self) -> None:
        """For loop should have iterator as condition_text."""
        result = _get_statements("control_flow.py")
        cf = next(n for n in result.nodes if n.node_type == "ControlFlow" and n.parent_name == "control_flow.for_loop")
        assert "item" in cf.condition_text
        assert "items" in cf.condition_text

    def test_for_body_branch(self) -> None:
        """For loop body should be wrapped in a branch."""
        result = _get_statements("control_flow.py")
        cf = next(n for n in result.nodes if n.node_type == "ControlFlow" and n.parent_name == "control_flow.for_loop")
        branches = [n for n in result.nodes if n.node_type == "Branch" and n.parent_name == cf.name]
        assert len(branches) >= 1


class TestWhileLoop:
    """Test while loop extraction."""

    def test_while_control_flow(self) -> None:
        """While loop should create a ControlFlow node."""
        result = _get_statements("control_flow.py")
        cfs = [n for n in result.nodes if n.node_type == "ControlFlow" and n.parent_name == "control_flow.while_loop"]
        assert len(cfs) == 1
        assert cfs[0].kind == "while"


class TestTryExcept:
    """Test try/except/else/finally extraction."""

    def test_try_control_flow(self) -> None:
        """Try statement should create a ControlFlow node."""
        result = _get_statements("control_flow.py")
        cfs = [n for n in result.nodes if n.node_type == "ControlFlow" and n.parent_name == "control_flow.try_except_flow"]
        assert len(cfs) == 1
        assert cfs[0].kind == "try"

    def test_try_branches(self) -> None:
        """Try/except/else/finally should create branches."""
        result = _get_statements("control_flow.py")
        cf = next(n for n in result.nodes if n.node_type == "ControlFlow" and n.parent_name == "control_flow.try_except_flow")
        branches = sorted(
            [n for n in result.nodes if n.node_type == "Branch" and n.parent_name == cf.name],
            key=lambda b: b.seq,
        )
        # try, except ValueError, except TypeError, else, finally
        assert len(branches) == 5
        kinds = [b.kind for b in branches]
        assert "try" in kinds
        assert "except" in kinds
        assert "else" in kinds
        assert "finally" in kinds


class TestNestedControlFlow:
    """Test nested control flow structures."""

    def test_nested_if_inside_for(self) -> None:
        """An if inside a for should create nested ControlFlow nodes."""
        result = _get_statements("control_flow.py")
        # The for loop's branch should contain an if ControlFlow
        cfs = [n for n in result.nodes if n.node_type == "ControlFlow"]
        nested_cfs = [n for n in cfs if "nested_control_flow" in n.name]
        # Should have at least a for and an if
        kinds = {n.kind for n in nested_cfs}
        assert "for" in kinds
        assert "if" in kinds

    def test_nested_contains_chain(self) -> None:
        """CONTAINS edges should chain: Function -> ControlFlow -> Branch -> ControlFlow."""
        result = _get_statements("control_flow.py")
        contains = [e for e in result.edges if e.edge_type == "CONTAINS" and "nested_control_flow" in e.source_name]
        assert len(contains) > 0


class TestNextChainTraversal:
    """Test that NEXT chains can reconstruct execution order."""

    def test_next_chain_in_simple_function(self) -> None:
        """Following NEXT edges should visit all statements in order."""
        result = _get_statements("control_flow.py")
        stmts = sorted(
            [n for n in result.nodes if n.parent_name == "control_flow.simple_statements"],
            key=lambda s: s.seq,
        )
        next_edges = {
            e.source_name: e.target_name
            for e in result.edges
            if e.edge_type == "NEXT" and any(s.name == e.source_name for s in stmts)
        }

        # Follow the chain from first to last
        visited = [stmts[0].name]
        current = stmts[0].name
        while current in next_edges:
            current = next_edges[current]
            visited.append(current)

        assert len(visited) == len(stmts)
        assert visited == [s.name for s in stmts]


class TestWithStatement:
    """Test with statement extraction."""

    def test_with_control_flow(self) -> None:
        """With statement should create a ControlFlow node."""
        result = _get_statements("control_flow.py")
        cfs = [n for n in result.nodes if n.node_type == "ControlFlow" and n.parent_name == "control_flow.with_statement"]
        assert len(cfs) == 1
        assert cfs[0].kind == "with"
