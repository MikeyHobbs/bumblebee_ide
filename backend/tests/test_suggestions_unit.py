"""Unit tests for suggestion helpers — no FalkorDB required.

Tests ``_build_snippet`` and ``_node_to_completion`` from the suggestions
router in isolation.
"""

from __future__ import annotations

import pytest

from app.routers.suggestions import _build_snippet, _node_to_completion


# ---------------------------------------------------------------------------
# _build_snippet
# ---------------------------------------------------------------------------


class TestBuildSnippet:
    """Verify snippet generation for Monaco insertText."""

    def test_two_params(self) -> None:
        result = _build_snippet("authenticate", [{"name": "email"}, {"name": "password"}])
        assert result == "authenticate(${1:email}, ${2:password})"

    def test_no_params(self) -> None:
        result = _build_snippet("generate_id", [])
        assert result == "generate_id()"

    def test_self_filtered(self) -> None:
        result = _build_snippet("add", [{"name": "self"}, {"name": "x"}])
        assert result == "add(${1:x})"

    def test_only_self(self) -> None:
        result = _build_snippet("total", [{"name": "self"}])
        assert result == "total()"

    def test_params_as_json_string(self) -> None:
        result = _build_snippet("func", '[{"name":"a"},{"name":"b"}]')
        assert result == "func(${1:a}, ${2:b})"

    def test_invalid_json_string_fallback(self) -> None:
        result = _build_snippet("func", "invalid json")
        assert result == "func()"

    def test_none_params(self) -> None:
        result = _build_snippet("func", None)
        assert result == "func()"

    def test_cls_filtered(self) -> None:
        result = _build_snippet("create", [{"name": "cls"}, {"name": "data"}])
        assert result == "create(${1:data})"


# ---------------------------------------------------------------------------
# _node_to_completion
# ---------------------------------------------------------------------------


class TestNodeToCompletion:
    """Verify node → CompletionItem mapping."""

    def test_function_with_params(self) -> None:
        props = {
            "name": "services.authenticate",
            "kind": "function",
            "signature": "authenticate(email, password)",
            "params": [{"name": "email"}, {"name": "password"}],
            "return_type": "str",
            "module_path": "services/py.py",
            "id": "node-1",
        }
        item = _node_to_completion(props)
        assert item.label == "authenticate"
        assert item.kind == "function"
        assert item.insert_text == "authenticate(${1:email}, ${2:password})"
        assert "services/py.py" in item.documentation
        assert "str" in item.documentation

    def test_class_no_snippet(self) -> None:
        props = {
            "name": "Order",
            "kind": "class",
            "signature": "class Order",
            "params": [],
            "return_type": "",
            "module_path": "models/py.py",
            "id": "node-2",
        }
        item = _node_to_completion(props)
        assert item.insert_text == "Order"
        assert item.kind == "class"

    def test_kind_override(self) -> None:
        props = {
            "name": "add_item",
            "kind": "function",
            "signature": "add_item(self, product, quantity)",
            "params": [{"name": "self"}, {"name": "product"}, {"name": "quantity"}],
            "return_type": "",
            "module_path": "models/py.py",
            "id": "node-3",
        }
        item = _node_to_completion(props, kind_override="method")
        assert item.kind == "method"
        assert item.insert_text == "add_item(${1:product}, ${2:quantity})"

    def test_sort_prefix(self) -> None:
        props = {"name": "foo", "kind": "function", "id": "n1"}
        item_a = _node_to_completion(props, sort_prefix="a")
        item_b = _node_to_completion(props, sort_prefix="b")
        assert item_a.sort_key.startswith("a_")
        assert item_b.sort_key.startswith("b_")

    def test_empty_props_graceful(self) -> None:
        item = _node_to_completion({})
        assert item.label == ""
        assert item.node_id == ""
        assert item.insert_text == "()"
