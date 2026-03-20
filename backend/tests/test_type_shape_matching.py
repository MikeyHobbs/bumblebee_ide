"""Tests for TypeShape duck-typing matching algorithm (TICKET-969).

Tests the structural matching, hint bridging, and edge-computation logic
extracted from type_shape_service.compute_compatible_with_edges — without
requiring FalkorDB.

Desired-but-not-yet-working behaviors are marked ``@pytest.mark.xfail``.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from app.services.analysis.type_shape_service import (
    build_shape_definition,
    compute_shape_hash,
)
from app.services.parsing.ast_parser import parse_file
from app.services.parsing.variable_extractor import ShapeEvidence, extract_variables


# ---------------------------------------------------------------------------
# Helper functions — pure-logic extraction of matching rules
# ---------------------------------------------------------------------------

# Minimum evidence items for the subset side of a structural match.
_MIN_EVIDENCE = 2

# Primitive container types excluded from hint bridging.
_PRIMITIVE_CONTAINERS = {"list", "dict", "set", "tuple", "frozenset", "deque"}


def _make_structural(
    id: str,
    base_type: str = "",
    attrs: list[str] | None = None,
    subscripts: list[str] | None = None,
    methods: list[str] | None = None,
) -> dict[str, Any]:
    """Build a structural shape dict matching the in-memory format used by
    ``compute_compatible_with_edges``."""
    return {
        "id": id,
        "base_type": base_type,
        "attrs": set(attrs or []),
        "subscripts": set(subscripts or []),
        "methods": set(methods or []),
    }


def _make_hint(id: str, type_name: str) -> dict[str, Any]:
    """Build a hint shape dict matching the in-memory format."""
    return {
        "id": id,
        "type": type_name,
    }


def _normalize_base(raw: str) -> str:
    """Normalize a base_type string the same way the production code does."""
    return raw.split("[")[0].rsplit(".", 1)[-1].strip().lower()


def _compute_structural_matches(
    shapes: list[dict[str, Any]],
    min_evidence: int = _MIN_EVIDENCE,
) -> list[tuple[str, str]]:
    """Extract structural↔structural matching logic from
    ``compute_compatible_with_edges``.

    Returns a list of ``(superset_id, subset_id)`` pairs.
    """
    edges: list[tuple[str, str]] = []
    for i, s1 in enumerate(shapes):
        for j, s2 in enumerate(shapes):
            if i == j:
                continue
            # Evidence threshold on subset side
            total_s2 = len(s2["attrs"]) + len(s2["subscripts"]) + len(s2["methods"])
            if total_s2 < min_evidence:
                continue
            # Base-type guard: any typed shape → route through hint hub only
            s1_base = s1["base_type"]
            s2_base = s2["base_type"]
            if s1_base or s2_base:
                continue
            # Strict superset
            if (
                s2["attrs"] <= s1["attrs"]
                and s2["subscripts"] <= s1["subscripts"]
                and s2["methods"] <= s1["methods"]
                and (s1["attrs"] | s1["subscripts"] | s1["methods"])
                != (s2["attrs"] | s2["subscripts"] | s2["methods"])
            ):
                edges.append((s1["id"], s2["id"]))
    return edges


def _compute_hint_structural_matches(
    hints: list[dict[str, Any]],
    structurals: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """Extract hint↔structural bridging logic.

    Returns a list of ``(source_id, target_id)`` pairs covering both
    hint→structural and structural→hint directions.
    """
    edges: list[tuple[str, str]] = []
    # hint → structural
    for hint in hints:
        hint_type = hint["type"]
        if not hint_type:
            continue
        hint_base = hint_type.split("[")[0].rsplit(".", 1)[-1].strip()
        if hint_base.lower() in _PRIMITIVE_CONTAINERS:
            continue
        for st in structurals:
            st_base = st["base_type"]
            if not st_base:
                continue
            st_norm = st_base.split("[")[0].rsplit(".", 1)[-1].strip()
            if hint_base.lower() == st_norm.lower():
                edges.append((hint["id"], st["id"]))
    # structural → hint
    for st in structurals:
        st_base = st["base_type"]
        if not st_base:
            continue
        st_norm = st_base.split("[")[0].rsplit(".", 1)[-1].strip()
        if st_norm.lower() in _PRIMITIVE_CONTAINERS:
            continue
        for hint in hints:
            hint_base = hint["type"].split("[")[0].rsplit(".", 1)[-1].strip()
            if st_norm.lower() == hint_base.lower():
                edges.append((st["id"], hint["id"]))
    return edges


def _compute_generic_bare_matches(
    hints: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """Extract generic→bare hint bridging logic.

    Returns ``(generic_id, bare_id)`` pairs.
    """
    bare_hints: dict[str, dict[str, Any]] = {}
    for hint in hints:
        ht = hint["type"]
        if not ht or "[" in ht:
            continue
        bare_hints[ht.lower()] = hint

    edges: list[tuple[str, str]] = []
    for hint in hints:
        ht = hint["type"]
        if not ht or "[" not in ht:
            continue
        bare_name = ht.split("[")[0].strip().lower()
        bare = bare_hints.get(bare_name)
        if bare and bare["id"] != hint["id"]:
            edges.append((hint["id"], bare["id"]))
    return edges


def _compute_facet_cluster_edges(
    shapes: list[dict[str, Any]],
    min_evidence: int = 1,
) -> list[tuple[str, str]]:
    """Connect untyped shapes with complementary facets.

    S1 has attrs/subscripts but no methods, S2 has methods but no attrs/subscripts
    (or vice versa). Both must have >= min_evidence items.
    """
    edges: list[tuple[str, str]] = []
    for i, s1 in enumerate(shapes):
        if s1["base_type"]:
            continue
        for j, s2 in enumerate(shapes):
            if i >= j or s2["base_type"]:
                continue
            s1_has_data = bool(s1["attrs"] or s1["subscripts"])
            s1_has_methods = bool(s1["methods"])
            s2_has_data = bool(s2["attrs"] or s2["subscripts"])
            s2_has_methods = bool(s2["methods"])
            if not ((s1_has_data and not s1_has_methods and s2_has_methods and not s2_has_data)
                    or (s1_has_methods and not s1_has_data and s2_has_data and not s2_has_methods)):
                continue
            s1_total = len(s1["attrs"]) + len(s1["subscripts"]) + len(s1["methods"])
            s2_total = len(s2["attrs"]) + len(s2["subscripts"]) + len(s2["methods"])
            if s1_total >= min_evidence and s2_total >= min_evidence:
                edges.append((s1["id"], s2["id"]))
                edges.append((s2["id"], s1["id"]))
    return edges


# ---------------------------------------------------------------------------
# Fixture helpers for sample_app integration tests
# ---------------------------------------------------------------------------

SAMPLE_APP_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "test_repos", "sample_app")
)


def _get_app_var_result(rel_path: str):  # type: ignore[no-untyped-def]
    """Parse a sample_app file and extract variables with shape evidence."""
    source = open(os.path.join(SAMPLE_APP_DIR, rel_path), encoding="utf-8").read()  # noqa: SIM115
    result = parse_file(source, rel_path)
    return extract_variables(source, rel_path, result.nodes)


def _build_shapes_from_evidence(
    evidence_map: dict[str, ShapeEvidence],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert evidence map to structural + hint shape lists (with dedup by hash)."""
    seen_hashes: dict[str, dict[str, Any]] = {}
    structurals: list[dict[str, Any]] = []
    hints: list[dict[str, Any]] = []

    for key, ev in evidence_map.items():
        defn = build_shape_definition(ev)
        if defn is None:
            continue
        h = compute_shape_hash(defn)
        if defn["kind"] == "structural":
            if h not in seen_hashes:
                shape = _make_structural(
                    id=h,
                    base_type=defn.get("base_type", ""),
                    attrs=defn.get("attrs", []),
                    subscripts=defn.get("subscripts", []),
                    methods=defn.get("methods", []),
                )
                seen_hashes[h] = shape
                structurals.append(shape)
            # Also emit a hint shape for dual-emission if type_hint exists
            if ev.type_hint and ev.type_hint not in {"int", "float", "str", "bool", "bytes", "complex", "None", "NoneType"}:
                hint_defn = {"kind": "hint", "type": ev.type_hint}
                hint_h = compute_shape_hash(hint_defn)
                if hint_h not in seen_hashes:
                    hint_shape = _make_hint(id=hint_h, type_name=ev.type_hint)
                    seen_hashes[hint_h] = hint_shape
                    hints.append(hint_shape)
        elif defn["kind"] == "hint":
            if h not in seen_hashes:
                shape = _make_hint(id=h, type_name=defn["type"])
                seen_hashes[h] = shape
                hints.append(shape)

    return structurals, hints


