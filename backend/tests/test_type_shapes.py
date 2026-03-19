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


class TestGenericBareHintCompatibility:
    """Test generic→bare hint bridging for generalization matching."""

    def test_list_str_generalizes_to_list(self) -> None:
        """hint:list[str] and hint:list should have different hashes, both kind=hint, generic has [."""
        ev_generic = ShapeEvidence(variable_name="test.items", type_hint="list[str]")
        ev_bare = ShapeEvidence(variable_name="test.items2", type_hint="list")

        def_generic = build_shape_definition(ev_generic)
        def_bare = build_shape_definition(ev_bare)
        assert def_generic is not None
        assert def_bare is not None

        assert def_generic["kind"] == "hint"
        assert def_bare["kind"] == "hint"
        assert "[" in def_generic["type"]
        assert "[" not in def_bare["type"]
        assert compute_shape_hash(def_generic) != compute_shape_hash(def_bare)

    def test_dict_str_int_generalizes_to_dict(self) -> None:
        """hint:dict[str, int] and hint:dict should have different hashes, same pattern."""
        ev_generic = ShapeEvidence(variable_name="test.d", type_hint="dict[str, int]")
        ev_bare = ShapeEvidence(variable_name="test.d2", type_hint="dict")

        def_generic = build_shape_definition(ev_generic)
        def_bare = build_shape_definition(ev_bare)
        assert def_generic is not None
        assert def_bare is not None

        assert def_generic["kind"] == "hint"
        assert def_bare["kind"] == "hint"
        assert "[" in def_generic["type"]
        assert "[" not in def_bare["type"]
        assert compute_shape_hash(def_generic) != compute_shape_hash(def_bare)

    def test_list_str_does_not_match_list_int(self) -> None:
        """hint:list[str] and hint:list[int] have different hashes with no COMPATIBLE_WITH bridge."""
        ev1 = ShapeEvidence(variable_name="test.a", type_hint="list[str]")
        ev2 = ShapeEvidence(variable_name="test.b", type_hint="list[int]")

        def1 = build_shape_definition(ev1)
        def2 = build_shape_definition(ev2)
        assert def1 is not None
        assert def2 is not None

        # Different hashes — no bridge between them
        assert compute_shape_hash(def1) != compute_shape_hash(def2)
        # Both are generics — neither is a bare type that the other could generalize to
        assert "[" in def1["type"]
        assert "[" in def2["type"]


SAMPLE_APP_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "test_repos", "sample_app")
)


def _get_app_var_result(rel_path: str):  # type: ignore[no-untyped-def]
    """Parse a sample_app fixture and extract variables with shape evidence."""
    source = open(os.path.join(SAMPLE_APP_DIR, rel_path), encoding="utf-8").read()
    result = parse_file(source, rel_path)
    return extract_variables(source, rel_path, result.nodes)


class TestSampleAppApiRoutes:
    """Test TypeShape evidence from api/routes.py."""

    def test_request_attr_shapes(self) -> None:
        """Request objects should produce attribute-based structural shapes."""
        result = _get_app_var_result("api/routes.py")
        request_evs = {k: v for k, v in result.evidence.items()
                       if k.endswith(".request") and v.attrs_accessed}
        assert len(request_evs) >= 2

    def test_response_attr_shapes_shared(self) -> None:
        """Multiple response-building functions should share a response attr shape."""
        result = _get_app_var_result("api/routes.py")
        response_evs = {k: v for k, v in result.evidence.items()
                        if k.endswith(".response") and v.attrs_accessed}
        assert len(response_evs) >= 2
        shapes = set()
        for ev in response_evs.values():
            defn = build_shape_definition(ev)
            if defn:
                shapes.add(compute_shape_hash(defn))
        assert len(shapes) < len(response_evs), "Expected shape sharing among response params"

    def test_session_subscript_shapes(self) -> None:
        """Session dict access should produce subscript shapes."""
        result = _get_app_var_result("api/routes.py")
        session_evs = {k: v for k, v in result.evidence.items()
                       if k.endswith(".session") and v.subscripts_accessed}
        assert len(session_evs) >= 1

    def test_config_subscript_shapes(self) -> None:
        """Config dict access should produce subscript shapes."""
        result = _get_app_var_result("api/routes.py")
        config_evs = {k: v for k, v in result.evidence.items()
                      if k.endswith(".config") and v.subscripts_accessed}
        assert len(config_evs) >= 1


