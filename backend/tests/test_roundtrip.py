"""Round-trip tests: parse -> extract -> generate -> validate.

These tests verify that the code generator produces valid Python from the
extraction pipeline output. The generated code is validated using tree-sitter
to ensure it parses without syntax errors.

Known limitations (documented in docs/codegen-limitations.md):
- Comments are lost (tree-sitter does not preserve comments in named nodes)
- Blank lines between statements may differ from the original
- Formatting may differ (indentation is reconstructed, not preserved byte-for-byte)
- Decorator order is preserved but decorator formatting may vary
"""

from __future__ import annotations

import os

import pytest
import tree_sitter
import tree_sitter_python

from app.services.ast_parser import ParseResult, parse_file, _get_parser
from app.services.statement_extractor import extract_statements, StatementResult
from app.services.code_generator import generate_from_extractions, generate_function


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "roundtrip")


def _get_fixture_files() -> list[str]:
    """Collect all Python fixture files in the roundtrip directory.

    Returns:
        Sorted list of .py filenames (excluding __init__.py).
    """
    files = [
        f for f in os.listdir(FIXTURES_DIR)
        if f.endswith(".py") and f != "__init__.py"
    ]
    return sorted(files)


def _has_error_nodes(node: tree_sitter.Node) -> list[str]:
    """Recursively find all ERROR nodes in a tree-sitter parse tree.

    Args:
        node: The root node to check.

    Returns:
        List of error descriptions (empty if no errors).
    """
    errors: list[str] = []
    if node.type == "ERROR":
        text_preview = node.text.decode("utf-8")[:80] if node.text else "<empty>"
        errors.append(
            f"ERROR at line {node.start_point[0] + 1}, col {node.start_point[1]}: {text_preview!r}"
        )
    for child in node.children:
        errors.extend(_has_error_nodes(child))
    return errors


def _validate_generated_source(source: str) -> list[str]:
    """Parse generated source with tree-sitter and return any errors.

    Args:
        source: Python source code to validate.

    Returns:
        List of error descriptions (empty if valid).
    """
    parser = _get_parser()
    tree = parser.parse(source.encode("utf-8"))
    return _has_error_nodes(tree.root_node)


def _count_named_children_of_type(node: tree_sitter.Node, node_type: str) -> int:
    """Count named children of a specific type recursively.

    Args:
        node: The root node to search.
        node_type: The tree-sitter node type to count.

    Returns:
        Count of matching nodes.
    """
    count = 0
    if node.type == node_type:
        count += 1
    for child in node.children:
        count += _count_named_children_of_type(child, node_type)
    return count


def _extract_function_names(node: tree_sitter.Node) -> list[str]:
    """Extract all function definition names from a tree-sitter tree.

    Args:
        node: The root node to search.

    Returns:
        Sorted list of function names.
    """
    names: list[str] = []
    if node.type == "function_definition":
        name_node = node.child_by_field_name("name")
        if name_node:
            names.append(name_node.text.decode("utf-8"))
    for child in node.children:
        names.extend(_extract_function_names(child))
    return sorted(names)


def _extract_class_names(node: tree_sitter.Node) -> list[str]:
    """Extract all class definition names from a tree-sitter tree.

    Args:
        node: The root node to search.

    Returns:
        Sorted list of class names.
    """
    names: list[str] = []
    if node.type == "class_definition":
        name_node = node.child_by_field_name("name")
        if name_node:
            names.append(name_node.text.decode("utf-8"))
    for child in node.children:
        names.extend(_extract_class_names(child))
    return sorted(names)


FIXTURE_FILES = _get_fixture_files()


class TestRoundTripGeneration:
    """Test that parse -> extract -> generate produces valid Python."""

    @pytest.mark.parametrize("fixture_file", FIXTURE_FILES)
    def test_generated_source_parses_without_errors(self, fixture_file: str) -> None:
        """Generated source should parse without tree-sitter ERROR nodes.

        Steps:
            1. Read original source
            2. Parse with ast_parser -> ParseResult
            3. Extract statements with statement_extractor
            4. Generate source from extractions
            5. Validate generated source with tree-sitter
        """
        filepath = os.path.join(FIXTURES_DIR, fixture_file)
        with open(filepath, encoding="utf-8") as f:
            original_source = f.read()

        parse_result = parse_file(original_source, fixture_file)
        stmt_result = extract_statements(original_source, fixture_file, parse_result.nodes)
        generated_source = generate_from_extractions(parse_result, stmt_result)

        errors = _validate_generated_source(generated_source)
        assert not errors, (
            f"Generated source for {fixture_file} has parse errors:\n"
            + "\n".join(errors)
            + f"\n\nGenerated source:\n{generated_source}"
        )

    @pytest.mark.parametrize("fixture_file", FIXTURE_FILES)
    def test_generated_source_preserves_function_names(self, fixture_file: str) -> None:
        """Generated source should contain the same function definitions."""
        filepath = os.path.join(FIXTURES_DIR, fixture_file)
        with open(filepath, encoding="utf-8") as f:
            original_source = f.read()

        parser = _get_parser()
        original_tree = parser.parse(original_source.encode("utf-8"))
        original_funcs = _extract_function_names(original_tree.root_node)

        parse_result = parse_file(original_source, fixture_file)
        stmt_result = extract_statements(original_source, fixture_file, parse_result.nodes)
        generated_source = generate_from_extractions(parse_result, stmt_result)

        generated_tree = parser.parse(generated_source.encode("utf-8"))
        generated_funcs = _extract_function_names(generated_tree.root_node)

        assert original_funcs == generated_funcs, (
            f"Function names differ for {fixture_file}:\n"
            f"  Original: {original_funcs}\n"
            f"  Generated: {generated_funcs}"
        )

    @pytest.mark.parametrize("fixture_file", FIXTURE_FILES)
    def test_generated_source_preserves_class_names(self, fixture_file: str) -> None:
        """Generated source should contain the same class definitions."""
        filepath = os.path.join(FIXTURES_DIR, fixture_file)
        with open(filepath, encoding="utf-8") as f:
            original_source = f.read()

        parser = _get_parser()
        original_tree = parser.parse(original_source.encode("utf-8"))
        original_classes = _extract_class_names(original_tree.root_node)

        parse_result = parse_file(original_source, fixture_file)
        stmt_result = extract_statements(original_source, fixture_file, parse_result.nodes)
        generated_source = generate_from_extractions(parse_result, stmt_result)

        generated_tree = parser.parse(generated_source.encode("utf-8"))
        generated_classes = _extract_class_names(generated_tree.root_node)

        assert original_classes == generated_classes, (
            f"Class names differ for {fixture_file}:\n"
            f"  Original: {original_classes}\n"
            f"  Generated: {generated_classes}"
        )


