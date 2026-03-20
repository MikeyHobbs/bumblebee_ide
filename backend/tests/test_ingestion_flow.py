"""Tests for end-to-end data-flow tracing through ingestion_flow.py.

Verifies that the extraction pipeline captures CALLS, PASSES_TO,
RETURNS, FEEDS, and TypeShape edges — then demonstrates the graph
queries that follow data through the full ``run()`` pipeline.
"""

from __future__ import annotations

import os
from typing import Any

from app.services.parsing.ast_parser import parse_file
from app.services.parsing.relationship_extractor import extract_relationships
from app.services.parsing.variable_extractor import extract_variables
from app.services.parsing.dataflow_extractor import extract_dataflow
from app.services.analysis.type_shape_service import build_shape_definition, compute_shape_hash

SAMPLE_APP_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "test_repos", "sample_app")
)

MODULE = "services.ingestion_flow"


def _load_source() -> str:
    path = os.path.join(SAMPLE_APP_DIR, "services", "ingestion_flow.py")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _extract_all():  # type: ignore[no-untyped-def]
    """Run the full extraction pipeline on ingestion_flow.py."""
    source = _load_source()
    file_path = "services/ingestion_flow.py"
    parsed = parse_file(source, file_path)
    rels = extract_relationships(source, file_path, parsed.nodes)
    var_result = extract_variables(source, file_path, parsed.nodes)
    dataflow = extract_dataflow(
        source, file_path, parsed.nodes,
        rels, var_result.nodes, var_result.edges,
    )
    return parsed, rels, var_result, dataflow


# ===================================================================
# Helpers: build in-memory adjacency from extracted edges
# ===================================================================

def _calls_adj(rels) -> dict[str, list[str]]:  # type: ignore[no-untyped-def]
    """Build caller → [callees] adjacency from CALLS edges."""
    adj: dict[str, list[str]] = {}
    for e in rels:
        if e.edge_type == "CALLS":
            adj.setdefault(e.source_name, []).append(e.target_name)
    return adj


def _passes_to_adj(dataflow) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    """Return (source_var, target_var) pairs for PASSES_TO edges."""
    return [
        (e.source_name, e.target_name)
        for e in dataflow.edges
        if e.edge_type == "PASSES_TO"
    ]


def _returns_map(var_result) -> dict[str, list[str]]:  # type: ignore[no-untyped-def]
    """Build function → [returned variables] map from RETURNS edges."""
    ret: dict[str, list[str]] = {}
    for e in var_result.edges:
        if e.edge_type == "RETURNS":
            ret.setdefault(e.source_name, []).append(e.target_name)
    return ret


def _feeds_adj(dataflow) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    """Return (source_var, target_var) pairs for FEEDS edges."""
    return [
        (e.source_name, e.target_name)
        for e in dataflow.edges
        if e.edge_type == "FEEDS"
    ]


# ===================================================================
# Test class: CALLS edges
# ===================================================================

class TestCallsEdges:
    """Verify that run() CALLS each pipeline stage."""

    def test_run_calls_parse_input(self) -> None:
        _, rels, _, _ = _extract_all()
        adj = _calls_adj(rels)
        callees = adj.get(f"{MODULE}.run", [])
        assert f"{MODULE}.parse_input" in callees

    def test_run_calls_validate(self) -> None:
        _, rels, _, _ = _extract_all()
        adj = _calls_adj(rels)
        callees = adj.get(f"{MODULE}.run", [])
        assert f"{MODULE}.validate" in callees

    def test_run_calls_enrich(self) -> None:
        _, rels, _, _ = _extract_all()
        adj = _calls_adj(rels)
        callees = adj.get(f"{MODULE}.run", [])
        assert f"{MODULE}.enrich" in callees

    def test_run_calls_store_record(self) -> None:
        _, rels, _, _ = _extract_all()
        adj = _calls_adj(rels)
        callees = adj.get(f"{MODULE}.run", [])
        assert f"{MODULE}.store_record" in callees

    def test_run_calls_exactly_four(self) -> None:
        _, rels, _, _ = _extract_all()
        adj = _calls_adj(rels)
        callees = adj.get(f"{MODULE}.run", [])
        assert len(callees) == 4


# ===================================================================
# Test class: PASSES_TO edges (argument → parameter)
# ===================================================================

