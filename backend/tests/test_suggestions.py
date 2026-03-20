"""Integration tests for the /api/v1/suggestions/complete endpoint.

Requires FalkorDB running with sample_app imported. Follows the same
fixture pattern as test_cypher_examples.py.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.graph.client import get_graph, init_client
from app.main import app


@pytest.fixture(scope="module", autouse=True)
def _init_graph():
    """Initialize the FalkorDB client; skip if unavailable or empty."""
    try:
        init_client()
        g = get_graph()
        result = g.query("MATCH (n:LogicNode) RETURN count(n)")
        count = result.result_set[0][0] if result.result_set else 0
        if count == 0:
            pytest.skip("FalkorDB graph is empty — import sample_app first")
    except Exception as exc:
        pytest.skip(f"FalkorDB not available: {exc}")


@pytest.fixture(scope="module")
def client() -> TestClient:
    """FastAPI test client."""
    return TestClient(app)


def _post(client: TestClient, body: dict[str, Any]) -> Any:
    """Helper: POST to the suggestions endpoint and return parsed JSON."""
    resp = client.post("/api/v1/suggestions/complete", json=body)
    return resp


# ---------------------------------------------------------------------------
# General trigger
# ---------------------------------------------------------------------------


class TestGeneralTrigger:
    """trigger="general" — fuzzy name search."""

    def test_auth_returns_authenticate(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "general", "query": "auth"})
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        labels = {i["label"] for i in items}
        assert any("authenticate" in l for l in labels)

    def test_all_items_have_required_fields(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "general", "query": "validate"})
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 2
        for item in items:
            for field in ("node_id", "label", "insert_text", "kind", "detail", "documentation", "sort_key", "module_path"):
                assert field in item, f"Missing field: {field}"
            assert item["kind"] in ("function", "method", "class")

    def test_empty_query_returns_empty(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "general", "query": ""})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_limit_respected(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "general", "query": "a", "limit": 1})
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) <= 1


# ---------------------------------------------------------------------------
# Member access trigger
# ---------------------------------------------------------------------------


class TestMemberAccessTrigger:
    """trigger="member_access" — class method/attribute lookup."""

    def test_order_members(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "member_access", "object_name": "Order"})
        assert resp.status_code == 200
        items = resp.json()
        labels = {i["label"] for i in items}
        assert "add_item" in labels or "total" in labels, f"Expected Order methods, got {labels}"

    def test_member_kind_is_method(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "member_access", "object_name": "Order"})
        items = resp.json()
        for item in items:
            assert item["kind"] == "method", f"Expected 'method', got '{item['kind']}' for {item['label']}"

    def test_add_item_insert_text_is_callable(self, client: TestClient) -> None:
        """Member access items should have callable insert_text (name with parens)."""
        resp = _post(client, {"trigger": "member_access", "object_name": "Order"})
        items = resp.json()
        add_items = [i for i in items if i["label"] == "add_item"]
        if add_items:
            # FIND_CLASS_MEMBERS doesn't return params, so snippet has no placeholders
            assert "add_item(" in add_items[0]["insert_text"]

    def test_user_members(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "member_access", "object_name": "User"})
        assert resp.status_code == 200
        items = resp.json()
        labels = {i["label"] for i in items}
        assert "full_name" in labels or "is_active" in labels, f"Expected User methods, got {labels}"

    def test_nonexistent_class_returns_empty(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "member_access", "object_name": "NonExistentClass"})
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Import trigger
# ---------------------------------------------------------------------------


class TestImportTrigger:
    """trigger="import" — module-based function discovery."""

    def test_services_prefix(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "import", "module_prefix": "services"})
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 3
        labels = {i["label"] for i in items}
        assert "authenticate" in labels or "register_user" in labels or "place_order" in labels, (
            f"Expected service functions, got {labels}"
        )

    def test_services_module_path_filter(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "import", "module_prefix": "services"})
        items = resp.json()
        for item in items:
            assert "services" in item["module_path"].lower() or "services" in item["label"].lower(), (
                f"Item {item['label']} module_path '{item['module_path']}' doesn't match services"
            )

    def test_auth_prefix(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "import", "module_prefix": "auth"})
        assert resp.status_code == 200
        items = resp.json()
        labels = {i["label"] for i in items}
        expected_any = {"hash_password", "verify_password", "create_token", "validate_token"}
        assert labels & expected_any, f"Expected auth functions, got {labels}"


# ---------------------------------------------------------------------------
# Variable consumer trigger
# ---------------------------------------------------------------------------


class TestVariableConsumerTrigger:
    """trigger="variable_consumer" — find functions accepting a given variable."""

    def test_password_consumers(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "variable_consumer", "variable_name": "password"})
        assert resp.status_code == 200
        items = resp.json()
        # Should find at least one function that accepts a "password" param
        assert len(items) >= 1, "Expected at least one consumer for 'password'"
        # All items should be well-formed
        for item in items:
            assert item["node_id"]
            assert item["label"]

    def test_email_consumers(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "variable_consumer", "variable_name": "email"})
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1, "Expected at least one consumer for 'email'"

    def test_no_match_returns_empty(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "variable_consumer", "variable_name": "zzz_no_match"})
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Miscellaneous edge-case tests."""

    def test_unknown_trigger_returns_400(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "unknown_trigger", "query": "foo"})
        assert resp.status_code == 400

    def test_completion_item_shape(self, client: TestClient) -> None:
        """Every returned item must have all 8 CompletionItem fields non-null."""
        resp = _post(client, {"trigger": "general", "query": "register"})
        assert resp.status_code == 200
        items = resp.json()
        if items:
            expected_fields = {"label", "kind", "detail", "documentation", "insert_text", "sort_key", "node_id", "module_path"}
            for item in items:
                assert set(item.keys()) == expected_fields, f"Unexpected fields: {set(item.keys())}"
                for k, v in item.items():
                    assert v is not None, f"Field {k} is None"


class TestSnippetQuality:
    """Verify snippet fidelity for well-known functions."""

    def test_register_user_snippet(self, client: TestClient) -> None:
        resp = _post(client, {"trigger": "general", "query": "register_user"})
        assert resp.status_code == 200
        items = resp.json()
        matches = [i for i in items if i["label"] == "register_user"]
        assert len(matches) >= 1, f"register_user not found in {[i['label'] for i in items]}"
        item = matches[0]
        # Verify snippet has numbered placeholders
        assert "${1:" in item["insert_text"]
        assert "register_user(" in item["insert_text"]
        # Verify detail contains signature
        assert "register_user" in item["detail"]