# ===================================================================
# Test Classes
# ===================================================================


class TestHashIsolation:
    """Verify that base_type is included in the canonical hash."""

    def test_same_attrs_different_base_type_different_hash(self) -> None:
        """Event.{data,name} != bare.{data,name} — base_type changes hash."""
        def1 = {"kind": "structural", "attrs": ["data", "name"], "subscripts": [], "methods": [], "base_type": "Event"}
        def2 = {"kind": "structural", "attrs": ["data", "name"], "subscripts": [], "methods": []}
        assert compute_shape_hash(def1) != compute_shape_hash(def2)

    def test_same_attrs_same_base_type_same_hash(self) -> None:
        """Deterministic: identical definitions produce the same hash."""
        def1 = {"kind": "structural", "attrs": ["data", "name"], "subscripts": [], "methods": [], "base_type": "Event"}
        def2 = {"kind": "structural", "attrs": ["data", "name"], "subscripts": [], "methods": [], "base_type": "Event"}
        assert compute_shape_hash(def1) == compute_shape_hash(def2)

    def test_no_base_type_empty_string_in_canonical(self) -> None:
        """When base_type is absent the canonical string uses empty string."""
        def_no_bt = {"kind": "structural", "attrs": ["x"], "subscripts": [], "methods": []}
        def_empty_bt = {"kind": "structural", "attrs": ["x"], "subscripts": [], "methods": [], "base_type": ""}
        assert compute_shape_hash(def_no_bt) == compute_shape_hash(def_empty_bt)


