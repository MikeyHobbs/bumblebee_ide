"""Tests for the hash-based identity system in app.services.hash_identity."""

from __future__ import annotations

from app.services.analysis.hash_identity import (
    compute_ast_hash,
    detect_signature_change,
    extract_params_detailed,
    extract_return_type,
    extract_signature_text,
    generate_node_id,
)


class TestComputeAstHash:
    """Tests for compute_ast_hash determinism, comment stripping, and whitespace normalization."""

    def test_determinism_same_source_same_hash(self) -> None:
        """Identical source text must produce the same hash on every call."""
        source = "def add(a: int, b: int) -> int:\n    return a + b\n"
        assert compute_ast_hash(source) == compute_ast_hash(source)

    def test_comment_stripping(self) -> None:
        """Adding or removing comments must not change the hash."""
        without_comments = "def add(a: int, b: int) -> int:\n    return a + b\n"
        with_comments = (
            "# This adds two numbers\n"
            "def add(a: int, b: int) -> int:\n"
            "    # perform addition\n"
            "    return a + b  # inline comment\n"
        )
        assert compute_ast_hash(without_comments) == compute_ast_hash(with_comments)

    def test_whitespace_normalization(self) -> None:
        """Reformatted code (extra blank lines, indentation changes) must produce the same hash."""
        compact = "def add(a: int, b: int) -> int:\n    return a + b\n"
        spacious = (
            "def add(a: int, b: int) -> int:\n"
            "\n"
            "\n"
            "    return a + b\n"
            "\n"
        )
        assert compute_ast_hash(compact) == compute_ast_hash(spacious)

    def test_different_logic_different_hash(self) -> None:
        """Different logic must produce different hashes."""
        source_a = "def add(a: int, b: int) -> int:\n    return a + b\n"
        source_b = "def add(a: int, b: int) -> int:\n    return a - b\n"
        assert compute_ast_hash(source_a) != compute_ast_hash(source_b)

    def test_docstring_stripping(self) -> None:
        """Docstrings should be stripped and not affect the hash."""
        without_doc = "def add(a: int, b: int) -> int:\n    return a + b\n"
        with_doc = 'def add(a: int, b: int) -> int:\n    """Add two numbers."""\n    return a + b\n'
        assert compute_ast_hash(without_doc) == compute_ast_hash(with_doc)


class TestDetectSignatureChange:
    """Tests for detect_signature_change comparing function signatures."""

    def test_no_change_returns_false(self) -> None:
        """Identical signatures must return False."""
        source = "def greet(name: str) -> str:\n    return f'Hello {name}'\n"
        assert detect_signature_change(source, source) is False

    def test_changed_param_name_returns_true(self) -> None:
        """Renaming a parameter must be detected as a signature change."""
        old = "def greet(name: str) -> str:\n    return f'Hello {name}'\n"
        new = "def greet(user: str) -> str:\n    return f'Hello {user}'\n"
        assert detect_signature_change(old, new) is True

    def test_changed_return_type_returns_true(self) -> None:
        """Changing the return type annotation must be detected."""
        old = "def greet(name: str) -> str:\n    return f'Hello {name}'\n"
        new = "def greet(name: str) -> bytes:\n    return f'Hello {name}'.encode()\n"
        assert detect_signature_change(old, new) is True

    def test_body_only_change_returns_false(self) -> None:
        """Changing only the function body must not be detected as a signature change."""
        old = "def greet(name: str) -> str:\n    return f'Hello {name}'\n"
        new = "def greet(name: str) -> str:\n    return f'Hi {name}'\n"
        assert detect_signature_change(old, new) is False


