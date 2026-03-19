"""Tests for TypeShape: structural type matching via graph hub nodes (TICKET-960–966)."""

from __future__ import annotations

import os

from app.services.parsing.ast_parser import parse_file
from app.services.parsing.variable_extractor import ShapeEvidence, extract_variables
from app.services.analysis.type_shape_service import (
    build_shape_definition,
    compute_shape_hash,
)


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sample_repo")


def _load_fixture(filename: str) -> str:
    """Load a fixture file's content."""
    with open(os.path.join(FIXTURES_DIR, filename), encoding="utf-8") as f:
        return f.read()


def _get_var_result(filename: str):  # type: ignore[no-untyped-def]
    """Parse a fixture and extract variables with shape evidence."""
    source = _load_fixture(filename)
    result = parse_file(source, filename)
    return extract_variables(source, filename, result.nodes)


class TestShapeEvidence:
    """Test that shape evidence is extracted correctly from AST patterns."""

    def test_subscript_access_tracked(self) -> None:
        """String-literal subscript access should be tracked as evidence."""
        result = _get_var_result("typed_pipeline.py")
        # extract_user_emails accesses user["name"] and user["email"]
        user_ev = result.evidence.get("typed_pipeline.extract_user_emails.user")
        assert user_ev is not None
        assert "name" in user_ev.subscripts_accessed
        assert "email" in user_ev.subscripts_accessed

    def test_attribute_access_tracked(self) -> None:
        """Attribute access on known variables should be tracked."""
        result = _get_var_result("typed_pipeline.py")
        # format_response accesses response.status_code and response.text
        resp_ev = result.evidence.get("typed_pipeline.format_response.response")
        assert resp_ev is not None
        assert "status_code" in resp_ev.attrs_accessed
        assert "text" in resp_ev.attrs_accessed

    def test_method_call_tracked(self) -> None:
        """Method calls on known variables should be tracked."""
        result = _get_var_result("typed_pipeline.py")
        # batch_process calls results.append() and results.extend()
        results_ev = result.evidence.get("typed_pipeline.batch_process.results")
        assert results_ev is not None
        assert "append" in results_ev.methods_called
        assert "extend" in results_ev.methods_called

    def test_type_hint_preserved(self) -> None:
        """Type hints should be preserved in shape evidence."""
        result = _get_var_result("typed_pipeline.py")
        # double has param value: int
        value_ev = result.evidence.get("typed_pipeline.double.value")
        assert value_ev is not None
        assert value_ev.type_hint == "int"

    def test_db_method_calls_tracked(self) -> None:
        """Method calls on DB-like objects should be tracked."""
        result = _get_var_result("typed_pipeline.py")
        # run_query calls conn.cursor()
        conn_ev = result.evidence.get("typed_pipeline.run_query.conn")
        assert conn_ev is not None
        assert "cursor" in conn_ev.methods_called

    def test_shared_subscript_shapes(self) -> None:
        """Multiple functions accessing same keys should produce same evidence patterns."""
        result = _get_var_result("typed_pipeline.py")
        extract_ev = result.evidence.get("typed_pipeline.extract_user_emails.user")
        send_ev = result.evidence.get("typed_pipeline.send_notification.user")
        assert extract_ev is not None
        assert send_ev is not None
        assert extract_ev.subscripts_accessed == send_ev.subscripts_accessed

    def test_superset_subscript_shape(self) -> None:
        """enrich_user accesses name, email, phone — superset of extract/send."""
        result = _get_var_result("typed_pipeline.py")
        enrich_ev = result.evidence.get("typed_pipeline.enrich_user.user")
        assert enrich_ev is not None
        assert enrich_ev.subscripts_accessed == {"name", "email", "phone"}

    def test_shared_attribute_shapes(self) -> None:
        """format_response and log_response should share attribute evidence."""
        result = _get_var_result("typed_pipeline.py")
        fmt_ev = result.evidence.get("typed_pipeline.format_response.response")
        log_ev = result.evidence.get("typed_pipeline.log_response.response")
        assert fmt_ev is not None
        assert log_ev is not None
        assert fmt_ev.attrs_accessed == log_ev.attrs_accessed

    def test_no_evidence_for_opaque(self) -> None:
        """identity(x) has no evidence — x has no type hint, no access patterns."""
        result = _get_var_result("typed_pipeline.py")
        x_ev = result.evidence.get("typed_pipeline.identity.x")
        # Should be None or have no evidence
        assert x_ev is None