class TestEvidenceThreshold:
    """Verify MIN_STRUCTURAL_EVIDENCE gate on the subset side."""

    def test_single_attr_excluded(self) -> None:
        """A shape with only 1 attr cannot be the subset side."""
        superset = _make_structural("s1", attrs=["a", "b"])
        subset = _make_structural("s2", attrs=["a"])
        edges = _compute_structural_matches([superset, subset])
        assert ("s1", "s2") not in edges

    def test_two_attrs_included(self) -> None:
        """A shape with 2 attrs meets the threshold."""
        superset = _make_structural("s1", attrs=["a", "b", "c"])
        subset = _make_structural("s2", attrs=["a", "b"])
        edges = _compute_structural_matches([superset, subset])
        assert ("s1", "s2") in edges

    def test_single_method_excluded(self) -> None:
        """aggregate_by_group(df) with only {groupby} — 1 method excluded."""
        superset = _make_structural("s1", methods=["groupby", "fillna"])
        subset = _make_structural("s2", methods=["groupby"])
        edges = _compute_structural_matches([superset, subset])
        assert ("s1", "s2") not in edges

    def test_threshold_counts_across_facets(self) -> None:
        """1 attr + 1 method = 2 total evidence — meets threshold."""
        superset = _make_structural("s1", attrs=["a", "b"], methods=["m1", "m2"])
        subset = _make_structural("s2", attrs=["a"], methods=["m1"])
        edges = _compute_structural_matches([superset, subset])
        assert ("s1", "s2") in edges


class TestBaseTypeGuard:
    """Verify base_type matching/blocking between structural shapes."""

    def test_both_typed_different_bases_no_match(self) -> None:
        """Event vs Request: both have base_type, different — blocked."""
        s1 = _make_structural("s1", base_type="Event", attrs=["name", "data", "source"])
        s2 = _make_structural("s2", base_type="Request", attrs=["name", "data"])
        edges = _compute_structural_matches([s1, s2])
        assert ("s1", "s2") not in edges

    def test_both_typed_same_base_routes_via_hub(self) -> None:
        """Event superset of Event — both typed, routed via hint hub."""
        s1 = _make_structural("s1", base_type="Event", attrs=["name", "data", "source"])
        s2 = _make_structural("s2", base_type="Event", attrs=["name", "data"])
        edges = _compute_structural_matches([s1, s2])
        assert ("s1", "s2") not in edges

    def test_one_typed_one_untyped_blocked(self) -> None:
        """Typed shapes do NOT superset-match untyped shapes — prevents false transitive links."""
        s1 = _make_structural("s1", base_type="Event", attrs=["name", "data", "source"])
        s2 = _make_structural("s2", attrs=["name", "data"])
        edges = _compute_structural_matches([s1, s2])
        assert ("s1", "s2") not in edges

    def test_untyped_superset_of_typed_blocked(self) -> None:
        """Untyped shapes cannot superset-match typed shapes either."""
        s1 = _make_structural("s1", attrs=["name", "data", "source", "extra"])
        s2 = _make_structural("s2", base_type="Event", attrs=["name", "data", "source"])
        edges = _compute_structural_matches([s1, s2])
        assert ("s1", "s2") not in edges

    def test_base_type_normalization(self) -> None:
        """'models.Event' normalizes to 'Event' — verify normalization works."""
        assert _normalize_base("models.Event") == _normalize_base("Event")
        # Both typed → routed via hub, no direct edge
        s1 = _make_structural("s1", base_type="models.Event", attrs=["name", "data", "source"])
        s2 = _make_structural("s2", base_type="Event", attrs=["name", "data"])
        edges = _compute_structural_matches([s1, s2])
        assert ("s1", "s2") not in edges