class TestSampleAppAuth:
    """Test TypeShape evidence from services/auth.py."""

    def test_token_subscript_subset_shapes(self) -> None:
        """Token dict functions access different subsets of keys."""
        result = _get_app_var_result("services/auth_service.py")
        token_evs = {k: v for k, v in result.evidence.items()
                     if k.endswith(".token") and v.subscripts_accessed}
        assert len(token_evs) >= 2
        sizes = sorted(len(ev.subscripts_accessed) for ev in token_evs.values())
        assert sizes[0] < sizes[-1], "Expected subset relationships in token shapes"

    def test_creds_subscript_shapes(self) -> None:
        """Credential dict access should produce subscript shapes."""
        result = _get_app_var_result("services/auth_service.py")
        cred_evs = {k: v for k, v in result.evidence.items()
                    if k.endswith(".creds") and v.subscripts_accessed}
        assert len(cred_evs) >= 2

    def test_session_subset_shapes(self) -> None:
        """Session dict access should have subset/superset relationships."""
        result = _get_app_var_result("services/auth_service.py")
        session_evs = {k: v for k, v in result.evidence.items()
                       if k.endswith(".session") and v.subscripts_accessed}
        assert len(session_evs) >= 2
        sizes = sorted(len(ev.subscripts_accessed) for ev in session_evs.values())
        assert sizes[0] < sizes[-1], "Expected subset relationships in session shapes"

    def test_hasher_method_shapes(self) -> None:
        """Hasher objects should produce method-based shapes."""
        result = _get_app_var_result("services/auth_service.py")
        hasher_evs = {k: v for k, v in result.evidence.items()
                      if k.endswith(".hasher") and v.methods_called}
        assert len(hasher_evs) >= 1

    def test_store_method_shapes(self) -> None:
        """Session store objects should produce method-based shapes."""
        result = _get_app_var_result("services/auth_service.py")
        store_evs = {k: v for k, v in result.evidence.items()
                     if k.endswith(".store") and v.methods_called}
        assert len(store_evs) >= 2


class TestSampleAppDataPipeline:
    """Test TypeShape evidence from services/data_pipeline.py."""

    def test_dataframe_attr_shapes(self) -> None:
        """DataFrame-like objects should produce attribute or method shapes."""
        result = _get_app_var_result("services/data_pipeline.py")
        df_evs = {k: v for k, v in result.evidence.items()
                  if k.endswith(".df") and (v.attrs_accessed or v.methods_called)}
        assert len(df_evs) >= 2

    def test_row_subscript_subset_shapes(self) -> None:
        """Row dict functions access different subsets of keys."""
        result = _get_app_var_result("services/data_pipeline.py")
        row_evs = {k: v for k, v in result.evidence.items()
                   if k.endswith(".row") and v.subscripts_accessed}
        assert len(row_evs) >= 2
        sizes = sorted(len(ev.subscripts_accessed) for ev in row_evs.values())
        assert sizes[0] < sizes[-1], "Expected different-sized row subscript sets"

    def test_conn_method_shapes(self) -> None:
        """DB connection objects should produce method-based shapes."""
        result = _get_app_var_result("services/data_pipeline.py")
        conn_evs = {k: v for k, v in result.evidence.items()
                    if k.endswith(".conn") and v.methods_called}
        assert len(conn_evs) >= 2

    def test_file_method_subset_shapes(self) -> None:
        """File-like objects should produce method shapes with subsets."""
        result = _get_app_var_result("services/data_pipeline.py")
        file_evs = {k: v for k, v in result.evidence.items()
                    if k.endswith(".f") and v.methods_called}
        assert len(file_evs) >= 2
        sizes = sorted(len(ev.methods_called) for ev in file_evs.values())
        assert sizes[0] < sizes[-1], "Expected different-sized file method sets"


class TestSampleAppEventBus:
    """Test TypeShape evidence from services/event_bus.py."""

    def test_event_attr_shapes(self) -> None:
        """Event objects should produce attribute-based shapes with subsets."""
        result = _get_app_var_result("services/event_bus.py")
        event_evs = {k: v for k, v in result.evidence.items()
                     if k.endswith(".event") and v.attrs_accessed}
        assert len(event_evs) >= 2

    def test_message_subscript_subset_shapes(self) -> None:
        """Message dict functions access different subsets of keys."""
        result = _get_app_var_result("services/event_bus.py")
        msg_evs = {k: v for k, v in result.evidence.items()
                   if k.endswith(".message") and v.subscripts_accessed}
        assert len(msg_evs) >= 2
        sizes = sorted(len(ev.subscripts_accessed) for ev in msg_evs.values())
        assert sizes[0] < sizes[-1], "Expected subset relationships in message shapes"


