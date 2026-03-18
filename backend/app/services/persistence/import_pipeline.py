"""Python-to-LogicNode import pipeline (TICKET-830).

Converts existing Python source files into LogicNodes in the graph,
reusing the existing AST parser, relationship extractor, variable extractor,
and dataflow extractor.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.graph.client import get_graph
from app.graph import logic_queries as lq
from app.models.logic_models import LogicNodeCreate, LogicNodeKind, LogicNodeResponse
from app.services.parsing.ast_parser import ParsedNode, ParseResult, parse_file
from app.services.analysis.hash_identity import (
    compute_ast_hash,
    compute_structural_hash,
    extract_params_detailed,
    extract_return_type,
    extract_signature_text,
    generate_deterministic_node_id,
)
from app.services.parsing.relationship_extractor import RelationshipEdge, extract_relationships
from app.services.parsing.variable_extractor import extract_variables

logger = logging.getLogger(__name__)


@dataclass
class ImportReport:
    """Summary of an import operation.

    Attributes:
        nodes_created: Number of new LogicNodes created.
        nodes_updated: Number of existing LogicNodes updated.
        edges_created: Number of edges created.
        variables_created: Number of Variable nodes created.
        errors: List of error messages for files/nodes that failed.
        files_processed: Number of files processed.
    """

    nodes_created: int = 0
    nodes_updated: int = 0
    edges_created: int = 0
    variables_created: int = 0
    errors: list[str] = field(default_factory=list)
    files_processed: int = 0


def import_file(
    file_path: str,
    source: str | None = None,
    abs_path: str | None = None,
    external_name_to_id: dict[str, str] | None = None,
    skip_edges: bool = False,
    parse_cache: dict[str, tuple[str, ParseResult]] | None = None,
) -> ImportReport:
    """Import a single Python file into the graph as LogicNodes.

    Parses the file, creates LogicNodes for all functions/methods/classes,
    extracts relationships, variables, and data flow edges.

    Args:
        file_path: Relative path used to derive Python module-qualified node names
            (e.g. ``"app/services/utils.py"`` → module ``"app.services.utils"``).
            Should be relative to the project root so that import resolution matches.
        source: Optional source code. If None, reads from *abs_path* or *file_path*.
        abs_path: Absolute filesystem path used to read the file and stored as
            ``module_path`` on the node (for the frontend file opener). If None,
            falls back to resolving *file_path*.
        external_name_to_id: If provided, local name_to_id is merged into this dict
            after node creation (used for two-pass cross-file edge resolution).
        skip_edges: If True, skip edge creation (nodes only — for pass 1).
        parse_cache: If provided, cache (source, parse_result) keyed by file_path.

    Returns:
        ImportReport with counts and any errors.
    """
    report = ImportReport(files_processed=1)

    read_path = abs_path or file_path
    if source is None:
        try:
            source = Path(read_path).read_text(encoding="utf-8")
        except OSError as exc:
            report.errors.append(f"Cannot read {read_path}: {exc}")
            return report

    # module_path stored on the node: absolute path so the frontend can open the file
    module_path = abs_path if abs_path else _file_to_module_path(file_path)

    try:
        parse_result = parse_file(source, file_path)
    except Exception as exc:
        report.errors.append(f"Parse error in {file_path}: {exc}")
        return report

    graph = get_graph()
    now = datetime.now(timezone.utc).isoformat()

    # Track name->UUID mapping for edge creation
    name_to_id: dict[str, str] = {}

    # Create LogicNodes for each parsed node (skip Modules — they're not LogicNodes)
    for parsed_node in parse_result.nodes:
        if parsed_node.node_type == "Module":
            continue

        kind = _parsed_type_to_kind(parsed_node)
        node_id = generate_deterministic_node_id(parsed_node.name)
        ast_hash = compute_ast_hash(parsed_node.source_text)

        # Skip unchanged nodes (but force update if structural_hash is missing)
        existing_hash, existing_structural = _get_existing_hashes(node_id)
        if existing_hash == ast_hash and existing_structural:
            name_to_id[parsed_node.name] = node_id
            continue

        is_update = existing_hash is not None
        if is_update:
            report.nodes_updated += 1
        else:
            report.nodes_created += 1

        signature = extract_signature_text(parsed_node.source_text)
        return_type = extract_return_type(parsed_node.source_text)
        structural_hash = compute_structural_hash(parsed_node.source_text)
        params_raw = extract_params_detailed(parsed_node.source_text) if kind != LogicNodeKind.CLASS else []

        params_json = json.dumps(params_raw)
        decorators_json = json.dumps(parsed_node.decorators)

        graph.query(
            lq.MERGE_LOGIC_NODE,
            params={
                "id": node_id,
                "ast_hash": ast_hash,
                "structural_hash": structural_hash,
                "kind": kind.value,
                "name": parsed_node.name,
                "module_path": module_path,
                "signature": signature,
                "source_text": parsed_node.source_text,
                "semantic_intent": "",
                "docstring": parsed_node.docstring or "",
                "decorators": decorators_json,
                "params": params_json,
                "return_type": return_type or "",
                "tags": "[]",
                "class_id": "",
                "derived_from": "",
                "start_line": parsed_node.start_line,
                "end_line": parsed_node.end_line,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
        )

        # Clean up any old non-deterministic nodes for the same function
        _cleanup_old_node_ids(parsed_node.name, module_path, node_id)

        name_to_id[parsed_node.name] = node_id

    # Merge local names into the global mapping (for two-pass import)
    if external_name_to_id is not None:
        external_name_to_id.update(name_to_id)
    if parse_cache is not None:
        parse_cache[file_path] = (source, parse_result)
    if skip_edges:
        return report

    # Create MEMBER_OF edges for methods
    for parsed_node in parse_result.nodes:
        if parsed_node.node_type == "Function" and parsed_node.parent_name:
            parent_id = name_to_id.get(parsed_node.parent_name)
            child_id = name_to_id.get(parsed_node.name)
            if parent_id and child_id:
                # Check if parent is a class
                parent_node = next((n for n in parse_result.nodes if n.name == parsed_node.parent_name), None)
                if parent_node and parent_node.node_type == "Class":
                    try:
                        graph.query(
                            lq.EDGE_MERGE_QUERIES["MEMBER_OF"],
                            params={
                                "source_id": child_id,
                                "target_id": parent_id,
                                "properties": {"access": _infer_access(parsed_node.name)},
                            },
                        )
                        report.edges_created += 1
                    except Exception as exc:
                        report.errors.append(f"MEMBER_OF edge error: {exc}")

    # Extract and create relationship edges (CALLS, INHERITS, IMPORTS)
    try:
        rel_edges = extract_relationships(source, file_path, parse_result.nodes)
        for rel_edge in rel_edges:
            _create_relationship_edge(rel_edge, name_to_id, report)
    except Exception as exc:
        report.errors.append(f"Relationship extraction error in {file_path}: {exc}")

    # Extract variables for each function node
    try:
        func_nodes = [n for n in parse_result.nodes if n.node_type == "Function"]
        if func_nodes:
            var_result = extract_variables(source, file_path, parse_result.nodes)
            var_name_to_id: dict[str, str] = {}

            for var_node in var_result.nodes:
                var_id = generate_deterministic_node_id(f"{var_node.name}::{var_node.scope}")
                origin_node_id = name_to_id.get(var_node.origin_func, "")
                if not origin_node_id:
                    continue

                graph.query(
                    lq.MERGE_VARIABLE,
                    params={
                        "id": var_id,
                        "name": var_node.name,
                        "scope": var_node.scope,
                        "origin_node_id": origin_node_id,
                        "origin_line": var_node.origin_line,
                        "type_hint": var_node.type_hint or "",
                        "is_parameter": "." not in var_node.name.split(".")[-1],
                        "is_attribute": "self." in var_node.name,
                        "created_at": now,
                    },
                )
                var_name_to_id[var_node.name] = var_id
                report.variables_created += 1

            # Create variable edges (ASSIGNS, MUTATES, READS, RETURNS)
            for var_edge in var_result.edges:
                source_id = name_to_id.get(var_edge.source_name, "")
                target_id = var_name_to_id.get(var_edge.target_name, "")
                if source_id and target_id and var_edge.edge_type in lq.EDGE_MERGE_QUERIES:
                    try:
                        props = dict(var_edge.properties) if var_edge.properties else {}
                        graph.query(
                            lq.EDGE_MERGE_QUERIES[var_edge.edge_type],
                            params={
                                "source_id": source_id,
                                "target_id": target_id,
                                "properties": props,
                            },
                        )
                        report.edges_created += 1
                    except Exception:
                        pass
    except Exception as exc:
        report.errors.append(f"Variable extraction error in {file_path}: {exc}")

    return report


def import_directory(
    dir_path: str,
    patterns: list[str] | None = None,
    progress_callback: Any = None,
) -> ImportReport:
    """Recursively import all matching Python files from a directory.

    Args:
        dir_path: Path to the directory to import.
        patterns: Glob patterns to match (default: ["*.py"]).
        progress_callback: Optional callback(file_path, total, done) for progress tracking.

    Returns:
        Aggregated ImportReport.
    """
    if patterns is None:
        patterns = ["*.py"]

    report = ImportReport()
    dir_path_obj = Path(dir_path)

    if not dir_path_obj.is_dir():
        report.errors.append(f"Not a directory: {dir_path}")
        return report

    # Collect existing node module_paths before import for stale cleanup
    _pre_import_paths = _get_existing_module_paths()

    # Set watch_path so the file endpoint can serve files from this repo
    from app.config import settings  # pylint: disable=import-outside-toplevel
    settings.watch_path = str(dir_path_obj.resolve())

    # Collect all matching files
    files: list[Path] = []
    for pattern in patterns:
        files.extend(dir_path_obj.rglob(pattern))

    # Filter out common non-source dirs
    skip_dirs = {"__pycache__", ".git", ".venv", "node_modules", ".bumblebee", ".tox", ".mypy_cache"}
    files = [f for f in files if not any(skip in f.parts for skip in skip_dirs)]

    total = len(files)
    logger.info("Importing %d files from %s", total, dir_path)

    global_name_to_id: dict[str, str] = {}
    parse_cache: dict[str, tuple[str, ParseResult]] = {}

    # Pass 1: create all nodes, accumulate global name_to_id
    for idx, file_path in enumerate(sorted(files)):
        try:
            # Use the package root to derive module naming so import resolution matches
            # node names even in monorepos with non-package intermediate directories.
            # E.g. for "monorepo/pkg-dir/mypackage/utils.py" where pkg-dir/ has no
            # __init__.py, the package root is pkg-dir/ and rel_path is
            # "mypackage/utils.py" → module "mypackage.utils", matching Python imports.
            pkg_root = _find_package_root(file_path, dir_path_obj)
            rel_path = str(file_path.relative_to(pkg_root))
            file_report = import_file(
                rel_path,
                abs_path=str(file_path.resolve()),
                external_name_to_id=global_name_to_id,
                skip_edges=True,
                parse_cache=parse_cache,
            )
            report.nodes_created += file_report.nodes_created
            report.nodes_updated += file_report.nodes_updated
            report.errors.extend(file_report.errors)
            report.files_processed += 1
        except Exception as exc:
            report.errors.append(f"Failed to import {file_path}: {exc}")

        if progress_callback:
            try:
                progress_callback(str(file_path), total, idx + 1)
            except Exception:
                pass

    # Pass 2: create edges using global name_to_id (cross-file resolution)
    graph = get_graph()
    now = datetime.now(timezone.utc).isoformat()

    for file_path_str, (cached_source, parse_result) in parse_cache.items():
        # MEMBER_OF edges for methods
        for parsed_node in parse_result.nodes:
            if parsed_node.node_type == "Function" and parsed_node.parent_name:
                parent_id = global_name_to_id.get(parsed_node.parent_name)
                child_id = global_name_to_id.get(parsed_node.name)
                if parent_id and child_id:
                    parent_node = next(
                        (n for n in parse_result.nodes if n.name == parsed_node.parent_name), None
                    )
                    if parent_node and parent_node.node_type == "Class":
                        try:
                            graph.query(
                                lq.EDGE_MERGE_QUERIES["MEMBER_OF"],
                                params={
                                    "source_id": child_id,
                                    "target_id": parent_id,
                                    "properties": {"access": _infer_access(parsed_node.name)},
                                },
                            )
                            report.edges_created += 1
                        except Exception as exc:
                            report.errors.append(f"MEMBER_OF edge error: {exc}")

        # Relationship edges (CALLS, INHERITS, IMPORTS) — using global name_to_id
        try:
            rel_edges = extract_relationships(cached_source, file_path_str, parse_result.nodes)
            for rel_edge in rel_edges:
                _create_relationship_edge(rel_edge, global_name_to_id, report)
        except Exception as exc:
            report.errors.append(f"Relationship extraction error in {file_path_str}: {exc}")

        # Variable nodes and edges
        try:
            func_nodes = [n for n in parse_result.nodes if n.node_type == "Function"]
            if func_nodes:
                var_result = extract_variables(cached_source, file_path_str, parse_result.nodes)
                var_name_to_id: dict[str, str] = {}

                for var_node in var_result.nodes:
                    var_id = generate_deterministic_node_id(f"{var_node.name}::{var_node.scope}")
                    origin_node_id = global_name_to_id.get(var_node.origin_func, "")
                    if not origin_node_id:
                        continue

                    graph.query(
                        lq.MERGE_VARIABLE,
                        params={
                            "id": var_id,
                            "name": var_node.name,
                            "scope": var_node.scope,
                            "origin_node_id": origin_node_id,
                            "origin_line": var_node.origin_line,
                            "type_hint": var_node.type_hint or "",
                            "is_parameter": "." not in var_node.name.split(".")[-1],
                            "is_attribute": "self." in var_node.name,
                            "created_at": now,
                        },
                    )
                    var_name_to_id[var_node.name] = var_id
                    report.variables_created += 1

                for var_edge in var_result.edges:
                    source_id = global_name_to_id.get(var_edge.source_name, "")
                    target_id = var_name_to_id.get(var_edge.target_name, "")
                    if source_id and target_id and var_edge.edge_type in lq.EDGE_MERGE_QUERIES:
                        try:
                            props = dict(var_edge.properties) if var_edge.properties else {}
                            graph.query(
                                lq.EDGE_MERGE_QUERIES[var_edge.edge_type],
                                params={
                                    "source_id": source_id,
                                    "target_id": target_id,
                                    "properties": props,
                                },
                            )
                            report.edges_created += 1
                        except Exception:
                            pass
        except Exception as exc:
            report.errors.append(f"Variable extraction error in {file_path_str}: {exc}")

    # Clean up stale nodes: files that no longer exist on disk
    imported_abs_paths = {str(f.resolve()) for f in files}
    stale_paths = [p for p in _pre_import_paths if p not in imported_abs_paths]
    if stale_paths:
        _cleanup_stale_nodes(stale_paths)
        logger.info("Cleaned up stale nodes from %d removed files", len(stale_paths))

    logger.info(
        "Import complete: %d files, %d nodes created, %d updated, %d edges, %d variables, %d errors",
        report.files_processed,
        report.nodes_created,
        report.nodes_updated,
        report.edges_created,
        report.variables_created,
        len(report.errors),
    )

    return report


def import_incremental(file_path: str) -> ImportReport:
    """Incrementally re-import a file — only update changed functions.

    Compares AST hashes of existing LogicNodes against the current file state.
    Only re-imports functions whose hash has changed.

    Args:
        file_path: Path to the Python file.

    Returns:
        ImportReport with only the changed nodes.
    """
    # import_file already handles incremental logic via _find_existing_node
    # and hash comparison
    return import_file(file_path)


def _find_package_root(file_path: Path, search_root: Path) -> Path:
    """Walk up from file_path.parent to find the Python package root.

    Stops at the first ancestor directory that either does NOT contain an
    ``__init__.py`` (i.e. is not a Python package) or has reached ``search_root``.
    This ensures that intermediate non-package directories in a monorepo (e.g.
    ``bcx-knowledge/`` inside ``bcx-bo/``) are excluded from the module path,
    so ``bcx-knowledge/bcx_knowledge/nodes.py`` resolves to ``bcx_knowledge.nodes``
    rather than ``bcx-knowledge.bcx_knowledge.nodes``.

    Args:
        file_path: Absolute path to the Python source file.
        search_root: The watch/import directory — never walk above this.

    Returns:
        Path to the package root directory.
    """
    current = file_path.parent
    while current != search_root and (current / "__init__.py").exists():
        current = current.parent
    return current


def _get_existing_module_paths() -> list[str]:
    """Get all distinct module_path values from existing LogicNodes."""
    graph = get_graph()
    try:
        result = graph.query("MATCH (n:LogicNode) RETURN DISTINCT n.module_path")
        return [str(row[0]) for row in result.result_set]
    except Exception:
        return []


def _cleanup_stale_nodes(stale_paths: list[str]) -> None:
    """Delete LogicNodes and their Variables for files no longer on disk."""
    graph = get_graph()
    # Delete variables whose origin nodes are in stale files
    graph.query(
        "MATCH (v:Variable)-[:ASSIGNS|MUTATES|READS|RETURNS]-(n:LogicNode) "
        "WHERE n.module_path IN $paths DETACH DELETE v",
        params={"paths": stale_paths},
    )
    # Delete the stale LogicNodes
    graph.query(
        "MATCH (n:LogicNode) WHERE n.module_path IN $paths DETACH DELETE n",
        params={"paths": stale_paths},
    )


def _cleanup_old_node_ids(name: str, module_path: str, keep_id: str) -> None:
    """Delete any LogicNodes with the same name/module_path but a different ID.

    Cleans up legacy random-UUID nodes after migration to deterministic IDs.
    """
    graph = get_graph()
    try:
        graph.query(
            "MATCH (n:LogicNode {name: $name, module_path: $module_path}) "
            "WHERE n.id <> $keep_id DETACH DELETE n",
            params={"name": name, "module_path": module_path, "keep_id": keep_id},
        )
    except Exception:
        pass


def _file_to_module_path(file_path: str) -> str:
    """Return the absolute file path for use as the module_path identifier.

    This preserves the real file path so the frontend editor can open the file.

    Args:
        file_path: File path (absolute or relative).

    Returns:
        Absolute file path string.
    """
    return str(Path(file_path).resolve())


def _parsed_type_to_kind(node: ParsedNode) -> LogicNodeKind:
    """Map a ParsedNode type to a LogicNodeKind.

    Args:
        node: The parsed node.

    Returns:
        Appropriate LogicNodeKind.
    """
    if node.node_type == "Class":
        return LogicNodeKind.CLASS
    if node.node_type == "Function":
        # Methods are functions with a class parent
        if node.parent_name:
            # Check if parent is a class by looking at the parent name pattern
            return LogicNodeKind.METHOD
        return LogicNodeKind.FUNCTION
    return LogicNodeKind.FUNCTION


def _find_existing_node(name: str, module_path: str) -> str | None:
    """Find an existing LogicNode by name and module_path.

    Args:
        name: Qualified node name.
        module_path: Module path.

    Returns:
        UUID of existing node, or None.
    """
    graph = get_graph()
    try:
        result = graph.query(
            "MATCH (n:LogicNode {name: $name, module_path: $module_path, status: 'active'}) RETURN n.id",
            params={"name": name, "module_path": module_path},
        )
        if result.result_set:
            return str(result.result_set[0][0])
    except Exception:
        pass
    return None


def _get_existing_hash(node_id: str) -> str | None:
    """Get the AST hash of an existing node.

    Args:
        node_id: UUID of the node.

    Returns:
        AST hash string, or None.
    """
    return _get_existing_hashes(node_id)[0]


def _get_existing_hashes(node_id: str) -> tuple[str | None, str | None]:
    """Get the AST hash and structural hash of an existing node.

    Args:
        node_id: UUID of the node.

    Returns:
        Tuple of (ast_hash, structural_hash), either may be None.
    """
    graph = get_graph()
    try:
        result = graph.query(
            "MATCH (n:LogicNode {id: $id}) RETURN n.ast_hash, n.structural_hash",
            params={"id": node_id},
        )
        if result.result_set:
            row = result.result_set[0]
            ast_h = str(row[0]) if row[0] is not None else None
            struct_h = str(row[1]) if row[1] is not None else None
            return (ast_h, struct_h)
    except Exception:
        pass
    return (None, None)


def _infer_access(name: str) -> str:
    """Infer method access level from naming convention.

    Args:
        name: Qualified method name.

    Returns:
        "private", "protected", or "public".
    """
    short_name = name.rsplit(".", 1)[-1]
    if short_name.startswith("__") and not short_name.endswith("__"):
        return "private"
    if short_name.startswith("_"):
        return "protected"
    return "public"


def _create_relationship_edge(
    rel_edge: RelationshipEdge,
    name_to_id: dict[str, str],
    report: ImportReport,
) -> None:
    """Create a relationship edge in the graph using UUID-based IDs.

    Args:
        rel_edge: The relationship edge from the extractor.
        name_to_id: Mapping of qualified names to UUIDs.
        report: Import report to update.
    """
    source_id = name_to_id.get(rel_edge.source_name, "")
    target_id = name_to_id.get(rel_edge.target_name, "")

    if not source_id or not target_id:
        return

    edge_type = rel_edge.edge_type
    if edge_type not in lq.EDGE_MERGE_QUERIES:
        return

    graph = get_graph()
    props = dict(rel_edge.properties) if rel_edge.properties else {}

    try:
        graph.query(
            lq.EDGE_MERGE_QUERIES[edge_type],
            params={
                "source_id": source_id,
                "target_id": target_id,
                "properties": props,
            },
        )
        report.edges_created += 1
    except Exception as exc:
        report.errors.append(f"Edge creation error ({edge_type} {rel_edge.source_name} -> {rel_edge.target_name}): {exc}")