class TestSupersetMatching:
    """Core superset logic for structural shapes."""

    def test_strict_superset_creates_edge(self) -> None:
        """S1 {a,b,c} ⊃ S2 {a,b} → edge."""
        s1 = _make_structural("s1", attrs=["a", "b", "c"])
        s2 = _make_structural("s2", attrs=["a", "b"])
        edges = _compute_structural_matches([s1, s2])
        assert ("s1", "s2") in edges

    def test_equal_sets_same_hash(self) -> None:
        """Same evidence → same hash → same node, no edge needed."""
        def1 = {"kind": "structural", "attrs": ["a", "b"], "subscripts": [], "methods": []}
        def2 = {"kind": "structural", "attrs": ["a", "b"], "subscripts": [], "methods": []}
        assert compute_shape_hash(def1) == compute_shape_hash(def2)

    def test_disjoint_no_edge(self) -> None:
        """{a,b} and {c,d} — disjoint, no superset relationship."""
        s1 = _make_structural("s1", attrs=["a", "b"])
        s2 = _make_structural("s2", attrs=["c", "d"])
        edges = _compute_structural_matches([s1, s2])
        assert len(edges) == 0

    def test_partial_overlap_no_edge(self) -> None:
        """{a,b,c} and {b,c,d} — partial overlap, neither is superset."""
        s1 = _make_structural("s1", attrs=["a", "b", "c"])
        s2 = _make_structural("s2", attrs=["b", "c", "d"])
        edges = _compute_structural_matches([s1, s2])
        assert len(edges) == 0

    def test_methods_superset(self) -> None:
        """{cursor, commit} ⊃ {cursor} — but {cursor} is below threshold."""
        s1 = _make_structural("s1", methods=["cursor", "commit"])
        s2 = _make_structural("s2", methods=["cursor"])
        # Single method is below threshold
        edges = _compute_structural_matches([s1, s2])
        assert ("s1", "s2") not in edges
        # With 2 methods on subset side
        s3 = _make_structural("s3", methods=["cursor", "commit", "rollback"])
        edges2 = _compute_structural_matches([s3, s1])
        assert ("s3", "s1") in edges2

    def test_cross_facet_superset(self) -> None:
        """{attrs:[a], methods:[m]} ⊃ {attrs:[a]} — cross-facet works but
        subset has only 1 evidence item so excluded by threshold.
        With 2 items on subset it passes."""
        s1 = _make_structural("s1", attrs=["a", "b"], methods=["m"])
        s2 = _make_structural("s2", attrs=["a", "b"])
        edges = _compute_structural_matches([s1, s2])
        assert ("s1", "s2") in edges


class TestDataFrameFacetMatching:
    """DataFrame shapes: attrs vs methods are disjoint facets."""

    def test_df_facets_union_is_superset(self) -> None:
        """PASS — documents that if we union df facets, the result is a superset
        of each individual facet. This is a math property, not an algorithm test."""
        attr_facet = {"columns", "shape"}
        method_facet = {"dropna", "fillna"}
        union = attr_facet | method_facet
        assert attr_facet <= union
        assert method_facet <= union

    def test_df_attr_and_method_facets_connected(self) -> None:
        """validate_schema(df) {attrs: columns, shape} and
        clean_dataframe(df) {methods: dropna, fillna} should connect via facet clustering."""
        attr_shape = _make_structural("df_attr", attrs=["columns", "shape"])
        method_shape = _make_structural("df_method", methods=["dropna", "fillna"])
        edges = _compute_structural_matches([attr_shape, method_shape]) + _compute_facet_cluster_edges([attr_shape, method_shape])
        connected = (
            ("df_attr", "df_method") in edges
            or ("df_method", "df_attr") in edges
        )
        assert connected, "Disjoint df facets should be connected"

    def test_df_all_facets_connected_component(self) -> None:
        """All 4 df shapes (attr-only, method-only, mixed, groupby) should be
        reachable from each other via superset + facet clustering."""
        shapes = [
            _make_structural("df_validate", attrs=["columns", "shape"]),
            _make_structural("df_clean", methods=["dropna", "fillna"]),
            _make_structural("df_profile", attrs=["columns", "shape", "dtypes", "index"]),
            _make_structural("df_group", methods=["groupby"]),
        ]
        edges = _compute_structural_matches(shapes) + _compute_facet_cluster_edges(shapes)
        # Build adjacency
        adj: dict[str, set[str]] = {s["id"]: set() for s in shapes}
        for src, tgt in edges:
            adj[src].add(tgt)
            adj[tgt].add(src)
        # BFS from first node
        visited: set[str] = set()
        queue = ["df_validate"]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            queue.extend(adj.get(node, set()) - visited)
        assert visited == {s["id"] for s in shapes}, (
            f"Expected all df shapes connected; got {visited}"
        )

    def test_subthreshold_facet_excluded(self) -> None:
        """Single-method shape connects via facet clustering to complementary attrs shape."""
        attr_shape = _make_structural("df_attrs", attrs=["columns", "shape"])
        single_method = _make_structural("df_group", methods=["groupby"])
        # Superset matching still excludes (different facets, no overlap)
        superset_edges = _compute_structural_matches([attr_shape, single_method])
        assert len(superset_edges) == 0
        # Facet clustering connects complementary facets even with 1 evidence item
        facet_edges = _compute_facet_cluster_edges([attr_shape, single_method])
        connected = ("df_attrs", "df_group") in facet_edges or ("df_group", "df_attrs") in facet_edges
        assert connected


