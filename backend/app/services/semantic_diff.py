"""Semantic diff service for comparing graph states (TICKET-822).

Compares two serialized `.bumblebee/` directory snapshots and reports structural
differences: added/removed/modified nodes, edges, and variables.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.logic_models import (
    EdgeResponse,
    EdgeType,
    LogicNodeKind,
    LogicNodeResponse,
    NodeStatus,
    ParamKind,
    ParamSpec,
    SemanticDiff,
    VariableResponse,
)
from app.services.serializer import serialize_graph

logger = logging.getLogger(__name__)


def compute_diff(old_dir: str, new_dir: str) -> SemanticDiff:
    """Compare two `.bumblebee/` directories and return structural differences.

    Nodes are matched by UUID. A node present only in *new_dir* is "added";
    only in *old_dir* is "removed". If the same UUID exists in both but the
    ``ast_hash`` differs the node is "modified".

    Edges are matched by the ``(type, source, target)`` tuple.
    Variables are matched by their ``id``.

    Args:
        old_dir: Path to the older `.bumblebee/` snapshot.
        new_dir: Path to the newer `.bumblebee/` snapshot.

    Returns:
        A SemanticDiff describing all differences.
    """
    old_nodes = _load_nodes_from_dir(old_dir)
    new_nodes = _load_nodes_from_dir(new_dir)

    old_edges = _load_edges_from_dir(old_dir)
    new_edges = _load_edges_from_dir(new_dir)

    old_vars = _load_variables_from_dir(old_dir)
    new_vars = _load_variables_from_dir(new_dir)

    # --- Nodes ---
    old_ids = set(old_nodes.keys())
    new_ids = set(new_nodes.keys())

    added_nodes = [_node_dict_to_response(new_nodes[nid]) for nid in sorted(new_ids - old_ids)]
    removed_nodes = [_node_dict_to_response(old_nodes[nid]) for nid in sorted(old_ids - new_ids)]

    modified_nodes: list[dict[str, Any]] = []
    for nid in sorted(old_ids & new_ids):
        old_hash = old_nodes[nid].get("ast_hash", "")
        new_hash = new_nodes[nid].get("ast_hash", "")
        if old_hash != new_hash:
            changed_fields: dict[str, Any] = {}
            for key in new_nodes[nid]:
                if old_nodes[nid].get(key) != new_nodes[nid].get(key):
                    changed_fields[key] = {
                        "old": old_nodes[nid].get(key),
                        "new": new_nodes[nid].get(key),
                    }
            modified_nodes.append({
                "id": nid,
                "old_ast_hash": old_hash,
                "new_ast_hash": new_hash,
                "changed_fields": changed_fields,
            })

    # --- Edges ---
    def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
        return (str(edge.get("type", "")), str(edge.get("source", "")), str(edge.get("target", "")))

    old_edge_map = {_edge_key(e): e for e in old_edges}
    new_edge_map = {_edge_key(e): e for e in new_edges}

    old_edge_keys = set(old_edge_map.keys())
    new_edge_keys = set(new_edge_map.keys())

    added_edges = [_edge_dict_to_response(new_edge_map[k]) for k in sorted(new_edge_keys - old_edge_keys)]
    removed_edges = [_edge_dict_to_response(old_edge_map[k]) for k in sorted(old_edge_keys - new_edge_keys)]

    # --- Variables ---
    old_var_ids = set(old_vars.keys())
    new_var_ids = set(new_vars.keys())

    added_variables = [_var_dict_to_response(new_vars[vid]) for vid in sorted(new_var_ids - old_var_ids)]
    removed_variables = [_var_dict_to_response(old_vars[vid]) for vid in sorted(old_var_ids - new_var_ids)]

    return SemanticDiff(
        added_nodes=added_nodes,
        removed_nodes=removed_nodes,
        modified_nodes=modified_nodes,
        added_edges=added_edges,
        removed_edges=removed_edges,
        added_variables=added_variables,
        removed_variables=removed_variables,
    )


def compute_diff_from_graph(serialized_dir: str) -> SemanticDiff:
    """Compare a serialized `.bumblebee/` directory against the live FalkorDB graph.

    The live graph is serialized to a temporary directory, then compared against
    *serialized_dir*. The temp directory is cleaned up after comparison.

    Args:
        serialized_dir: Path to the on-disk `.bumblebee/` snapshot to compare.

    Returns:
        A SemanticDiff where "added" means present in the live graph but not on
        disk, and "removed" means present on disk but not in the live graph.
    """
    tmp_dir = tempfile.mkdtemp(prefix="bumblebee_diff_")
    try:
        serialize_graph(tmp_dir)
        return compute_diff(old_dir=serialized_dir, new_dir=tmp_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _load_nodes_from_dir(dir_path: str) -> dict[str, dict[str, Any]]:
    """Read all ``nodes/*.json`` files and return a mapping of UUID to node data.

    Args:
        dir_path: Root of the `.bumblebee/` directory.

    Returns:
        Dict keyed by node UUID with raw dict values.
    """
    nodes: dict[str, dict[str, Any]] = {}
    nodes_dir = Path(dir_path) / "nodes"
    if not nodes_dir.is_dir():
        return nodes

    for node_file in sorted(nodes_dir.glob("*.json")):
        try:
            data = json.loads(node_file.read_text(encoding="utf-8"))
            node_id = data.get("id", node_file.stem)
            nodes[node_id] = data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping unreadable node file %s: %s", node_file, exc)
    return nodes


def _load_edges_from_dir(dir_path: str) -> list[dict[str, Any]]:
    """Read ``edges/manifest.json`` and return a list of edge dicts.

    Args:
        dir_path: Root of the `.bumblebee/` directory.

    Returns:
        List of edge dicts with keys ``type``, ``source``, ``target``, ``properties``.
    """
    manifest_path = Path(dir_path) / "edges" / "manifest.json"
    if not manifest_path.is_file():
        return []

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return data.get("edges", [])
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read edge manifest %s: %s", manifest_path, exc)
        return []


def _load_variables_from_dir(dir_path: str) -> dict[str, dict[str, Any]]:
    """Read all ``variables/var_*.json`` files and return a mapping of variable ID to data.

    Each file contains ``{"scope": ..., "variables": [...]}``. Variables are
    flattened across all scope files and keyed by their ``id``.

    Args:
        dir_path: Root of the `.bumblebee/` directory.

    Returns:
        Dict keyed by variable ID with raw dict values.
    """
    variables: dict[str, dict[str, Any]] = {}
    var_dir = Path(dir_path) / "variables"
    if not var_dir.is_dir():
        return variables

    for var_file in sorted(var_dir.glob("var_*.json")):
        try:
            data = json.loads(var_file.read_text(encoding="utf-8"))
            for var in data.get("variables", []):
                var_id = var.get("id", "")
                if var_id:
                    variables[var_id] = var
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping unreadable variable file %s: %s", var_file, exc)
    return variables


def _node_dict_to_response(data: dict[str, Any]) -> LogicNodeResponse:
    """Convert a raw node dict (from JSON) to a ``LogicNodeResponse``.

    Args:
        data: Dict with node fields as stored in ``nodes/<uuid>.json``.

    Returns:
        Validated LogicNodeResponse instance.
    """
    params_raw = data.get("params") or []
    params = [
        ParamSpec(
            name=p.get("name", ""),
            type_hint=p.get("type_hint"),
            default=p.get("default"),
            kind=ParamKind(p["kind"]) if p.get("kind") else ParamKind.POSITIONAL_OR_KEYWORD,
        )
        for p in params_raw
        if isinstance(p, dict)
    ]

    return LogicNodeResponse(
        id=data.get("id", ""),
        ast_hash=data.get("ast_hash", ""),
        kind=LogicNodeKind(data["kind"]) if data.get("kind") else LogicNodeKind.FUNCTION,
        name=data.get("name", ""),
        module_path=data.get("module_path", ""),
        signature=data.get("signature", ""),
        source_text=data.get("source_text", ""),
        semantic_intent=data.get("semantic_intent"),
        docstring=data.get("docstring"),
        decorators=data.get("decorators") or [],
        params=params,
        return_type=data.get("return_type"),
        tags=data.get("tags") or [],
        class_id=data.get("class_id"),
        derived_from=data.get("derived_from"),
        start_line=data.get("start_line"),
        end_line=data.get("end_line"),
        status=NodeStatus(data["status"]) if data.get("status") else NodeStatus.ACTIVE,
        created_at=_parse_datetime(data.get("created_at")),
        updated_at=_parse_datetime(data.get("updated_at")),
        warnings=data.get("warnings") or [],
    )


def _var_dict_to_response(data: dict[str, Any]) -> VariableResponse:
    """Convert a raw variable dict (from JSON) to a ``VariableResponse``.

    Args:
        data: Dict with variable fields as stored in ``variables/var_*.json``.

    Returns:
        Validated VariableResponse instance.
    """
    return VariableResponse(
        id=data.get("id", ""),
        name=data.get("name", ""),
        scope=data.get("scope", ""),
        origin_node_id=data.get("origin_node_id", ""),
        origin_line=data.get("origin_line"),
        type_hint=data.get("type_hint"),
        is_parameter=bool(data.get("is_parameter", False)),
        is_attribute=bool(data.get("is_attribute", False)),
        created_at=_parse_datetime(data.get("created_at")),
    )


def _edge_dict_to_response(data: dict[str, Any]) -> EdgeResponse:
    """Convert a raw edge dict (from JSON) to an ``EdgeResponse``.

    Args:
        data: Dict with edge fields as stored in ``edges/manifest.json``.

    Returns:
        Validated EdgeResponse instance.
    """
    return EdgeResponse(
        type=EdgeType(data["type"]) if data.get("type") else EdgeType.CALLS,
        source=data.get("source", ""),
        target=data.get("target", ""),
        properties=data.get("properties") or {},
    )


def _parse_datetime(value: Any) -> datetime:
    """Best-effort parsing of a datetime value from JSON.

    Handles ISO-format strings, unix timestamps, and ``None``.

    Args:
        value: Raw datetime value from deserialized JSON.

    Returns:
        A timezone-aware ``datetime`` instance.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return datetime.now(timezone.utc)