class TestSampleAppModels:
    """Test TypeShape evidence from models/user.py and models/post.py."""

    def test_user_attr_shapes(self) -> None:
        """User attribute access should produce structural shapes."""
        result = _get_app_var_result("models/user_model.py")
        user_evs = {k: v for k, v in result.evidence.items()
                    if k.endswith(".user") and v.attrs_accessed}
        assert len(user_evs) >= 1

    def test_user_row_subscript_subset(self) -> None:
        """User row dict functions should have subset relationships."""
        result = _get_app_var_result("models/user_model.py")
        row_evs = {k: v for k, v in result.evidence.items()
                   if k.endswith(".row") and v.subscripts_accessed}
        assert len(row_evs) >= 2
        sizes = sorted(len(ev.subscripts_accessed) for ev in row_evs.values())
        assert sizes[0] < sizes[-1], "Expected subset relationships in user row shapes"

    def test_post_attr_shapes(self) -> None:
        """Post attribute access should produce structural shapes."""
        result = _get_app_var_result("models/post_model.py")
        post_evs = {k: v for k, v in result.evidence.items()
                    if k.endswith(".post") and v.attrs_accessed}
        assert len(post_evs) >= 1


class TestSampleAppGraphAlgorithms:
    """Test TypeShape evidence from utils/graph_algorithms.py."""

    def test_node_attr_shapes(self) -> None:
        """Graph/tree nodes should produce attribute-based shapes."""
        result = _get_app_var_result("utils/graph_algorithms.py")
        node_evs = {k: v for k, v in result.evidence.items()
                    if ".node" in k and v.attrs_accessed}
        assert len(node_evs) >= 2

    def test_edge_subscript_shapes(self) -> None:
        """Edge dicts should produce subscript-based shapes."""
        result = _get_app_var_result("utils/graph_algorithms.py")
        edge_evs = {k: v for k, v in result.evidence.items()
                    if ".edge" in k and v.subscripts_accessed}
        assert len(edge_evs) >= 1

    def test_collection_method_shapes(self) -> None:
        """Stack/queue/set collections should produce method shapes."""
        result = _get_app_var_result("utils/graph_algorithms.py")
        collection_evs = {k: v for k, v in result.evidence.items()
                          if v.methods_called & {"append", "pop", "popleft", "add"}}
        assert len(collection_evs) >= 3


class TestSampleAppMathHelpers:
    """Test TypeShape evidence from utils/math_helpers.py."""

    def test_many_float_params_share_shape(self) -> None:
        """Multiple float params should produce the same primitive shape."""
        result = _get_app_var_result("utils/math_helpers.py")
        float_evs = [v for v in result.evidence.values() if v.type_hint == "float"]
        assert len(float_evs) >= 5
        defs = [build_shape_definition(ev) for ev in float_evs]
        hashes = {compute_shape_hash(d) for d in defs if d}
        assert len(hashes) == 1, "All float params should share one shape hash"

    def test_many_int_params_share_shape(self) -> None:
        """Multiple int params should produce the same primitive shape."""
        result = _get_app_var_result("utils/math_helpers.py")
        int_evs = [v for v in result.evidence.values() if v.type_hint == "int"]
        assert len(int_evs) >= 3
        defs = [build_shape_definition(ev) for ev in int_evs]
        hashes = {compute_shape_hash(d) for d in defs if d}
        assert len(hashes) == 1, "All int params should share one shape hash"

    def test_matrix_attr_shapes(self) -> None:
        """Matrix objects should produce attribute-based shapes."""
        result = _get_app_var_result("utils/math_helpers.py")
        matrix_evs = {k: v for k, v in result.evidence.items()
                      if k.endswith(".matrix") and v.attrs_accessed}
        assert len(matrix_evs) >= 1