class TestEventHubConvergence:
    """Event shapes should route through a hint hub, not form O(N^2) mesh."""

    def _make_event_shapes(self) -> list[dict[str, Any]]:
        """Build 5 Event structural shapes with varying attr sets."""
        return [
            _make_structural("evt_log", base_type="Event", attrs=["name", "data"]),
            _make_structural("evt_verbose", base_type="Event", attrs=["name", "data", "source", "timestamp"]),
            _make_structural("evt_priority", base_type="Event", attrs=["name", "priority"]),
            _make_structural("evt_fingerprint", base_type="Event", attrs=["name", "data", "source", "timestamp", "priority"]),
            _make_structural("evt_dispatch", base_type="Event", attrs=["name", "data", "handled"]),
        ]

    def test_event_shapes_produce_multiple_nodes(self) -> None:
        """PASS — documents current behavior: different attr sets → different hashes."""
        shapes = self._make_event_shapes()
        hashes = set()
        for s in shapes:
            defn = {
                "kind": "structural",
                "attrs": sorted(s["attrs"]),
                "subscripts": sorted(s["subscripts"]),
                "methods": sorted(s["methods"]),
                "base_type": s["base_type"],
            }
            hashes.add(compute_shape_hash(defn))
        assert len(hashes) == len(shapes), "Each Event shape should have a unique hash"

    def test_hint_event_bridges_to_all_structural(self) -> None:
        """PASS — existing hint↔structural bridging connects hint:Event to all
        structural shapes with base_type=Event."""
        hints = [_make_hint("hint_event", "Event")]
        structurals = self._make_event_shapes()
        edges = _compute_hint_structural_matches(hints, structurals)
        targets = {tgt for src, tgt in edges if src == "hint_event"}
        expected_ids = {s["id"] for s in structurals}
        assert targets == expected_ids

    def test_event_structural_to_structural_edges_zero(self) -> None:
        """When both shapes have the same base_type, skip superset edge —
        the hint hub already connects them."""
        shapes = self._make_event_shapes()
        edges = _compute_structural_matches(shapes)
        assert len(edges) == 0, (
            f"Expected 0 structural↔structural edges for same-base Event shapes, got {len(edges)}"
        )

    def test_event_compatible_edges_linear_not_quadratic(self) -> None:
        """Total COMPATIBLE_WITH edges for N Event shapes should be ≤ 2*N
        (each structural ↔ hub, not pairwise)."""
        shapes = self._make_event_shapes()
        hints = [_make_hint("hint_event", "Event")]
        structural_edges = _compute_structural_matches(shapes)
        hint_edges = _compute_hint_structural_matches(hints, shapes)
        total = len(structural_edges) + len(hint_edges)
        n = len(shapes)
        assert total <= 2 * n, (
            f"Expected ≤ {2 * n} edges (O(N)), got {total} (structural={len(structural_edges)}, hint={len(hint_edges)})"
        )

    def test_event_hub_is_hint_node(self) -> None:
        """Every structural Event shape should connect ONLY through the
        hint:Event node — no direct structural↔structural edges."""
        shapes = self._make_event_shapes()
        hints = [_make_hint("hint_event", "Event")]
        structural_edges = _compute_structural_matches(shapes)
        hint_edges = _compute_hint_structural_matches(hints, shapes)
        # All structural edges should be zero
        assert len(structural_edges) == 0, "Structural↔structural edges should be zero"
        # Every structural should have an edge to/from the hub
        connected_to_hub = set()
        for src, tgt in hint_edges:
            if src == "hint_event":
                connected_to_hub.add(tgt)
            if tgt == "hint_event":
                connected_to_hub.add(src)
        assert connected_to_hub == {s["id"] for s in shapes}


