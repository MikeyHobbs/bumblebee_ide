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

    # Load LogicNodes
    nodes_dir = base / "nodes"
    if nodes_dir.is_dir():
        for node_file in sorted(nodes_dir.glob("*.json")):
            try:
                data = json.loads(node_file.read_text(encoding="utf-8"))
                _load_logic_node(graph, data, strategy, report)
            except Exception as exc:
                report.errors.append(f"Error loading {node_file.name}: {exc}")

    # Load Variables
    vars_dir = base / "variables"
    if vars_dir.is_dir():
        for var_file in sorted(vars_dir.glob("var_*.json")):
            try:
                data = json.loads(var_file.read_text(encoding="utf-8"))
                for var_data in data.get("variables", []):
                    _load_variable(graph, var_data, report)
            except Exception as exc:
                report.errors.append(f"Error loading {var_file.name}: {exc}")

    # Load Edges
    edges_dir = base / "edges"
    manifest_path = edges_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for edge_data in manifest.get("edges", []):
                _load_edge(graph, edge_data, report)
        except Exception as exc:
            report.errors.append(f"Error loading edge manifest: {exc}")
    elif edges_dir.is_dir():
        # Check for sharded edge files
        for edge_file in sorted(edges_dir.glob("*.json")):
            try:
                data = json.loads(edge_file.read_text(encoding="utf-8"))
                for edge_data in data.get("edges", []):
                    _load_edge(graph, edge_data, report)
            except Exception as exc:
                report.errors.append(f"Error loading {edge_file.name}: {exc}")

    # Load Flows
    flows_dir = base / "flows"
    if flows_dir.is_dir():
        for flow_file in sorted(flows_dir.glob("flow_*.json")):
            try:
                data = json.loads(flow_file.read_text(encoding="utf-8"))
                _load_flow(graph, data, report)
            except Exception as exc:
                report.errors.append(f"Error loading {flow_file.name}: {exc}")

    logger.info(
        "Deserialized: %d nodes, %d variables, %d edges, %d flows, %d errors",
        report.nodes_loaded,
        report.variables_loaded,
        report.edges_loaded,
        report.flows_loaded,
        len(report.errors),
    )

    return report


def _load_logic_node(graph: Any, data: dict[str, Any], strategy: str, report: DeserializationReport) -> None:
    """Load a single LogicNode into the graph."""
    node_id = data.get("id", "")
    if not node_id:
        return

    # Serialize lists as JSON strings for graph storage
    params = data.get("params", [])
    if isinstance(params, list):
        params = json.dumps(params)
    decorators = data.get("decorators", [])
    if isinstance(decorators, list):
        decorators = json.dumps(decorators)
    tags = data.get("tags", [])
    if isinstance(tags, list):
        tags = json.dumps(tags)

    graph.query(
        lq.MERGE_LOGIC_NODE,
        params={
            "id": node_id,
            "ast_hash": data.get("ast_hash", ""),
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
        },
    )
    report.nodes_loaded += 1


def _load_variable(graph: Any, data: dict[str, Any], report: DeserializationReport) -> None:
    """Load a single Variable into the graph."""
    var_id = data.get("id", "")
    if not var_id:
        return

    graph.query(
        lq.MERGE_VARIABLE,
        params={
            "id": var_id,
            "name": data.get("name", ""),
            "scope": data.get("scope", ""),
            "origin_node_id": data.get("origin_node_id", ""),
            "origin_line": data.get("origin_line", 0),
            "type_hint": data.get("type_hint", ""),
            "is_parameter": data.get("is_parameter", False),
            "is_attribute": data.get("is_attribute", False),
            "created_at": data.get("created_at", ""),
        },
    )
    report.variables_loaded += 1


def _load_edge(graph: Any, data: dict[str, Any], report: DeserializationReport) -> None:
    """Load a single edge into the graph."""
    edge_type = data.get("type", "")
    source = data.get("source", "")
    target = data.get("target", "")
    props = data.get("properties", {})

    if not edge_type or not source or not target:
        return

    query = lq.EDGE_MERGE_QUERIES.get(edge_type)
    if query is None:
        report.errors.append(f"Unknown edge type: {edge_type}")
        return

    try:
        graph.query(query, params={"source_id": source, "target_id": target, "properties": props})
        report.edges_loaded += 1
    except Exception as exc:
        # Edge endpoints may not exist yet — log but don't fail
        logger.debug("Skipped edge %s->%s (%s): %s", source, target, edge_type, exc)


def _load_flow(graph: Any, data: dict[str, Any], report: DeserializationReport) -> None:
    """Load a single Flow into the graph."""
    flow_id = data.get("id", "")
    if not flow_id:
        return

    # Serialize lists for graph storage
    exit_points = data.get("exit_points", [])
    if isinstance(exit_points, list):
        exit_points = json.dumps(exit_points)
    node_ids = data.get("node_ids", [])
    if isinstance(node_ids, list):
        node_ids = json.dumps(node_ids)
    sub_flow_ids = data.get("sub_flow_ids", [])
    if isinstance(sub_flow_ids, list):
        sub_flow_ids = json.dumps(sub_flow_ids)

    graph.query(
        lq.MERGE_FLOW,
        params={
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
        },
    )
    report.flows_loaded += 1

    # Create STEP_OF edges for flow steps
    raw_node_ids = data.get("node_ids", [])
    if isinstance(raw_node_ids, str):
        try:
            raw_node_ids = json.loads(raw_node_ids)
        except (json.JSONDecodeError, TypeError):
            raw_node_ids = []

    for order, step_node_id in enumerate(raw_node_ids):
        try:
            graph.query(
                lq.EDGE_MERGE_QUERIES["STEP_OF"],
                params={
                    "source_id": step_node_id,
                    "target_id": flow_id,
                    "properties": {"step_order": order},
                },
            )
        except Exception:
            pass

    # Create CONTAINS_FLOW edges for sub-flows
    raw_sub_ids = data.get("sub_flow_ids", [])
    if isinstance(raw_sub_ids, str):
        try:
            raw_sub_ids = json.loads(raw_sub_ids)
        except (json.JSONDecodeError, TypeError):
            raw_sub_ids = []

    for order, sub_flow_id in enumerate(raw_sub_ids):
        try:
            graph.query(
                lq.EDGE_MERGE_QUERIES["CONTAINS_FLOW"],
                params={
                    "source_id": flow_id,
                    "target_id": sub_flow_id,
                    "properties": {"step_order": order},
                },
            )
        except Exception:
            pass