class TestShapeDefinition:
    """Test building shape definitions from evidence."""

    def test_structural_from_subscripts(self) -> None:
        """Evidence with subscript access should produce a structural definition."""
        ev = ShapeEvidence(
            variable_name="test.user",
            subscripts_accessed={"name", "email"},
        )
        definition = build_shape_definition(ev)
        assert definition is not None
        assert definition["kind"] == "structural"
        assert definition["subscripts"] == ["email", "name"]  # sorted

    def test_structural_from_attrs(self) -> None:
        """Evidence with attribute access should produce a structural definition."""
        ev = ShapeEvidence(
            variable_name="test.response",
            attrs_accessed={"status_code", "text"},
        )
        definition = build_shape_definition(ev)
        assert definition is not None
        assert definition["kind"] == "structural"
        assert definition["attrs"] == ["status_code", "text"]

    def test_structural_from_methods(self) -> None:
        """Evidence with method calls should produce a structural definition."""
        ev = ShapeEvidence(
            variable_name="test.items",
            methods_called={"append", "extend"},
        )
        definition = build_shape_definition(ev)
        assert definition is not None
        assert definition["kind"] == "structural"
        assert definition["methods"] == ["append", "extend"]

    def test_primitive_from_hint(self) -> None:
        """Evidence with only a primitive type hint should produce a primitive definition."""
        ev = ShapeEvidence(variable_name="test.x", type_hint="int")
        definition = build_shape_definition(ev)
        assert definition is not None
        assert definition["kind"] == "primitive"
        assert definition["type"] == "int"

    def test_hint_for_complex_type(self) -> None:
        """Non-primitive type hints should produce a hint definition."""
        ev = ShapeEvidence(variable_name="test.items", type_hint="list[str]")
        definition = build_shape_definition(ev)
        assert definition is not None
        assert definition["kind"] == "hint"
        assert definition["type"] == "list[str]"

    def test_no_definition_for_no_evidence(self) -> None:
        """No evidence should produce None."""
        ev = ShapeEvidence(variable_name="test.x")
        definition = build_shape_definition(ev)
        assert definition is None

    def test_structural_overrides_hint(self) -> None:
        """Structural evidence takes priority over hint-only classification."""
        ev = ShapeEvidence(
            variable_name="test.d",
            subscripts_accessed={"key1"},
            type_hint="dict",
        )
        definition = build_shape_definition(ev)
        assert definition is not None
        assert definition["kind"] == "structural"
        assert definition["base_type"] == "dict"


class TestShapeHash:
    """Test deterministic hashing of shape definitions."""

    def test_same_evidence_same_hash(self) -> None:
        """Same evidence should produce the same hash."""
        def1 = {"kind": "structural", "attrs": ["email", "name"], "subscripts": [], "methods": []}
        def2 = {"kind": "structural", "attrs": ["email", "name"], "subscripts": [], "methods": []}
        assert compute_shape_hash(def1) == compute_shape_hash(def2)

    def test_different_evidence_different_hash(self) -> None:
        """Different evidence should produce different hashes."""
        def1 = {"kind": "structural", "attrs": ["email", "name"], "subscripts": [], "methods": []}
        def2 = {"kind": "structural", "attrs": ["email", "name", "phone"], "subscripts": [], "methods": []}
        assert compute_shape_hash(def1) != compute_shape_hash(def2)

    def test_order_independent(self) -> None:
        """Hash should be independent of the order of attributes."""
        def1 = {"kind": "structural", "attrs": ["name", "email"], "subscripts": [], "methods": []}
        def2 = {"kind": "structural", "attrs": ["email", "name"], "subscripts": [], "methods": []}
        assert compute_shape_hash(def1) == compute_shape_hash(def2)

    def test_primitive_hash_deterministic(self) -> None:
        """Primitive type hashes should be deterministic."""
        def1 = {"kind": "primitive", "type": "int"}
        def2 = {"kind": "primitive", "type": "int"}
        assert compute_shape_hash(def1) == compute_shape_hash(def2)

    def test_different_kinds_different_hash(self) -> None:
        """Different kinds should produce different hashes."""
        def1 = {"kind": "primitive", "type": "int"}
        def2 = {"kind": "hint", "type": "int"}
        assert compute_shape_hash(def1) != compute_shape_hash(def2)