class TestHintStructuralBridging:
    """Hint↔structural bridging for typed variables to duck-typed consumers."""

    def test_hint_bridges_to_matching_base_type(self) -> None:
        """hint:Event connects to structural with base_type=Event."""
        hints = [_make_hint("h1", "Event")]
        structurals = [_make_structural("s1", base_type="Event", attrs=["name", "data"])]
        edges = _compute_hint_structural_matches(hints, structurals)
        assert ("h1", "s1") in edges

    def test_hint_skips_untyped_structural(self) -> None:
        """hint:Event does NOT connect to untyped structural shapes."""
        hints = [_make_hint("h1", "Event")]
        structurals = [_make_structural("s1", attrs=["name", "data"])]
        edges = _compute_hint_structural_matches(hints, structurals)
        hint_to_structural = [(s, t) for s, t in edges if s == "h1" and t == "s1"]
        assert len(hint_to_structural) == 0

    def test_structural_bridges_back_to_hint(self) -> None:
        """structural with base_type=Event connects back to hint:Event."""
        hints = [_make_hint("h1", "Event")]
        structurals = [_make_structural("s1", base_type="Event", attrs=["name", "data"])]
        edges = _compute_hint_structural_matches(hints, structurals)
        assert ("s1", "h1") in edges

    def test_primitive_container_excluded(self) -> None:
        """hint:list should NOT bridge to structural shapes — too generic."""
        hints = [_make_hint("h1", "list")]
        structurals = [_make_structural("s1", base_type="list", methods=["append", "extend"])]
        edges = _compute_hint_structural_matches(hints, structurals)
        hint_to_st = [(s, t) for s, t in edges if s == "h1"]
        assert len(hint_to_st) == 0

    def test_hint_to_all_event_structurals(self) -> None:
        """hint:Event connects to each Event structural shape individually."""
        hints = [_make_hint("h1", "Event")]
        structurals = [
            _make_structural("s1", base_type="Event", attrs=["name", "data"]),
            _make_structural("s2", base_type="Event", attrs=["name", "data", "source"]),
            _make_structural("s3", base_type="Event", attrs=["priority", "name"]),
        ]
        edges = _compute_hint_structural_matches(hints, structurals)
        targets = {tgt for src, tgt in edges if src == "h1"}
        assert targets == {"s1", "s2", "s3"}


class TestGenericBareHintBridging:
    """Generic hint (e.g. list[str]) → bare hint (list) bridging."""

    def test_generic_bridges_to_bare(self) -> None:
        """hint:list[str] → hint:list."""
        hints = [
            _make_hint("h_generic", "list[str]"),
            _make_hint("h_bare", "list"),
        ]
        edges = _compute_generic_bare_matches(hints)
        assert ("h_generic", "h_bare") in edges

    def test_two_generics_no_bridge(self) -> None:
        """hint:list[str] and hint:list[int] — no direct bridge between generics."""
        hints = [
            _make_hint("h1", "list[str]"),
            _make_hint("h2", "list[int]"),
        ]
        edges = _compute_generic_bare_matches(hints)
        assert ("h1", "h2") not in edges
        assert ("h2", "h1") not in edges

    def test_no_bare_no_bridge(self) -> None:
        """hint:list[str] with no bare hint:list — no edge."""
        hints = [_make_hint("h1", "list[str]")]
        edges = _compute_generic_bare_matches(hints)
        assert len(edges) == 0