class TestPassesToEdges:
    """Verify PASSES_TO edges through the pipeline chain."""

    def test_raw_passes_to_parse_input(self) -> None:
        """run.raw → parse_input.raw."""
        _, _, _, dataflow = _extract_all()
        pt = _passes_to_adj(dataflow)
        assert (f"{MODULE}.run.raw", f"{MODULE}.parse_input.raw") in pt

    def test_parsed_passes_to_validate(self) -> None:
        """run.parsed → validate.record."""
        _, _, _, dataflow = _extract_all()
        pt = _passes_to_adj(dataflow)
        assert (f"{MODULE}.run.parsed", f"{MODULE}.validate.record") in pt

    def test_valid_passes_to_enrich(self) -> None:
        """run.valid → enrich.record."""
        _, _, _, dataflow = _extract_all()
        pt = _passes_to_adj(dataflow)
        assert (f"{MODULE}.run.valid", f"{MODULE}.enrich.record") in pt

    def test_enriched_passes_to_store(self) -> None:
        """run.enriched → store_record.record."""
        _, _, _, dataflow = _extract_all()
        pt = _passes_to_adj(dataflow)
        assert (f"{MODULE}.run.enriched", f"{MODULE}.store_record.record") in pt

    def test_db_passes_to_store(self) -> None:
        """run.db → store_record.db."""
        _, _, _, dataflow = _extract_all()
        pt = _passes_to_adj(dataflow)
        assert (f"{MODULE}.run.db", f"{MODULE}.store_record.db") in pt


# ===================================================================
# Test class: RETURNS edges
# ===================================================================

class TestReturnsEdges:
    """Verify each stage returns its output variable."""

    def test_parse_input_returns_record(self) -> None:
        _, _, var_result, _ = _extract_all()
        ret = _returns_map(var_result)
        returned = ret.get(f"{MODULE}.parse_input", [])
        assert f"{MODULE}.parse_input.record" in returned

    def test_validate_returns_record(self) -> None:
        _, _, var_result, _ = _extract_all()
        ret = _returns_map(var_result)
        returned = ret.get(f"{MODULE}.validate", [])
        assert f"{MODULE}.validate.record" in returned

    def test_enrich_returns_record(self) -> None:
        _, _, var_result, _ = _extract_all()
        ret = _returns_map(var_result)
        returned = ret.get(f"{MODULE}.enrich", [])
        assert f"{MODULE}.enrich.record" in returned

    def test_store_returns_row_id(self) -> None:
        _, _, var_result, _ = _extract_all()
        ret = _returns_map(var_result)
        returned = ret.get(f"{MODULE}.store_record", [])
        assert f"{MODULE}.store_record.row_id" in returned

    def test_run_returns_row_id(self) -> None:
        _, _, var_result, _ = _extract_all()
        ret = _returns_map(var_result)
        returned = ret.get(f"{MODULE}.run", [])
        assert f"{MODULE}.run.row_id" in returned


# ===================================================================
# Test class: FEEDS edges (intra-function data flow)
# ===================================================================

class TestFeedsEdges:
    """Verify FEEDS edges within functions."""

    def test_parts_feeds_record_in_parse(self) -> None:
        """parse_input: parts feeds into record (parts used in record assignment)."""
        _, _, _, dataflow = _extract_all()
        feeds = _feeds_adj(dataflow)
        assert (f"{MODULE}.parse_input.parts", f"{MODULE}.parse_input.record") in feeds

    def test_raw_feeds_parts_in_parse(self) -> None:
        """parse_input: raw feeds into parts (raw.split assigns parts)."""
        _, _, _, dataflow = _extract_all()
        feeds = _feeds_adj(dataflow)
        assert (f"{MODULE}.parse_input.raw", f"{MODULE}.parse_input.parts") in feeds


# ===================================================================
# Test class: Full pipeline traversal (the graph query)
# ===================================================================