class TestExtractSignatureText:
    """Tests for extract_signature_text extracting full signature lines."""

    def test_extracts_function_signature(self) -> None:
        """Must extract the 'def ...' signature without the body."""
        source = "def foo(x: int) -> bool:\n    return x > 0\n"
        sig = extract_signature_text(source)
        assert "def foo(x: int) -> bool" in sig

    def test_extracts_class_signature(self) -> None:
        """Must extract the 'class ...' signature."""
        source = "class MyClass(Base):\n    pass\n"
        sig = extract_signature_text(source)
        assert "class MyClass(Base)" in sig

    def test_multiline_signature_collapsed(self) -> None:
        """Multi-line signatures should be collapsed to a single line."""
        source = "def long_func(\n    a: int,\n    b: str,\n) -> bool:\n    return True\n"
        sig = extract_signature_text(source)
        assert "\n" not in sig
        assert "a: int" in sig
        assert "b: str" in sig


class TestExtractReturnType:
    """Tests for extract_return_type extracting return annotations."""

    def test_extracts_return_type(self) -> None:
        """Must extract the annotated return type."""
        source = "def foo(x: int) -> bool:\n    return x > 0\n"
        assert extract_return_type(source) == "bool"

    def test_returns_none_when_missing(self) -> None:
        """Must return None when there is no return type annotation."""
        source = "def foo(x):\n    return x\n"
        assert extract_return_type(source) is None

    def test_complex_return_type(self) -> None:
        """Must extract complex return types."""
        source = "def foo() -> list[dict[str, int]]:\n    return []\n"
        result = extract_return_type(source)
        assert result is not None
        assert "list" in result


class TestExtractParamsDetailed:
    """Tests for extract_params_detailed extracting parameter specifications."""

    def test_positional_or_keyword(self) -> None:
        """Basic typed parameters are positional_or_keyword."""
        source = "def foo(x: int, y: str) -> None:\n    pass\n"
        params = extract_params_detailed(source)
        assert len(params) == 2
        assert params[0]["name"] == "x"
        assert params[0]["type_hint"] == "int"
        assert params[0]["kind"] == "positional_or_keyword"
        assert params[1]["name"] == "y"
        assert params[1]["type_hint"] == "str"

    def test_default_value(self) -> None:
        """Parameters with defaults must capture the default."""
        source = "def foo(x: int = 5) -> None:\n    pass\n"
        params = extract_params_detailed(source)
        assert len(params) == 1
        assert params[0]["name"] == "x"
        assert params[0]["default"] == "5"

    def test_var_positional(self) -> None:
        """*args parameter must have kind var_positional."""
        source = "def foo(*args) -> None:\n    pass\n"
        params = extract_params_detailed(source)
        assert len(params) == 1
        assert params[0]["name"] == "args"
        assert params[0]["kind"] == "var_positional"

    def test_var_keyword(self) -> None:
        """**kwargs parameter must have kind var_keyword."""
        source = "def foo(**kwargs) -> None:\n    pass\n"
        params = extract_params_detailed(source)
        assert len(params) == 1
        assert params[0]["name"] == "kwargs"
        assert params[0]["kind"] == "var_keyword"

    def test_no_params(self) -> None:
        """Function with no parameters must return empty list (excluding self)."""
        source = "def foo() -> None:\n    pass\n"
        params = extract_params_detailed(source)
        assert params == []

    def test_no_function_returns_empty(self) -> None:
        """Non-function source must return empty list."""
        source = "x = 42\n"
        params = extract_params_detailed(source)
        assert params == []


class TestGenerateNodeId:
    """Tests for generate_node_id UUID7 generation."""

    def test_returns_string(self) -> None:
        """Must return a string."""
        result = generate_node_id()
        assert isinstance(result, str)

    def test_unique_each_call(self) -> None:
        """Successive calls must produce different IDs."""
        id1 = generate_node_id()
        id2 = generate_node_id()
        assert id1 != id2

    def test_uuid_format(self) -> None:
        """Must look like a UUID (contains hyphens, correct length)."""
        result = generate_node_id()
        parts = result.split("-")
        assert len(parts) == 5
        assert len(result) == 36
