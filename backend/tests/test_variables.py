"""Tests for variable and assignment extraction (TICKET-201)."""

from __future__ import annotations

import os

from app.services.parsing.ast_parser import parse_file
from app.services.parsing.variable_extractor import extract_variables


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sample_repo")


def _load_fixture(filename: str) -> str:
    """Load a fixture file's content."""
    with open(os.path.join(FIXTURES_DIR, filename), encoding="utf-8") as f:
        return f.read()


def _get_var_result(filename: str):  # type: ignore[no-untyped-def]
    """Parse a fixture and extract variables."""
    source = _load_fixture(filename)
    result = parse_file(source, filename)
    return extract_variables(source, filename, result.nodes)


class TestVariableNodeCreation:
    """Test that Variable nodes are created correctly."""

    def test_simple_assignment_creates_variable(self) -> None:
        """Simple assignments should create Variable nodes."""
        result = _get_var_result("variables.py")
        var_names = {v.name for v in result.nodes}
        assert "variables.process_items.result" in var_names
        assert "variables.process_items.count" in var_names
        assert "variables.process_items.total" in var_names

    def test_parameter_creates_variable(self) -> None:
        """Function parameters should create Variable nodes."""
        result = _get_var_result("variables.py")
        var_names = {v.name for v in result.nodes}
        assert "variables.process_items.items" in var_names
        assert "variables.process_items.threshold" in var_names

    def test_self_attribute_creates_class_scoped_variable(self) -> None:
        """self.x assignments should create class-scoped Variable nodes."""
        result = _get_var_result("variables.py")
        var_names = {v.name for v in result.nodes}
        assert "variables.Account.owner" in var_names
        assert "variables.Account.balance" in var_names
        assert "variables.Account.transactions" in var_names

    def test_self_attribute_one_node_two_methods(self) -> None:
        """self.balance set in __init__ and modified in deposit/withdraw should be one Variable node."""
        result = _get_var_result("variables.py")
        balance_vars = [v for v in result.nodes if v.name == "variables.Account.balance"]
        assert len(balance_vars) == 1

    def test_variable_scope(self) -> None:
        """Variable scope should be the enclosing function."""
        result = _get_var_result("variables.py")
        result_var = next(v for v in result.nodes if v.name == "variables.process_items.result")
        assert result_var.scope == "variables.process_items"

    def test_unpacking_creates_variables(self) -> None:
        """Tuple unpacking should create Variable nodes for each target."""
        result = _get_var_result("variables.py")
        var_names = {v.name for v in result.nodes}
        assert "variables.unpacking_example.a" in var_names
        assert "variables.unpacking_example.b" in var_names


class TestAssignsEdges:
    """Test ASSIGNS edge creation."""

    def test_assigns_edge_count(self) -> None:
        """Correct number of ASSIGNS edges should be created."""
        result = _get_var_result("variables.py")
        assigns = [e for e in result.edges if e.edge_type == "ASSIGNS"]
        assert len(assigns) > 0

    def test_assigns_has_line(self) -> None:
        """ASSIGNS edges should have line property."""
        result = _get_var_result("variables.py")
        assigns = [e for e in result.edges if e.edge_type == "ASSIGNS"]
        for edge in assigns:
            assert edge.properties["line"] > 0

    def test_augmented_assign_is_rebind(self) -> None:
        """+= assignments should have is_rebind=True."""
        result = _get_var_result("variables.py")
        assigns = [
            e for e in result.edges
            if e.edge_type == "ASSIGNS" and e.target_name == "variables.process_items.count"
        ]
        # First assign: count = 0 (is_rebind=False), then count += 1 (is_rebind=True)
        rebinds = [e for e in assigns if e.properties.get("is_rebind")]
        assert len(rebinds) >= 1

    def test_conditional_assign_has_context(self) -> None:
        """Assignments inside if blocks should have control_context and branch."""
        result = _get_var_result("variables.py")
        assigns = [
            e for e in result.edges
            if e.edge_type == "ASSIGNS"
            and e.target_name == "variables.process_items.count"
            and e.properties.get("control_context")
        ]
        assert len(assigns) >= 1
        assert assigns[0].properties["branch"] is not None

    def test_self_assign_from_multiple_methods(self) -> None:
        """self.balance should have ASSIGNS edges from both __init__ and deposit."""
        result = _get_var_result("variables.py")
        balance_assigns = [
            e for e in result.edges
            if e.edge_type == "ASSIGNS" and e.target_name == "variables.Account.balance"
        ]
        sources = {e.source_name for e in balance_assigns}
        assert "variables.Account.__init__" in sources