class TestPipelineTraversal:
    """Simulate graph queries that follow data through the pipeline.

    These tests demonstrate that without a running FalkorDB, we can
    build an in-memory graph from extracted edges and answer the same
    questions that Cypher queries would.
    """

    def test_follow_calls_chain_from_run(self) -> None:
        """Query: MATCH (run)-[:CALLS]->(callee) RETURN callee
        Verifies we can discover the full call chain."""
        _, rels, _, _ = _extract_all()
        adj = _calls_adj(rels)
        callees = set(adj.get(f"{MODULE}.run", []))
        assert callees == {
            f"{MODULE}.parse_input",
            f"{MODULE}.validate",
            f"{MODULE}.enrich",
            f"{MODULE}.store_record",
        }

    def test_follow_data_from_input_to_output(self) -> None:
        """Query: MATCH path = (start)-[:PASSES_TO*1..5]->(end)
        Follow run.raw through the full PASSES_TO chain.

        run.raw → parse_input.raw
        run.parsed → validate.record
        run.valid → enrich.record
        run.enriched → store_record.record

        These are hop-by-hop within run(). The full data lineage is:
        raw → parsed → valid → enriched → row_id
        """
        _, _, _, dataflow = _extract_all()
        pt = _passes_to_adj(dataflow)

        # Build adjacency for BFS
        adj: dict[str, set[str]] = {}
        for src, tgt in pt:
            adj.setdefault(src, set()).add(tgt)

        # All variables reachable from run's namespace via PASSES_TO
        run_vars = {src for src, _ in pt if src.startswith(f"{MODULE}.run.")}
        all_targets: set[str] = set()
        for rv in run_vars:
            all_targets.update(adj.get(rv, set()))

        # Each pipeline stage receives data from run
        assert f"{MODULE}.parse_input.raw" in all_targets
        assert f"{MODULE}.validate.record" in all_targets
        assert f"{MODULE}.enrich.record" in all_targets
        assert f"{MODULE}.store_record.record" in all_targets

    def test_data_lineage_through_returns_and_passes(self) -> None:
        """Simulate multi-hop query: follow RETURNS + PASSES_TO to trace
        the full data lineage from raw input to stored row_id.

        The lineage is:
          run.raw -[PASSES_TO]-> parse_input.raw
          parse_input -[RETURNS]-> parse_input.record
          run.parsed -[PASSES_TO]-> validate.record  (parsed = parse_input(raw))
          validate -[RETURNS]-> validate.record
          run.valid -[PASSES_TO]-> enrich.record     (valid = validate(parsed))
          enrich -[RETURNS]-> enrich.record
          run.enriched -[PASSES_TO]-> store_record.record  (enriched = enrich(valid))
          store_record -[RETURNS]-> store_record.row_id
          run -[RETURNS]-> run.row_id
        """
        _, rels, var_result, dataflow = _extract_all()

        # Build combined graph
        calls = _calls_adj(rels)
        passes = _passes_to_adj(dataflow)
        returns = _returns_map(var_result)

        # Verify the chain: run calls 4 stages in sequence
        run_callees = calls.get(f"{MODULE}.run", [])
        assert len(run_callees) == 4

        # Each stage returns a variable
        for stage in ["parse_input", "validate", "enrich", "store_record"]:
            fqn = f"{MODULE}.{stage}"
            assert len(returns.get(fqn, [])) >= 1, f"{stage} should RETURN something"

        # PASSES_TO connects run's locals to stage parameters
        pass_map = {src: tgt for src, tgt in passes}
        assert pass_map[f"{MODULE}.run.raw"] == f"{MODULE}.parse_input.raw"
        assert pass_map[f"{MODULE}.run.parsed"] == f"{MODULE}.validate.record"
        assert pass_map[f"{MODULE}.run.valid"] == f"{MODULE}.enrich.record"
        assert pass_map[f"{MODULE}.run.enriched"] == f"{MODULE}.store_record.record"

    def test_find_all_consumers_of_record_shape(self) -> None:
        """Query: find all functions that consume a dict via subscript access.

        This simulates:
          MATCH (v:Variable)-[:HAS_SHAPE]->(ts:TypeShape)
          WHERE ts.kind = "structural"
          RETURN v.scope, ts.definition

        We verify that validate and enrich both produce structural shapes
        from their record parameter, and that store_record's db parameter
        produces a distinct structural shape with methods.
        """
        source = _load_source()
        file_path = "services/ingestion_flow.py"
        parsed = parse_file(source, file_path)
        var_result = extract_variables(source, file_path, parsed.nodes)

        # Collect shape evidence for all variables with structural access
        record_shapes: dict[str, dict[str, Any]] = {}
        for key, ev in var_result.evidence.items():
            if not (ev.attrs_accessed or ev.subscripts_accessed or ev.methods_called):
                continue
            defn = build_shape_definition(ev)
            if defn and defn["kind"] == "structural":
                record_shapes[key] = defn

        # validate.record subscripts: {name, value}
        val_record = record_shapes.get(f"{MODULE}.validate.record")
        assert val_record is not None, "validate.record should have structural shape"
        assert "name" in val_record.get("subscripts", [])
        assert "value" in val_record.get("subscripts", [])

        # enrich.record subscripts: {hash, timestamp} (subscript assignments)
        enrich_record = record_shapes.get(f"{MODULE}.enrich.record")
        assert enrich_record is not None, "enrich.record should have structural shape"
        assert "timestamp" in enrich_record.get("subscripts", [])

        # Both have base_type="dict" → routed through hint hub, not pairwise
        assert val_record.get("base_type") == "dict"
        assert enrich_record.get("base_type") == "dict"

        # store_record.db has methods {execute, commit} + attr {lastrowid}
        db_shape = record_shapes.get(f"{MODULE}.store_record.db")
        assert db_shape is not None, "store_record.db should have structural shape"
        assert "execute" in db_shape.get("methods", [])
        assert "commit" in db_shape.get("methods", [])

        # db shape has NO base_type → it's an untyped structural (duck-typed)
        assert not db_shape.get("base_type"), "db should be untyped (duck-typed)"