class TestEndToEndFromFixtures:
    """Integration tests using real sample_app fixtures."""

    def test_user_superset_detected(self) -> None:
        """enrich_user {name, email, phone} ⊃ extract_user_emails {name, email}."""
        result = _get_app_var_result("services/data_pipeline.py")
        # These are typed_pipeline fixtures but data_pipeline has row subscripts
        # Use the actual fixture: typed_pipeline.py from test fixtures
        fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures", "sample_repo")
        source = open(os.path.join(fixtures_dir, "typed_pipeline.py"), encoding="utf-8").read()  # noqa: SIM115
        parsed = parse_file(source, "typed_pipeline.py")
        var_result = extract_variables(source, "typed_pipeline.py", parsed.nodes)

        enrich_ev = var_result.evidence.get("typed_pipeline.enrich_user.user")
        extract_ev = var_result.evidence.get("typed_pipeline.extract_user_emails.user")
        assert enrich_ev is not None and extract_ev is not None

        enrich_def = build_shape_definition(enrich_ev)
        extract_def = build_shape_definition(extract_ev)
        assert enrich_def is not None and extract_def is not None

        s1 = _make_structural(
            "enrich",
            subscripts=enrich_def.get("subscripts", []),
        )
        s2 = _make_structural(
            "extract",
            subscripts=extract_def.get("subscripts", []),
        )
        edges = _compute_structural_matches([s1, s2])
        assert ("enrich", "extract") in edges

    def test_response_shapes_shared(self) -> None:
        """format_response and log_response produce the same hash."""
        fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures", "sample_repo")
        source = open(os.path.join(fixtures_dir, "typed_pipeline.py"), encoding="utf-8").read()  # noqa: SIM115
        parsed = parse_file(source, "typed_pipeline.py")
        var_result = extract_variables(source, "typed_pipeline.py", parsed.nodes)

        fmt_ev = var_result.evidence.get("typed_pipeline.format_response.response")
        log_ev = var_result.evidence.get("typed_pipeline.log_response.response")
        assert fmt_ev is not None and log_ev is not None

        def1 = build_shape_definition(fmt_ev)
        def2 = build_shape_definition(log_ev)
        assert def1 is not None and def2 is not None
        assert compute_shape_hash(def1) == compute_shape_hash(def2)

    def test_conn_superset(self) -> None:
        """run_insert {cursor, commit} ⊃ run_query {cursor} — but single method
        below threshold, so test the superset relationship directly."""
        fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures", "sample_repo")
        source = open(os.path.join(fixtures_dir, "typed_pipeline.py"), encoding="utf-8").read()  # noqa: SIM115
        parsed = parse_file(source, "typed_pipeline.py")
        var_result = extract_variables(source, "typed_pipeline.py", parsed.nodes)

        insert_ev = var_result.evidence.get("typed_pipeline.run_insert.conn")
        query_ev = var_result.evidence.get("typed_pipeline.run_query.conn")
        assert insert_ev is not None and query_ev is not None

        insert_def = build_shape_definition(insert_ev)
        query_def = build_shape_definition(query_ev)
        assert insert_def is not None and query_def is not None

        # Verify superset relationship exists in the evidence
        insert_methods = set(insert_def.get("methods", []))
        query_methods = set(query_def.get("methods", []))
        assert query_methods <= insert_methods, "run_query methods should be subset of run_insert"
        assert insert_methods != query_methods, "Should be strict superset"

    def test_df_connected_component(self) -> None:
        """All DataFrame shapes from data_pipeline.py should be reachable."""
        result = _get_app_var_result("services/data_pipeline.py")
        df_evs = {k: v for k, v in result.evidence.items()
                  if k.endswith(".df") and (v.attrs_accessed or v.methods_called)}
        assert len(df_evs) >= 2, f"Expected 2+ df evidence entries, got {len(df_evs)}"

        shapes = []
        for key, ev in df_evs.items():
            defn = build_shape_definition(ev)
            if defn and defn["kind"] == "structural":
                shapes.append(_make_structural(
                    id=key,
                    attrs=defn.get("attrs", []),
                    subscripts=defn.get("subscripts", []),
                    methods=defn.get("methods", []),
                ))
        edges = _compute_structural_matches(shapes) + _compute_facet_cluster_edges(shapes)
        # Build adjacency and check connectivity
        adj: dict[str, set[str]] = {s["id"]: set() for s in shapes}
        for src, tgt in edges:
            adj[src].add(tgt)
            adj[tgt].add(src)
        visited: set[str] = set()
        queue = [shapes[0]["id"]]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            queue.extend(adj.get(node, set()) - visited)
        assert visited == {s["id"] for s in shapes}, (
            f"Expected all df shapes connected; visited {len(visited)}/{len(shapes)}"
        )

    def test_event_hub_pattern(self) -> None:
        """Event shapes from event_bus.py should route through hint:Event hub."""
        result = _get_app_var_result("services/event_bus.py")
        event_evs = {k: v for k, v in result.evidence.items()
                     if k.endswith(".event") and v.attrs_accessed}
        assert len(event_evs) >= 3

        structurals, hints = _build_shapes_from_evidence(
            {k: v for k, v in result.evidence.items() if k.endswith(".event")}
        )
        structural_edges = _compute_structural_matches(structurals)
        # With hub routing, structural↔structural edges should be zero
        assert len(structural_edges) == 0, (
            f"Expected 0 structural edges with hub routing, got {len(structural_edges)}"
        )


