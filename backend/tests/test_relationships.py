"""Tests for relationship edge extraction (CALLS, INHERITS, IMPORTS)."""

from __future__ import annotations

import os

from app.services.ast_parser import parse_file
from app.services.relationship_extractor import extract_relationships


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sample_repo")


def _load_fixture(filename: str) -> str:
    """Load a fixture file's content."""
    with open(os.path.join(FIXTURES_DIR, filename), encoding="utf-8") as f:
        return f.read()


def _get_edges(filename: str, edge_type: str | None = None) -> list:
    """Parse a fixture and extract relationship edges, optionally filtered by type."""
    source = _load_fixture(filename)
    result = parse_file(source, filename)
    edges = extract_relationships(source, filename, result.nodes)
    if edge_type:
        return [e for e in edges if e.edge_type == edge_type]
    return edges


class TestCallsExtraction:
    """Test CALLS edge extraction."""

    def test_direct_function_call(self) -> None:
        """Direct function calls should produce CALLS edges."""
        calls = _get_edges("services.py", "CALLS")
        # create_and_compute calls validate_positive, Calculator, calc.add (x2), clamp
        source_names = {e.source_name for e in calls}
        assert "services.create_and_compute" in source_names

    def test_call_order_preserved(self) -> None:
        """CALLS edges within a function should have sequential call_order."""
        calls = _get_edges("services.py", "CALLS")
        func_calls = [e for e in calls if e.source_name == "services.create_and_compute"]
        orders = [e.properties["call_order"] for e in func_calls]
        assert orders == sorted(orders)
        assert len(set(orders)) == len(orders)  # All unique

    def test_method_call_on_self(self) -> None:
        """self.method() calls should resolve to the class method."""
        source = _load_fixture("calculator.py")
        result = parse_file(source, "calculator.py")
        calls = extract_relationships(source, "calculator.py", result.nodes)
        calls_edges = [e for e in calls if e.edge_type == "CALLS"]
        # Calculator methods don't call other methods in this fixture,
        # but we can verify no spurious self calls
        for edge in calls_edges:
            assert edge.source_name.startswith("calculator.")

    def test_call_line_property(self) -> None:
        """CALLS edges should have call_line set."""
        calls = _get_edges("services.py", "CALLS")
        for edge in calls:
            assert edge.properties["call_line"] > 0

    def test_nested_function_calls(self) -> None:
        """Calls within nested functions should be extracted."""
        source = _load_fixture("nested.py")
        result = parse_file(source, "nested.py")
        calls = extract_relationships(source, "nested.py", result.nodes)
        calls_edges = [e for e in calls if e.edge_type == "CALLS"]
        # top_level_func calls nested_func()
        top_calls = [e for e in calls_edges if e.source_name == "nested.top_level_func"]
        target_names = {e.target_name for e in top_calls}
        assert "nested.top_level_func.nested_func" in target_names

    def test_call_chain(self) -> None:
        """A -> B -> C call chain should produce edges for each hop."""
        calls = _get_edges("services.py", "CALLS")
        # main -> process_batch -> create_and_compute
        main_calls = {e.target_name for e in calls if e.source_name == "services.main"}
        batch_calls = {e.target_name for e in calls if e.source_name == "services.process_batch"}
        assert "services.process_batch" in main_calls
        assert "services.create_and_compute" in batch_calls


class TestInheritsExtraction:
    """Test INHERITS edge extraction."""

    def test_single_inheritance(self) -> None:
        """Single inheritance should produce one INHERITS edge."""
        edges = _get_edges("shapes.py", "INHERITS")
        circle_inherits = [e for e in edges if e.source_name == "shapes.Circle"]
        assert len(circle_inherits) == 1
        # Should inherit from Shape (resolved or via import)
        assert any("Shape" in e.target_name for e in circle_inherits)

    def test_multiple_classes_inherit(self) -> None:
        """Multiple classes inheriting from the same base should each have INHERITS edges."""
        edges = _get_edges("shapes.py", "INHERITS")
        inheriting_classes = {e.source_name for e in edges}
        assert "shapes.Circle" in inheriting_classes
        assert "shapes.Rectangle" in inheriting_classes

    def test_abc_inheritance(self) -> None:
        """Classes inheriting from ABC should produce INHERITS edge."""
        edges = _get_edges("shapes.py", "INHERITS")
        shape_inherits = [e for e in edges if e.source_name == "shapes.Shape"]
        assert len(shape_inherits) == 1
        assert "ABC" in shape_inherits[0].target_name


class TestImportsExtraction:
    """Test IMPORTS edge extraction."""

    def test_import_statement(self) -> None:
        """'import X' should produce an IMPORTS edge."""
        edges = _get_edges("shapes.py", "IMPORTS")
        target_names = {e.target_name for e in edges}
        # shapes.py imports abc and math
        assert "abc" in target_names or "math" in target_names

    def test_import_from_statement(self) -> None:
        """'from X import Y' should produce an IMPORTS edge to X."""
        edges = _get_edges("services.py", "IMPORTS")
        target_names = {e.target_name for e in edges}
        assert "calculator" in target_names
        assert "utils" in target_names

    def test_import_source_is_module(self) -> None:
        """IMPORTS edges should always have the module as source."""
        edges = _get_edges("services.py", "IMPORTS")
        for edge in edges:
            assert edge.source_type == "Module"
            assert edge.source_name == "services"

    def test_import_resolves_cross_file_calls(self) -> None:
        """Imported names should resolve in CALLS edges."""
        calls = _get_edges("services.py", "CALLS")
        targets = {e.target_name for e in calls}
        # validate_positive is imported from utils
        assert any("validate_positive" in t for t in targets)


class TestCombinedExtraction:
    """Test that all edge types are extracted together."""

    def test_all_edge_types_present(self) -> None:
        """A file with imports, inheritance, and calls should produce all edge types."""
        source = _load_fixture("services.py")
        result = parse_file(source, "services.py")
        edges = extract_relationships(source, "services.py", result.nodes)
        edge_types = {e.edge_type for e in edges}
        assert "CALLS" in edge_types
        assert "IMPORTS" in edge_types

    def test_shapes_all_edge_types(self) -> None:
        """shapes.py should have IMPORTS and INHERITS."""
        edges = _get_edges("shapes.py")
        edge_types = {e.edge_type for e in edges}
        assert "IMPORTS" in edge_types
        assert "INHERITS" in edge_types