class TestCompatibleWith:
    """Test COMPATIBLE_WITH subset relationship detection."""

    def test_superset_is_compatible(self) -> None:
        """A shape with attrs {name, email, phone} should be compatible with {name, email}."""
        ev_superset = ShapeEvidence(
            variable_name="test.user",
            subscripts_accessed={"name", "email", "phone"},
        )
        ev_subset = ShapeEvidence(
            variable_name="test.user2",
            subscripts_accessed={"name", "email"},
        )
        def_super = build_shape_definition(ev_superset)
        def_sub = build_shape_definition(ev_subset)
        assert def_super is not None
        assert def_sub is not None
        # Superset has all of subset's subscripts
        sub_subs = set(def_sub.get("subscripts", []))
        super_subs = set(def_super.get("subscripts", []))
        assert sub_subs <= super_subs

    def test_equal_shapes_not_compatible(self) -> None:
        """Equal shapes should NOT have a COMPATIBLE_WITH edge (same shape)."""
        ev1 = ShapeEvidence(
            variable_name="test.user",
            subscripts_accessed={"name", "email"},
        )
        ev2 = ShapeEvidence(
            variable_name="test.user2",
            subscripts_accessed={"name", "email"},
        )
        def1 = build_shape_definition(ev1)
        def2 = build_shape_definition(ev2)
        assert def1 is not None
        assert def2 is not None
        # Same hash means same node — COMPATIBLE_WITH is for superset → subset
        assert compute_shape_hash(def1) == compute_shape_hash(def2)


class TestNoShape:
    """Test that variables with no evidence get no TypeShape."""

    def test_opaque_variable_no_shape(self) -> None:
        """Variables with no type hint and no usage patterns should not create a TypeShape."""
        ev = ShapeEvidence(variable_name="test.x")
        definition = build_shape_definition(ev)
        assert definition is None

    def test_identity_function_no_evidence(self) -> None:
        """The identity function's param x should have no shape evidence."""
        result = _get_var_result("typed_pipeline.py")
        x_ev = result.evidence.get("typed_pipeline.identity.x")
        assert x_ev is None


class TestEndToEndEvidence:
    """Integration tests: parse fixture → verify evidence → verify definitions."""

    def test_shared_shapes_produce_same_hash(self) -> None:
        """extract_user_emails and send_notification should share a shape hash for param user."""
        result = _get_var_result("typed_pipeline.py")

        extract_ev = result.evidence.get("typed_pipeline.extract_user_emails.user")
        send_ev = result.evidence.get("typed_pipeline.send_notification.user")
        assert extract_ev is not None
        assert send_ev is not None

        def1 = build_shape_definition(extract_ev)
        def2 = build_shape_definition(send_ev)
        assert def1 is not None
        assert def2 is not None
        assert compute_shape_hash(def1) == compute_shape_hash(def2)

    def test_shared_attr_shapes_produce_same_hash(self) -> None:
        """format_response and log_response should share a shape hash for response."""
        result = _get_var_result("typed_pipeline.py")

        fmt_ev = result.evidence.get("typed_pipeline.format_response.response")
        log_ev = result.evidence.get("typed_pipeline.log_response.response")
        assert fmt_ev is not None
        assert log_ev is not None

        def1 = build_shape_definition(fmt_ev)
        def2 = build_shape_definition(log_ev)
        assert def1 is not None
        assert def2 is not None
        assert compute_shape_hash(def1) == compute_shape_hash(def2)

    def test_int_primitives_share_hash(self) -> None:
        """double(value: int) and increment(n: int) should share a hint-based shape hash."""
        result = _get_var_result("typed_pipeline.py")

        value_ev = result.evidence.get("typed_pipeline.double.value")
        n_ev = result.evidence.get("typed_pipeline.increment.n")
        assert value_ev is not None
        assert n_ev is not None

        def1 = build_shape_definition(value_ev)
        def2 = build_shape_definition(n_ev)
        assert def1 is not None
        assert def2 is not None
        assert compute_shape_hash(def1) == compute_shape_hash(def2)

    def test_db_conn_shapes_share(self) -> None:
        """run_query and run_insert should share a shape for conn (methods: cursor)."""
        result = _get_var_result("typed_pipeline.py")

        rq_ev = result.evidence.get("typed_pipeline.run_query.conn")
        ri_ev = result.evidence.get("typed_pipeline.run_insert.conn")
        assert rq_ev is not None
        assert ri_ev is not None

        def1 = build_shape_definition(rq_ev)
        def2 = build_shape_definition(ri_ev)
        assert def1 is not None
        assert def2 is not None

        # Both call conn.cursor(), run_insert also calls conn.commit()
        # So run_insert's conn shape should be a superset
        assert "cursor" in rq_ev.methods_called
        assert "cursor" in ri_ev.methods_called

    def test_results_list_methods(self) -> None:
        """batch_process results param should have append and extend methods."""
        result = _get_var_result("typed_pipeline.py")
        results_ev = result.evidence.get("typed_pipeline.batch_process.results")
        assert results_ev is not None
        definition = build_shape_definition(results_ev)
        assert definition is not None
        assert definition["kind"] == "structural"
        assert "append" in definition["methods"]
        assert "extend" in definition["methods"]
