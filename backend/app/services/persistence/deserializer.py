"""Git-to-Graph deserializer (TICKET-821).

Loads a `.bumblebee/` directory into FalkorDB on startup.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.graph.client import get_graph
from app.graph import logic_queries as lq

logger = logging.getLogger(__name__)


@dataclass
class DeserializationReport:
    """Summary of a deserialization operation.

    Attributes:
        nodes_loaded: Number of LogicNodes loaded.
        variables_loaded: Number of Variables loaded.
        edges_loaded: Number of edges loaded.
        flows_loaded: Number of Flows loaded.
        errors: List of error messages.
        conflicts: List of conflict descriptions.
    """

    nodes_loaded: int = 0
    variables_loaded: int = 0
    edges_loaded: int = 0
    flows_loaded: int = 0
    errors: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def deserialize_graph(
    input_dir: str,
    strategy: str = "replace",
) -> DeserializationReport:
    """Load a `.bumblebee/` directory into FalkorDB.

    Args:
        input_dir: Path to the `.bumblebee/` directory.
        strategy: "replace" (clear graph first) or "merge" (skip existing, add new).

    Returns:
        DeserializationReport with counts and any errors.
    """
    report = DeserializationReport()
    base = Path(input_dir)

    if not base.is_dir():
        report.errors.append(f"Not a directory: {input_dir}")
        return report

    # Validate meta.json
    meta_path = base / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            logger.info(
                "Loading graph: %d nodes, %d edges, schema v%s",
                meta.get("node_count", "?"),
                meta.get("edge_count", "?"),
                meta.get("schema_version", "?"),
            )
        except Exception as exc:
            report.errors.append(f"Invalid meta.json: {exc}")

    graph = get_graph()

    # Clear graph if replacing
    if strategy == "replace":
        try:
            graph.query("MATCH (n) DETACH DELETE n")
            logger.info("Cleared existing graph data")
        except Exception as exc:
            report.errors.append(f"Failed to clear graph: {exc}")
            return report

    # ── Batch load LogicNodes ──
    all_node_items: list[dict[str, Any]] = []
    nodes_dir = base / "nodes"
    if nodes_dir.is_dir():
        for node_file in sorted(nodes_dir.glob("*.json")):
            try:
                data = json.loads(node_file.read_text(encoding="utf-8"))
                item = _prepare_node_item(data)
                if item:
                    all_node_items.append(item)
                    report.nodes_loaded += 1
            except Exception as exc:
                report.errors.append(f"Error loading {node_file.name}: {exc}")

    if all_node_items:
        _chunked_query(graph, lq.BATCH_MERGE_LOGIC_NODES, all_node_items)

    # ── Batch load Variables ──
    all_var_items: list[dict[str, Any]] = []
    vars_dir = base / "variables"
    if vars_dir.is_dir():
        for var_file in sorted(vars_dir.glob("var_*.json")):
            try:
                data = json.loads(var_file.read_text(encoding="utf-8"))
                for var_data in data.get("variables", []):
                    item = _prepare_variable_item(var_data)
                    if item:
                        all_var_items.append(item)
                        report.variables_loaded += 1
            except Exception as exc:
                report.errors.append(f"Error loading {var_file.name}: {exc}")

    if all_var_items:
        _chunked_query(graph, lq.BATCH_MERGE_VARIABLES, all_var_items)

    # ── Batch load TypeShapes ──
    all_ts_items: list[dict[str, Any]] = []
    ts_dir = base / "type_shapes"
    if ts_dir.is_dir():
        for ts_file in sorted(ts_dir.glob("ts_*.json")):
            try:
                data = json.loads(ts_file.read_text(encoding="utf-8"))
                item = _prepare_type_shape_item(data)
                if item:
                    all_ts_items.append(item)
            except Exception as exc:
                report.errors.append(f"Error loading {ts_file.name}: {exc}")

    if all_ts_items:
        _chunked_query(graph, lq.BATCH_MERGE_TYPE_SHAPES, all_ts_items)

    # ── Batch load Edges (grouped by type) ──
    edge_buckets: dict[str, list[dict[str, Any]]] = {}
    edges_dir = base / "edges"
    all_edge_datas: list[dict[str, Any]] = []

    manifest_path = edges_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            all_edge_datas.extend(manifest.get("edges", []))
        except Exception as exc:
            report.errors.append(f"Error loading edge manifest: {exc}")
    elif edges_dir.is_dir():
        for edge_file in sorted(edges_dir.glob("*.json")):
            try:
                data = json.loads(edge_file.read_text(encoding="utf-8"))
                all_edge_datas.extend(data.get("edges", []))
            except Exception as exc:
                report.errors.append(f"Error loading {edge_file.name}: {exc}")

    for edge_data in all_edge_datas:
        edge_type = edge_data.get("type", "")
        source = edge_data.get("source", "")
        target = edge_data.get("target", "")
        if not edge_type or not source or not target:
            continue
        if edge_type not in lq.BATCH_EDGE_MERGE_QUERIES:
            report.errors.append(f"Unknown edge type: {edge_type}")
            continue
        props = edge_data.get("properties", {})
        item: dict[str, Any] = {"source_id": source, "target_id": target}
        item.update(props)
        edge_buckets.setdefault(edge_type, []).append(item)
        report.edges_loaded += 1

    for edge_type, items in edge_buckets.items():
        try:
            _chunked_query(graph, lq.BATCH_EDGE_MERGE_QUERIES[edge_type], items)
        except Exception as exc:
            report.errors.append(f"Batch edge error ({edge_type}): {exc}")

    # ── Batch load Flows ──
    all_flow_items: list[dict[str, Any]] = []
    step_of_items: list[dict[str, Any]] = []
    contains_flow_items: list[dict[str, Any]] = []

    flows_dir = base / "flows"
    if flows_dir.is_dir():
        for flow_file in sorted(flows_dir.glob("flow_*.json")):
            try:
                data = json.loads(flow_file.read_text(encoding="utf-8"))
                flow_item = _prepare_flow_item(data)
                if flow_item:
                    all_flow_items.append(flow_item)
                    report.flows_loaded += 1
                    _collect_flow_edges(data, step_of_items, contains_flow_items)
            except Exception as exc:
                report.errors.append(f"Error loading {flow_file.name}: {exc}")

    if all_flow_items:
        _chunked_query(graph, lq.BATCH_MERGE_FLOWS, all_flow_items)
    if step_of_items:
        _chunked_query(graph, lq.BATCH_EDGE_MERGE_QUERIES["STEP_OF"], step_of_items)
    if contains_flow_items:
        _chunked_query(graph, lq.BATCH_EDGE_MERGE_QUERIES["CONTAINS_FLOW"], contains_flow_items)

    logger.info(
        "Deserialized: %d nodes, %d variables, %d edges, %d flows, %d errors",
        report.nodes_loaded,
        report.variables_loaded,
        report.edges_loaded,
        report.flows_loaded,
        len(report.errors),
    )

    return report


BATCH_CHUNK_SIZE = 500


def _chunked_query(graph: Any, query: str, items: list[dict[str, Any]], chunk_size: int = BATCH_CHUNK_SIZE) -> None:
    """Execute a batch UNWIND query in chunks to avoid memory limits."""
    if not items:
        return
    for i in range(0, len(items), chunk_size):
        graph.query(query, params={"items": items[i : i + chunk_size]})


def _prepare_node_item(data: dict[str, Any]) -> dict[str, Any] | None:
    """Prepare a LogicNode dict for batch UNWIND insertion."""
    node_id = data.get("id", "")
    if not node_id:
        return None

    params = data.get("params", [])
    if isinstance(params, list):
        params = json.dumps(params)
    decorators = data.get("decorators", [])
    if isinstance(decorators, list):
        decorators = json.dumps(decorators)
    tags = data.get("tags", [])
    if isinstance(tags, list):
        tags = json.dumps(tags)

    return {
        "id": node_id,
        "ast_hash": data.get("ast_hash", ""),
        "structural_hash": data.get("structural_hash", ""),
        "kind": data.get("kind", "function"),
        "name": data.get("name", ""),
        "module_path": data.get("module_path", ""),
        "signature": data.get("signature", ""),
        "source_text": data.get("source_text", ""),
        "semantic_intent": data.get("semantic_intent", ""),
        "docstring": data.get("docstring", ""),
        "decorators": decorators,
        "params": params,
        "return_type": data.get("return_type", ""),
        "tags": tags,
        "class_id": data.get("class_id", ""),
        "derived_from": data.get("derived_from", ""),
        "start_line": data.get("start_line", 0),
        "end_line": data.get("end_line", 0),
        "status": data.get("status", "active"),
        "created_at": data.get("created_at", ""),
        "updated_at": data.get("updated_at", ""),
    }


def _prepare_variable_item(data: dict[str, Any]) -> dict[str, Any] | None:
    """Prepare a Variable dict for batch UNWIND insertion."""
    var_id = data.get("id", "")
    if not var_id:
        return None

    return {
        "id": var_id,
        "name": data.get("name", ""),
        "scope": data.get("scope", ""),
        "origin_node_id": data.get("origin_node_id", ""),
        "origin_line": data.get("origin_line", 0),
        "type_hint": data.get("type_hint", ""),
        "is_parameter": data.get("is_parameter", False),
        "is_attribute": data.get("is_attribute", False),
        "created_at": data.get("created_at", ""),
    }


def _prepare_type_shape_item(data: dict[str, Any]) -> dict[str, Any] | None:
    """Prepare a TypeShape dict for batch UNWIND insertion."""
    ts_id = data.get("id", "")
    if not ts_id:
        return None

    definition = data.get("definition", {})
    if isinstance(definition, dict):
        definition = json.dumps(definition, sort_keys=True)

    return {
        "id": ts_id,
        "shape_hash": data.get("shape_hash", ""),
        "kind": data.get("kind", ""),
        "base_type": data.get("base_type", ""),
        "definition": definition,
        "created_at": data.get("created_at", ""),
    }


def _prepare_flow_item(data: dict[str, Any]) -> dict[str, Any] | None:
    """Prepare a Flow dict for batch UNWIND insertion."""
    flow_id = data.get("id", "")
    if not flow_id:
        return None

    exit_points = data.get("exit_points", [])
    if isinstance(exit_points, list):
        exit_points = json.dumps(exit_points)
    node_ids = data.get("node_ids", [])
    if isinstance(node_ids, list):
        node_ids = json.dumps(node_ids)
    sub_flow_ids = data.get("sub_flow_ids", [])
    if isinstance(sub_flow_ids, list):
        sub_flow_ids = json.dumps(sub_flow_ids)

    return {
        "id": flow_id,
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "entry_point": data.get("entry_point", ""),
        "exit_points": exit_points,
        "node_ids": node_ids,
        "sub_flow_ids": sub_flow_ids,
        "parent_flow_id": data.get("parent_flow_id", ""),
        "promoted_node_id": data.get("promoted_node_id", ""),
        "created_at": data.get("created_at", ""),
        "updated_at": data.get("updated_at", ""),
    }


def _collect_flow_edges(
    data: dict[str, Any],
    step_of_items: list[dict[str, Any]],
    contains_flow_items: list[dict[str, Any]],
) -> None:
    """Collect STEP_OF and CONTAINS_FLOW edge items from a flow's raw data."""
    flow_id = data.get("id", "")

    raw_node_ids = data.get("node_ids", [])
    if isinstance(raw_node_ids, str):
        try:
            raw_node_ids = json.loads(raw_node_ids)
        except (json.JSONDecodeError, TypeError):
            raw_node_ids = []

    for order, step_node_id in enumerate(raw_node_ids):
        step_of_items.append({
            "source_id": step_node_id,
            "target_id": flow_id,
            "step_order": order,
        })

    raw_sub_ids = data.get("sub_flow_ids", [])
    if isinstance(raw_sub_ids, str):
        try:
            raw_sub_ids = json.loads(raw_sub_ids)
        except (json.JSONDecodeError, TypeError):
            raw_sub_ids = []

    for order, sub_flow_id in enumerate(raw_sub_ids):
        contains_flow_items.append({
            "source_id": flow_id,
            "target_id": sub_flow_id,
            "step_order": order,
        })