class TestMutatesEdges:
    """Test MUTATES edge creation (TICKET-202)."""

    def test_append_creates_mutates(self) -> None:
        """list.append() should create a MUTATES edge."""
        result = _get_var_result("variables.py")
        mutates = [
            e for e in result.edges
            if e.edge_type == "MUTATES" and "items" in e.target_name
            and e.source_name == "variables.mutation_patterns"
        ]
        assert len(mutates) >= 1
        kinds = {e.properties.get("mutation_kind") for e in mutates}
        assert "method_call" in kinds

    def test_dict_update_creates_mutates(self) -> None:
        """dict.update() should create a MUTATES edge."""
        result = _get_var_result("variables.py")
        mutates = [
            e for e in result.edges
            if e.edge_type == "MUTATES" and "data" in e.target_name
            and e.source_name == "variables.mutation_patterns"
        ]
        assert len(mutates) >= 1

    def test_set_add_creates_mutates(self) -> None:
        """set.add() should create a MUTATES edge."""
        result = _get_var_result("variables.py")
        mutates = [
            e for e in result.edges
            if e.edge_type == "MUTATES" and "numbers" in e.target_name
            and e.source_name == "variables.mutation_patterns"
        ]
        assert len(mutates) >= 1

    def test_subscript_assign_creates_mutates(self) -> None:
        """items[0] = 99 should create a MUTATES edge with subscript_assign kind."""
        result = _get_var_result("variables.py")
        sub_mutates = [
            e for e in result.edges
            if e.edge_type == "MUTATES"
            and e.properties.get("mutation_kind") == "subscript_assign"
            and e.source_name == "variables.mutation_patterns"
        ]
        assert len(sub_mutates) >= 1

    def test_self_transactions_append_is_mutates(self) -> None:
        """self.transactions.append() should be a MUTATES edge."""
        result = _get_var_result("variables.py")
        mutates = [
            e for e in result.edges
            if e.edge_type == "MUTATES" and "transactions" in e.target_name
        ]
        assert len(mutates) >= 1


class TestReadsEdges:
    """Test READS edge creation (TICKET-202)."""

    def test_reads_in_expression(self) -> None:
        """Variables read in expressions should create READS edges."""
        result = _get_var_result("variables.py")
        reads = [
            e for e in result.edges
            if e.edge_type == "READS"
        ]
        assert len(reads) > 0

    def test_reads_self_balance_in_condition(self) -> None:
        """self.balance read in 'if amount > self.balance' should create READS edge."""
        result = _get_var_result("variables.py")
        reads = [
            e for e in result.edges
            if e.edge_type == "READS" and "balance" in e.target_name
            and e.source_name == "variables.Account.withdraw"
        ]
        assert len(reads) >= 1


class TestReturnsEdges:
    """Test RETURNS edge creation (TICKET-202)."""

    def test_return_creates_returns_edge(self) -> None:
        """'return result' should create a RETURNS edge."""
        result = _get_var_result("variables.py")
        returns = [
            e for e in result.edges
            if e.edge_type == "RETURNS" and e.target_name == "variables.process_items.result"
        ]
        assert len(returns) >= 1

    def test_self_balance_return(self) -> None:
        """'return self.balance' should create a RETURNS edge."""
        result = _get_var_result("variables.py")
        returns = [
            e for e in result.edges
            if e.edge_type == "RETURNS" and "balance" in e.target_name
        ]
        assert len(returns) >= 1


class TestSeqOrdering:
    """Test that all edges have seq values for ordering."""

    def test_edges_sorted_by_seq(self) -> None:
        """All edges within a function should be sortable by seq."""
        result = _get_var_result("variables.py")
        func_edges = [
            e for e in result.edges
            if e.source_name == "variables.process_items"
        ]
        seqs = [e.properties.get("seq") for e in func_edges]
        assert all(s is not None for s in seqs)