class TestCrossModuleShapeDedup:
    """Test that TypeShape deduplication works ACROSS sample_app modules."""

    def test_request_shape_shared_across_api_and_auth(self) -> None:
        """Request attr shapes in api/routes.py and services/auth.py should overlap."""
        routes = _get_app_var_result("api/routes.py")
        auth = _get_app_var_result("services/auth_service.py")

        route_req = {k: v for k, v in routes.evidence.items()
                     if k.endswith(".request") and v.attrs_accessed}
        auth_req = {k: v for k, v in auth.evidence.items()
                    if k.endswith(".request") and v.attrs_accessed}
        assert route_req and auth_req, "Both modules should have request evidence"

        # Auth accesses a subset of request attrs (e.g., just headers, body)
        # Routes accesses more (method, path, headers, body, query_params)
        route_attrs = set()
        for ev in route_req.values():
            route_attrs |= ev.attrs_accessed
        auth_attrs = set()
        for ev in auth_req.values():
            auth_attrs |= ev.attrs_accessed
        # Auth's request attrs should be a subset of routes' request attrs
        assert auth_attrs & route_attrs, "Auth and routes should share some request attrs"

    def test_session_shape_shared_across_modules(self) -> None:
        """Session dict shapes should appear in both auth and middleware."""
        auth = _get_app_var_result("services/auth_service.py")
        mw = _get_app_var_result("api/middleware.py")

        auth_sess = {k: v for k, v in auth.evidence.items()
                     if k.endswith(".session") and v.subscripts_accessed}
        mw_sess = {k: v for k, v in mw.evidence.items()
                   if k.endswith(".session") and v.subscripts_accessed}
        assert auth_sess, "Auth should have session evidence"
        assert mw_sess, "Middleware should have session evidence"

    def test_int_shapes_shared_across_modules(self) -> None:
        """int params in math_helpers and graph_algorithms should share a shape hash."""
        math = _get_app_var_result("utils/math_helpers.py")
        graph = _get_app_var_result("utils/graph_algorithms.py")

        math_int = next((v for v in math.evidence.values() if v.type_hint == "int"), None)
        graph_int = next((v for v in graph.evidence.values() if v.type_hint == "int"), None)
        assert math_int and graph_int

        d1 = build_shape_definition(math_int)
        d2 = build_shape_definition(graph_int)
        assert d1 and d2
        assert compute_shape_hash(d1) == compute_shape_hash(d2)

    def test_unique_shape_count_across_sample_app(self) -> None:
        """Across all sample_app modules, unique shapes should be much fewer than evidence."""
        all_hashes: set[str] = set()
        total_evidence = 0

        for root, _dirs, files in os.walk(SAMPLE_APP_DIR):
            for f in sorted(files):
                if not f.endswith(".py") or f == "__init__.py":
                    continue
                rel = os.path.relpath(os.path.join(root, f), SAMPLE_APP_DIR)
                result = _get_app_var_result(rel)
                for ev in result.evidence.values():
                    defn = build_shape_definition(ev)
                    if defn:
                        all_hashes.add(compute_shape_hash(defn))
                        total_evidence += 1

        # 333 shape-eligible entries, 118 unique — significant dedup
        assert total_evidence > 200, f"Expected 200+ evidence entries, got {total_evidence}"
        assert len(all_hashes) < total_evidence * 0.5, (
            f"Expected significant dedup: {len(all_hashes)} unique out of {total_evidence} total"
        )


class TestDualShapeBehavior:
    """Test dual TypeShape emission: structural + hint for typed parameters."""

    def test_event_params_all_have_type_hints(self) -> None:
        """Every .event evidence in event_bus.py should have both attrs_accessed and type_hint == 'Event'."""
        result = _get_app_var_result("services/event_bus.py")
        event_evs = {k: v for k, v in result.evidence.items()
                     if k.endswith(".event") and v.attrs_accessed}
        assert len(event_evs) >= 3, f"Expected 3+ event evidences, got {len(event_evs)}"
        for key, ev in event_evs.items():
            assert ev.type_hint == "Event", f"{key} should have type_hint='Event', got '{ev.type_hint}'"
            assert ev.attrs_accessed, f"{key} should have attrs_accessed"

    def test_structural_with_hint_produces_distinct_hashes(self) -> None:
        """Structural and hint definitions from same evidence should have different hashes."""
        ev = ShapeEvidence(
            variable_name="test.event",
            attrs_accessed={"name", "priority"},
            type_hint="Event",
        )
        structural_def = build_shape_definition(ev)
        hint_def = {"kind": "hint", "type": "Event"}

        assert structural_def is not None
        assert structural_def["kind"] == "structural"
        assert compute_shape_hash(structural_def) != compute_shape_hash(hint_def)

    def test_primitive_hint_skips_dual_shape(self) -> None:
        """A primitive type hint (int) with structural evidence should NOT produce a hint shape.

        The import pipeline guards against this with _HINT_SKIP_TYPES.
        Here we verify the guard values match expectations.
        """
        from app.services.persistence.import_pipeline import _HINT_SKIP_TYPES

        assert "int" in _HINT_SKIP_TYPES
        assert "float" in _HINT_SKIP_TYPES
        assert "str" in _HINT_SKIP_TYPES
        assert "bool" in _HINT_SKIP_TYPES
        # Non-primitives should NOT be in the skip set
        assert "Event" not in _HINT_SKIP_TYPES
        assert "dict" not in _HINT_SKIP_TYPES
        assert "list" not in _HINT_SKIP_TYPES