class TestGenerateFunction:
    """Test single function generation."""

    def test_generate_simple_function(self) -> None:
        """Generate a single function from extraction results."""
        source = """def add(a: int, b: int) -> int:
    result = a + b
    return result
"""
        parse_result = parse_file(source, "test.py")
        stmt_result = extract_statements(source, "test.py", parse_result.nodes)
        result = generate_function("test.add", parse_result, stmt_result)
        errors = _validate_generated_source(result)
        assert not errors, f"Generated function has parse errors: {errors}\n{result}"

    def test_generate_function_preserves_signature(self) -> None:
        """Generated function should preserve the original signature."""
        source = """def greet(name: str, greeting: str = "Hello") -> str:
    msg = f"{greeting}, {name}!"
    return msg
"""
        parse_result = parse_file(source, "test.py")
        stmt_result = extract_statements(source, "test.py", parse_result.nodes)
        result = generate_function("test.greet", parse_result, stmt_result)
        assert "def greet(" in result
        assert "name: str" in result

    def test_generate_function_not_found(self) -> None:
        """Should raise NodeNotFoundError for missing function."""
        source = """def foo():
    pass
"""
        parse_result = parse_file(source, "test.py")
        stmt_result = extract_statements(source, "test.py", parse_result.nodes)
        with pytest.raises(Exception):
            generate_function("test.nonexistent", parse_result, stmt_result)


class TestGenerateFromExtractions:
    """Test full module generation from extractions."""

    def test_simple_module(self) -> None:
        """Generate a simple module with one function."""
        source = """def hello() -> str:
    return "hello"
"""
        parse_result = parse_file(source, "test.py")
        stmt_result = extract_statements(source, "test.py", parse_result.nodes)
        result = generate_from_extractions(parse_result, stmt_result)
        errors = _validate_generated_source(result)
        assert not errors, f"Generated source has errors: {errors}\n{result}"

    def test_module_with_class(self) -> None:
        """Generate a module with a class."""
        source = """class Foo:
    \"\"\"A foo class.\"\"\"

    def bar(self) -> int:
        return 42
"""
        parse_result = parse_file(source, "test.py")
        stmt_result = extract_statements(source, "test.py", parse_result.nodes)
        result = generate_from_extractions(parse_result, stmt_result)
        errors = _validate_generated_source(result)
        assert not errors, f"Generated source has errors: {errors}\n{result}"
        assert "class Foo" in result
        assert "def bar" in result

    def test_module_with_control_flow(self) -> None:
        """Generate a module with control flow statements."""
        source = """def process(x: int) -> str:
    if x > 0:
        return "positive"
    elif x < 0:
        return "negative"
    else:
        return "zero"
"""
        parse_result = parse_file(source, "test.py")
        stmt_result = extract_statements(source, "test.py", parse_result.nodes)
        result = generate_from_extractions(parse_result, stmt_result)
        errors = _validate_generated_source(result)
        assert not errors, f"Generated source has errors: {errors}\n{result}"

    def test_module_with_nested_control_flow(self) -> None:
        """Generate a module with nested control flow."""
        source = """def nested(items: list) -> list:
    results = []
    for item in items:
        if item > 0:
            results.append(item)
        else:
            results.append(0)
    return results
"""
        parse_result = parse_file(source, "test.py")
        stmt_result = extract_statements(source, "test.py", parse_result.nodes)
        result = generate_from_extractions(parse_result, stmt_result)
        errors = _validate_generated_source(result)
        assert not errors, f"Generated source has errors: {errors}\n{result}"

    def test_module_with_try_except(self) -> None:
        """Generate a module with try/except/else/finally."""
        source = """def safe_divide(a: int, b: int) -> float:
    try:
        result = a / b
    except ZeroDivisionError:
        result = 0.0
    else:
        result = round(result, 2)
    finally:
        pass
    return result
"""
        parse_result = parse_file(source, "test.py")
        stmt_result = extract_statements(source, "test.py", parse_result.nodes)
        result = generate_from_extractions(parse_result, stmt_result)
        errors = _validate_generated_source(result)
        assert not errors, f"Generated source has errors: {errors}\n{result}"