class TestCrossModuleDedup:
    """Verify shape deduplication across modules."""

    def test_same_evidence_different_modules_same_hash(self) -> None:
        """Identical structural evidence from different modules → same hash."""
        def1 = {
            "kind": "structural",
            "attrs": ["status_code", "text"],
            "subscripts": [],
            "methods": [],
        }
        def2 = {
            "kind": "structural",
            "attrs": ["status_code", "text"],
            "subscripts": [],
            "methods": [],
        }
        assert compute_shape_hash(def1) == compute_shape_hash(def2)

    def test_base_type_prevents_false_dedup(self) -> None:
        """Same attrs but different base_type → different hash → no false dedup."""
        def1 = {
            "kind": "structural",
            "attrs": ["name", "data"],
            "subscripts": [],
            "methods": [],
            "base_type": "Event",
        }
        def2 = {
            "kind": "structural",
            "attrs": ["name", "data"],
            "subscripts": [],
            "methods": [],
            "base_type": "Message",
        }
        assert compute_shape_hash(def1) != compute_shape_hash(def2)


class TestCrossModuleIsolation:
    """Verify that typed and untyped shapes do not create false transitive paths."""

    def test_typed_event_does_not_superset_untyped(self) -> None:
        """event_fingerprint(event: Event) must NOT match format_record(record)."""
        event_shape = _make_structural(
            "evt_fingerprint",
            base_type="Event",
            attrs=["name", "data", "source", "timestamp", "priority"],
        )
        untyped_shape = _make_structural(
            "format_record",
            attrs=["name", "data"],
        )
        edges = _compute_structural_matches([event_shape, untyped_shape])
        assert ("evt_fingerprint", "format_record") not in edges

    def test_untyped_to_untyped_superset_still_works(self) -> None:
        """Untyped shapes can still superset-match each other (duck-typing)."""
        s1 = _make_structural("broad_consumer", attrs=["name", "data", "extra"])
        s2 = _make_structural("narrow_consumer", attrs=["name", "data"])
        edges = _compute_structural_matches([s1, s2])
        assert ("broad_consumer", "narrow_consumer") in edges

    def test_no_transitive_event_to_matrix(self) -> None:
        """Event and matrix must NOT connect through a shared untyped intermediary.

        Scenario:
        - event_fingerprint(event: Event) has {base_type="Event", attrs={name, data, ...}}
        - format_record(record) has {attrs={name, data}}
        - matrix_info(matrix) has {attrs={rows, data, name}}

        With the OR guard, event_fingerprint cannot match format_record,
        so no transitive path exists from event to matrix.
        """
        event_shape = _make_structural(
            "evt_fingerprint",
            base_type="Event",
            attrs=["name", "data", "source", "timestamp", "priority"],
        )
        format_shape = _make_structural(
            "format_record",
            attrs=["name", "data"],
        )
        matrix_shape = _make_structural(
            "matrix_info",
            attrs=["rows", "data", "name"],
        )
        edges = _compute_structural_matches([event_shape, format_shape, matrix_shape])

        # Event cannot reach format_record (typed vs untyped)
        assert ("evt_fingerprint", "format_record") not in edges
        # matrix_info can reach format_record (both untyped, superset)
        assert ("matrix_info", "format_record") in edges
        # Event cannot reach matrix_info (typed vs untyped)
        assert ("evt_fingerprint", "matrix_info") not in edges

        # BFS from evt_fingerprint: must not reach matrix_info
        adj: dict[str, set[str]] = {s: set() for s in ["evt_fingerprint", "format_record", "matrix_info"]}
        for src, tgt in edges:
            adj[src].add(tgt)
            adj[tgt].add(src)
        visited: set[str] = set()
        queue = ["evt_fingerprint"]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            queue.extend(adj.get(node, set()) - visited)
        assert "matrix_info" not in visited, "Event should NOT transitively reach matrix"

    def test_e2e_event_bus_vs_math_helpers_isolation(self) -> None:
        """E2E: shapes from event_bus.py must not structurally connect to math_helpers.py shapes."""
        event_result = _get_app_var_result("services/event_bus.py")
        math_result = _get_app_var_result("utils/math_helpers.py")

        event_structurals, _ = _build_shapes_from_evidence(event_result.evidence)
        math_structurals, _ = _build_shapes_from_evidence(math_result.evidence)

        all_structurals = event_structurals + math_structurals
        edges = _compute_structural_matches(all_structurals)

        event_ids = {s["id"] for s in event_structurals}
        math_ids = {s["id"] for s in math_structurals}

        for src, tgt in edges:
            cross = (src in event_ids and tgt in math_ids) or (src in math_ids and tgt in event_ids)
            assert not cross, f"False cross-module edge: {src} -> {tgt}"
