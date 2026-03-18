"""Graph-to-Git serializer (TICKET-820).

Serializes the FalkorDB graph state to the `.bumblebee/` directory structure
as JSON files for Git storage.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.graph.client import get_graph
from app.graph import logic_queries as lq

logger = logging.getLogger(__name__)


@dataclass
class SerializationReport:
    """Summary of a serialization operation.

    Attributes:
        nodes_written: Number of LogicNode files written.
        variables_written: Number of Variable group files written.
        edges_written: Number of edges in manifest.
        flows_written: Number of Flow files written.
        skipped: Number of unchanged files skipped (incremental).
    """

    nodes_written: int = 0
    variables_written: int = 0
    edges_written: int = 0
    flows_written: int = 0
    skipped: int = 0


def serialize_graph(output_dir: str) -> SerializationReport:
    """Serialize the full FalkorDB graph to `.bumblebee/` directory.

    Creates the directory structure:
      output_dir/meta.json
      output_dir/nodes/<uuid>.json
      output_dir/variables/var_<scope_hash>.json
      output_dir/edges/manifest.json
      output_dir/flows/flow_<name>.json

    Args:
        output_dir: Path to the `.bumblebee/` directory.

    Returns:
        SerializationReport with counts.
    """
    report = SerializationReport()
    graph = get_graph()
    base = Path(output_dir)

    # Create directories
    (base / "nodes").mkdir(parents=True, exist_ok=True)
    (base / "variables").mkdir(parents=True, exist_ok=True)
    (base / "edges").mkdir(parents=True, exist_ok=True)
    (base / "flows").mkdir(parents=True, exist_ok=True)
    (base / "vfs").mkdir(parents=True, exist_ok=True)

    # Serialize LogicNodes
    try:
        result = graph.query(lq.GET_ALL_LOGIC_NODES)
        for row in result.result_set:
            node = row[0]
            props = node.properties if hasattr(node, "properties") else node
            node_id = props.get("id", "")
            if not node_id:
                continue

            node_data = _node_to_dict(props)
            node_path = base / "nodes" / f"{node_id}.json"
            _write_json(node_path, node_data)
            report.nodes_written += 1
    except Exception as exc:
        logger.error("Error serializing nodes: %s", exc)

    # Serialize Variables (grouped by scope)
    try:
        result = graph.query(lq.GET_ALL_VARIABLES)
        scope_groups: dict[str, list[dict[str, Any]]] = {}
        for row in result.result_set:
            var = row[0]
            props = var.properties if hasattr(var, "properties") else var
            scope = props.get("scope", "")
            # Group by function scope (strip the variable name from the scope)
            func_scope = ".".join(scope.rsplit(".", 1)[:-1]) if "." in scope else scope
            if func_scope not in scope_groups:
                scope_groups[func_scope] = []
            scope_groups[func_scope].append(_var_to_dict(props))

        for scope, variables in scope_groups.items():
            scope_hash = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:8]
            var_data = {
                "scope": scope,
                "scope_hash": scope_hash,
                "variables": variables,
            }
            var_path = base / "variables" / f"var_{scope_hash}.json"
            _write_json(var_path, var_data)
            report.variables_written += 1
    except Exception as exc:
        logger.error("Error serializing variables: %s", exc)

    # Serialize Edges
    try:
        result = graph.query(lq.GET_ALL_EDGES)
        edges: list[dict[str, Any]] = []
        for row in result.result_set:
            edge_type = row[0]
            source = row[1]
            target = row[2]
            props = row[3] if len(row) > 3 and isinstance(row[3], dict) else {}
            edges.append({
                "type": edge_type,
                "source": source,
                "target": target,
                "properties": props,
            })

        manifest = {
            "schema_version": 1,
            "edge_count": len(edges),
            "edges": edges,
        }
        _write_json(base / "edges" / "manifest.json", manifest)
        report.edges_written = len(edges)
    except Exception as exc:
        logger.error("Error serializing edges: %s", exc)

    # Serialize Flows
    try:
        result = graph.query(lq.GET_ALL_FLOWS)
        for row in result.result_set:
            flow = row[0]
            props = flow.properties if hasattr(flow, "properties") else flow
            flow_name = props.get("name", "unnamed")
            flow_data = _flow_to_dict(props)
            flow_path = base / "flows" / f"flow_{_safe_filename(flow_name)}.json"
            _write_json(flow_path, flow_data)
            report.flows_written += 1
    except Exception as exc:
        logger.error("Error serializing flows: %s", exc)

    # Write meta.json
    meta = {
        "version": "1.0.0",
        "schema_version": 1,
        "graph_name": "bumblebee",
        "node_count": report.nodes_written,
        "variable_count": report.variables_written,
        "edge_count": report.edges_written,
        "flow_count": report.flows_written,
        "last_serialized": datetime.now(timezone.utc).isoformat(),
        "source_language": "python",
        "source_root": "",
    }
    _write_json(base / "meta.json", meta)

    logger.info(
        "Serialized: %d nodes, %d variable groups, %d edges, %d flows",
        report.nodes_written,
        report.variables_written,
        report.edges_written,
        report.flows_written,
    )

    return report


def _node_to_dict(props: Any) -> dict[str, Any]:
    """Convert a graph node's properties to a serializable dict."""
    data: dict[str, Any] = {}
    keys = [
        "id", "ast_hash", "structural_hash", "kind", "name", "module_path", "signature",
        "source_text", "semantic_intent", "docstring", "decorators",
        "params", "return_type", "tags", "class_id", "derived_from",
        "status", "created_at", "updated_at",
    ]
    for key in keys:
        val = props.get(key, None) if isinstance(props, dict) else getattr(props, key, None)
        # Parse JSON strings back to lists
        if key in ("decorators", "params", "tags") and isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
        data[key] = val
    return data


def _var_to_dict(props: Any) -> dict[str, Any]:
    """Convert a Variable node's properties to a serializable dict."""
    keys = ["id", "name", "scope", "origin_node_id", "origin_line", "type_hint", "is_parameter", "is_attribute", "created_at"]
    return {key: (props.get(key) if isinstance(props, dict) else getattr(props, key, None)) for key in keys}


def _flow_to_dict(props: Any) -> dict[str, Any]:
    """Convert a Flow node's properties to a serializable dict."""
    keys = [
        "id", "name", "description", "entry_point", "exit_points",
        "node_ids", "sub_flow_ids", "parent_flow_id", "promoted_node_id",
        "created_at", "updated_at",
    ]
    data: dict[str, Any] = {}
    for key in keys:
        val = props.get(key, None) if isinstance(props, dict) else getattr(props, key, None)
        if key in ("exit_points", "node_ids", "sub_flow_ids") and isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
        data[key] = val
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON with 2-space indent and sorted keys for clean Git diffs."""
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _safe_filename(name: str) -> str:
    """Sanitize a name for use as a filename."""
    return "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in name)
