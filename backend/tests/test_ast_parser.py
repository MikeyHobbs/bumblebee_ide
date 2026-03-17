"""Tests for the AST parser structural node extraction."""

from __future__ import annotations

import os

import pytest

from app.services.parsing.ast_parser import ParsedNode, compute_checksum, parse_file


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sample_repo")


def _load_fixture(filename: str) -> str:
    """Load a fixture file's content.

    Args:
        filename: Name of the fixture file to load.

    Returns:
        The file contents as a string.
    """
    with open(os.path.join(FIXTURES_DIR, filename), encoding="utf-8") as f:
        return f.read()


class TestParseFileBasic:
    """Test basic file parsing."""

    def test_module_node_created(self) -> None:
        """Each parsed file should produce a Module node."""
        source = _load_fixture("calculator.py")
        result = parse_file(source, "calculator.py")
        modules = [n for n in result.nodes if n.node_type == "Module"]
        assert len(modules) == 1
        assert modules[0].name == "calculator"

    def test_class_extraction(self) -> None:
        """Classes should be extracted with correct properties."""
        source = _load_fixture("calculator.py")
        result = parse_file(source, "calculator.py")
        classes = [n for n in result.nodes if n.node_type == "Class"]
        assert len(classes) == 1
        assert classes[0].name == "calculator.Calculator"
        assert classes[0].docstring == "A simple calculator class."

    def test_function_extraction(self) -> None:
        """Functions should be extracted with params and docstrings."""
        source = _load_fixture("calculator.py")
        result = parse_file(source, "calculator.py")
        functions = [n for n in result.nodes if n.node_type == "Function"]
        # __init__, add, subtract, reset
        assert len(functions) == 4

        add_func = next(f for f in functions if f.name.endswith(".add"))
        assert add_func.name == "calculator.Calculator.add"
        assert "self" in add_func.params
        assert "x" in add_func.params
        assert add_func.docstring == "Add x to the current value."

    def test_defines_edges(self) -> None:
        """DEFINES edges should connect Module->Class and Class->Function."""
        source = _load_fixture("calculator.py")
        result = parse_file(source, "calculator.py")

        # Module DEFINES Class
        mod_class_edges = [e for e in result.edges if e.source_type == "Module" and e.target_type == "Class"]
        assert len(mod_class_edges) == 1
        assert mod_class_edges[0].target_name == "calculator.Calculator"

        # Class DEFINES Functions
        class_func_edges = [e for e in result.edges if e.source_type == "Class" and e.target_type == "Function"]
        assert len(class_func_edges) == 4  # __init__, add, subtract, reset

    def test_checksum_consistency(self) -> None:
        """Same source should produce same checksum."""
        source = _load_fixture("calculator.py")
        r1 = parse_file(source, "calculator.py")
        r2 = parse_file(source, "calculator.py")
        assert r1.checksum == r2.checksum

    def test_checksum_changes(self) -> None:
        """Different source should produce different checksum."""
        assert compute_checksum("foo") != compute_checksum("bar")


class TestInheritanceStructure:
    """Test parsing of inheritance hierarchies."""

    def test_multiple_classes(self) -> None:
        """Multiple classes in one file should all be extracted."""
        source = _load_fixture("shapes.py")
        result = parse_file(source, "shapes.py")
        classes = [n for n in result.nodes if n.node_type == "Class"]
        class_names = {c.name for c in classes}
        assert "shapes.Shape" in class_names
        assert "shapes.Circle" in class_names
        assert "shapes.Rectangle" in class_names

    def test_abstract_method_decorator(self) -> None:
        """Abstract methods should have their decorators captured."""
        source = _load_fixture("shapes.py")
        result = parse_file(source, "shapes.py")
        area = next(n for n in result.nodes if n.name == "shapes.Shape.area")
        assert "abstractmethod" in area.decorators


class TestNestedDefinitions:
    """Test parsing of nested classes and functions."""

    def test_nested_class(self) -> None:
        """Inner classes should be extracted with qualified names."""
        source = _load_fixture("nested.py")
        result = parse_file(source, "nested.py")
        classes = [n for n in result.nodes if n.node_type == "Class"]
        class_names = {c.name for c in classes}
        assert "nested.Outer" in class_names
        assert "nested.Outer.Inner" in class_names

    def test_nested_function(self) -> None:
        """Nested functions should be extracted."""
        source = _load_fixture("nested.py")
        result = parse_file(source, "nested.py")
        functions = [n for n in result.nodes if n.node_type == "Function"]
        func_names = {f.name for f in functions}
        assert "nested.top_level_func" in func_names
        assert "nested.top_level_func.nested_func" in func_names

    def test_static_method_decorator(self) -> None:
        """Static methods should have staticmethod decorator."""
        source = _load_fixture("nested.py")
        result = parse_file(source, "nested.py")
        static = next(n for n in result.nodes if n.name == "nested.Outer.static_method")
        assert "staticmethod" in static.decorators


class TestAsyncFunctions:
    """Test async function detection."""

    def test_async_function(self) -> None:
        """Async functions should be flagged."""
        source = _load_fixture("utils.py")
        result = parse_file(source, "utils.py")
        fetch = next(n for n in result.nodes if n.name == "utils.fetch_data")
        assert fetch.is_async is True

    def test_sync_function_not_async(self) -> None:
        """Regular functions should not be flagged as async."""
        source = _load_fixture("utils.py")
        result = parse_file(source, "utils.py")
        validate = next(n for n in result.nodes if n.name == "utils.validate_positive")
        assert validate.is_async is False


class TestDecorators:
    """Test decorator extraction."""

    def test_lru_cache_decorator(self) -> None:
        """Parameterized decorators should be extracted."""
        source = _load_fixture("decorators.py")
        result = parse_file(source, "decorators.py")
        cached = next(n for n in result.nodes if n.name == "decorators.cached_compute")
        assert any("lru_cache" in d for d in cached.decorators)

    def test_property_decorator(self) -> None:
        """Property decorator should be captured."""
        source = _load_fixture("decorators.py")
        result = parse_file(source, "decorators.py")
        prop = next(n for n in result.nodes if n.name == "decorators.MyClass.my_property")
        assert "property" in prop.decorators


class TestLineNumbers:
    """Test that line numbers are correct."""

    def test_function_line_range(self) -> None:
        """Function start and end lines should be accurate."""
        source = _load_fixture("utils.py")
        result = parse_file(source, "utils.py")
        validate = next(n for n in result.nodes if n.name == "utils.validate_positive")
        assert validate.start_line > 0
        assert validate.end_line >= validate.start_line

    def test_module_spans_whole_file(self) -> None:
        """Module node should span the entire file."""
        source = _load_fixture("utils.py")
        result = parse_file(source, "utils.py")
        module = next(n for n in result.nodes if n.node_type == "Module")
        assert module.start_line == 1


class TestSourceText:
    """Test source_text capture."""

    def test_function_source_text(self) -> None:
        """Function source_text should contain the full function definition."""
        source = _load_fixture("calculator.py")
        result = parse_file(source, "calculator.py")
        add = next(n for n in result.nodes if n.name == "calculator.Calculator.add")
        assert "def add" in add.source_text
        assert "return self.value" in add.source_text
