"""Indexer service: reads files, parses AST, upserts to FalkorDB."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.graph import queries
from app.graph.batch_upsert import BatchUpserter
from app.graph.client import get_graph
from app.models.exceptions import IndexingError
from app.services.ast_parser import ParsedNode, ParseResult, _get_parser, compute_checksum, parse_file
from app.services.dataflow_extractor import DataFlowEdge, extract_dataflow
from app.services.relationship_extractor import RelationshipEdge, extract_relationships
from app.services.statement_extractor import StatementEdge, StatementNode, extract_statements
from app.services.variable_extractor import VariableEdge, VariableNode, VariableResult, extract_variables

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Individual upsert helpers (kept for backward compatibility / file watcher)
# ---------------------------------------------------------------------------


def _upsert_node(graph, node: ParsedNode, checksum: str = "") -> None:  # type: ignore[no-untyped-def]
    """Upsert a single node to the graph.

    Args:
        graph: FalkorDB graph instance.
        node: Parsed AST node to upsert.
        checksum: File checksum (used for Module nodes).
    """
    if node.node_type == "Module":
        graph.query(
            queries.MERGE_MODULE,
            params={
                "name": node.name,
                "start_line": node.start_line,
                "end_line": node.end_line,
                "module_path": node.module_path,
                "checksum": checksum,
            },
        )
    elif node.node_type == "Class":
        graph.query(
            queries.MERGE_CLASS,
            params={
                "name": node.name,
                "start_line": node.start_line,
                "end_line": node.end_line,
                "start_col": node.start_col,
                "end_col": node.end_col,
                "source_text": node.source_text,
                "module_path": node.module_path,
                "decorators": node.decorators,
                "docstring": node.docstring or "",
            },
        )
    elif node.node_type == "Function":
        graph.query(
            queries.MERGE_FUNCTION,
            params={
                "name": node.name,
                "start_line": node.start_line,
                "end_line": node.end_line,
                "start_col": node.start_col,
                "end_col": node.end_col,
                "source_text": node.source_text,
                "module_path": node.module_path,
                "params": node.params,
                "decorators": node.decorators,
                "docstring": node.docstring or "",
                "is_async": node.is_async,
            },
        )


def _upsert_edge(graph, edge) -> None:  # type: ignore[no-untyped-def]
    """Upsert a single edge to the graph.

    Args:
        graph: FalkorDB graph instance.
        edge: Parsed AST edge to upsert.
    """
    if edge.edge_type == "DEFINES":
        graph.query(
            queries.MERGE_DEFINES,
            params={
                "source_name": edge.source_name,
                "target_name": edge.target_name,
            },
        )


def _upsert_relationship_edge(graph, edge: RelationshipEdge) -> None:  # type: ignore[no-untyped-def]
    """Upsert a relationship edge (CALLS, INHERITS, IMPORTS) to the graph.

    Args:
        graph: FalkorDB graph instance.
        edge: Relationship edge to upsert.
    """
    if edge.edge_type == "CALLS":
        graph.query(
            queries.MERGE_CALLS,
            params={
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "call_line": edge.properties.get("call_line", 0),
                "seq": edge.properties.get("seq", 0),
                "call_order": edge.properties.get("call_order", 0),
            },
        )
    elif edge.edge_type == "INHERITS":
        graph.query(
            queries.MERGE_INHERITS,
            params={
                "source_name": edge.source_name,
                "target_name": edge.target_name,
            },
        )
    elif edge.edge_type == "IMPORTS":
        graph.query(
            queries.MERGE_IMPORTS,
            params={
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "alias": edge.properties.get("alias") or "",
            },
        )


def _upsert_statement_node(graph, node: StatementNode) -> None:  # type: ignore[no-untyped-def]
    """Upsert a Statement, ControlFlow, or Branch node to the graph.

    Args:
        graph: FalkorDB graph instance.
        node: Statement-level node to upsert.
    """
    if node.node_type == "Statement":
        query = queries.MERGE_STATEMENT
    elif node.node_type == "ControlFlow":
        query = queries.MERGE_CONTROL_FLOW
    elif node.node_type == "Branch":
        query = queries.MERGE_BRANCH
    else:
        return

    graph.query(
        query,
        params={
            "name": node.name,
            "kind": node.kind,
            "source_text": node.source_text,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "start_col": node.start_col,
            "end_col": node.end_col,
            "seq": node.seq,
            "module_path": node.module_path,
            "condition_text": node.condition_text or "",
        },
    )


def _upsert_statement_edge(graph, edge: StatementEdge) -> None:  # type: ignore[no-untyped-def]
    """Upsert a CONTAINS or NEXT edge to the graph.

    Args:
        graph: FalkorDB graph instance.
        edge: Statement-level edge to upsert.
    """
    if edge.edge_type == "CONTAINS":
        query = queries.MERGE_CONTAINS
    elif edge.edge_type == "NEXT":
        query = queries.MERGE_NEXT
    else:
        return

    graph.query(
        query,
        params={
            "source_name": edge.source_name,
            "target_name": edge.target_name,
        },
    )


def _upsert_variable_node(graph, node: VariableNode) -> None:  # type: ignore[no-untyped-def]
    """Upsert a Variable node to the graph.

    Args:
        graph: FalkorDB graph instance.
        node: Variable node to upsert.
    """
    graph.query(
        queries.MERGE_VARIABLE,
        params={
            "name": node.name,
            "scope": node.scope,
            "origin_line": node.origin_line,
            "origin_func": node.origin_func,
            "type_hint": node.type_hint or "",
            "module_path": node.module_path,
        },
    )


def _upsert_variable_edge(graph, edge: VariableEdge) -> None:  # type: ignore[no-untyped-def]
    """Upsert a variable interaction edge (ASSIGNS, MUTATES, READS, RETURNS).

    Args:
        graph: FalkorDB graph instance.
        edge: Variable interaction edge to upsert.
    """
    props = edge.properties
    if edge.edge_type == "ASSIGNS":
        graph.query(
            queries.MERGE_ASSIGNS,
            params={
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "line": props.get("line", 0),
                "col": props.get("col", 0),
                "seq": props.get("seq", 0),
                "is_rebind": props.get("is_rebind", False),
                "control_context": props.get("control_context") or "",
                "branch": props.get("branch") or "",
            },
        )
    elif edge.edge_type == "MUTATES":
        graph.query(
            queries.MERGE_MUTATES,
            params={
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "line": props.get("line", 0),
                "seq": props.get("seq", 0),
                "mutation_kind": props.get("mutation_kind", ""),
                "control_context": props.get("control_context") or "",
                "branch": props.get("branch") or "",
            },
        )
    elif edge.edge_type == "READS":
        graph.query(
            queries.MERGE_READS,
            params={
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "line": props.get("line", 0),
                "seq": props.get("seq", 0),
                "control_context": props.get("control_context") or "",
                "branch": props.get("branch") or "",
            },
        )
    elif edge.edge_type == "RETURNS":
        graph.query(
            queries.MERGE_RETURNS,
            params={
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "line": props.get("line", 0),
                "seq": props.get("seq", 0),
                "control_context": props.get("control_context") or "",
                "branch": props.get("branch") or "",
            },
        )


def _upsert_dataflow_edge(graph, edge: DataFlowEdge) -> None:  # type: ignore[no-untyped-def]
    """Upsert a PASSES_TO or FEEDS edge to the graph.

    Args:
        graph: FalkorDB graph instance.
        edge: Data flow edge to upsert.
    """
    props = edge.properties
    if edge.edge_type == "PASSES_TO":
        graph.query(
            queries.MERGE_PASSES_TO,
            params={
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "call_line": props.get("call_line", 0),
                "seq": props.get("seq", 0),
                "arg_position": props.get("arg_position", 0),
                "arg_keyword": props.get("arg_keyword") or "",
            },
        )
    elif edge.edge_type == "FEEDS":
        graph.query(
            queries.MERGE_FEEDS,
            params={
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "line": props.get("line", 0),
                "seq": props.get("seq", 0),
                "expression_text": props.get("expression_text") or "",
                "via": props.get("via") or "",
            },
        )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _delete_module_nodes(graph, module_path: str) -> None:  # type: ignore[no-untyped-def]
    """Delete all nodes belonging to a module (for re-indexing).

    Args:
        graph: FalkorDB graph instance.
        module_path: Relative module path to delete nodes for.
    """
    graph.query(queries.DELETE_MODULE_NODES, params={"module_path": module_path})


def _get_module_checksum(graph, module_path: str) -> str | None:  # type: ignore[no-untyped-def]
    """Get the stored checksum for a module, or None if not indexed.

    Args:
        graph: FalkorDB graph instance.
        module_path: Relative module path to look up.

    Returns:
        The stored checksum string, or None if the module is not yet indexed.
    """
    result = graph.query(queries.GET_MODULE_CHECKSUM, params={"module_path": module_path})
    if result.result_set:
        return result.result_set[0][0]  # type: ignore[no-any-return]
    return None


# ---------------------------------------------------------------------------
# Batched file indexing
# ---------------------------------------------------------------------------


def index_file(file_path: str, repo_root: str = "") -> ParseResult:
    """Index a single Python file into the graph using batched upserts.

    Reads the file, parses its AST once, and upserts all nodes/edges to FalkorDB
    in ~16 batched UNWIND queries instead of hundreds of individual queries.
    Skips re-indexing if the file checksum has not changed.

    Args:
        file_path: Absolute or relative path to the Python file.
        repo_root: Root of the repository (for computing relative module paths).

    Returns:
        The ParseResult from parsing the file.

    Raises:
        IndexingError: If the file cannot be read or parsed.
    """
    graph = get_graph()

    try:
        abs_path = os.path.abspath(file_path)
        with open(abs_path, encoding="utf-8") as f:
            source = f.read()
    except OSError as exc:
        raise IndexingError(f"Cannot read file: {file_path}") from exc

    # Compute relative path for module_path
    if repo_root:
        rel_path = os.path.relpath(abs_path, os.path.abspath(repo_root))
    else:
        rel_path = file_path

    # Check if file has changed
    new_checksum = compute_checksum(source)
    stored_checksum = _get_module_checksum(graph, rel_path)

    if stored_checksum == new_checksum:
        logger.info("Skipping unchanged file: %s", rel_path)
        return parse_file(source, rel_path)

    # Delete old nodes and re-index
    if stored_checksum is not None:
        logger.info("Re-indexing changed file: %s", rel_path)
        _delete_module_nodes(graph, rel_path)
    else:
        logger.info("Indexing new file: %s", rel_path)

    # Parse once, reuse tree for all extractors
    parser = _get_parser()
    tree = parser.parse(source.encode("utf-8"))

    result = parse_file(source, rel_path, tree=tree)

    # Use BatchUpserter for all graph writes
    batch = BatchUpserter(graph)

    # Add all structural nodes
    for node in result.nodes:
        batch.add_node(node, checksum=result.checksum)

    # Add all structural edges (DEFINES)
    for edge in result.edges:
        batch.add_edge(edge)

    # Extract relationships (CALLS, INHERITS, IMPORTS)
    rel_edges = extract_relationships(source, rel_path, result.nodes, tree=tree)
    for rel_edge in rel_edges:
        batch.add_relationship_edge(rel_edge)

    # Extract statement-level nodes and edges
    stmt_result = extract_statements(source, rel_path, result.nodes, tree=tree)
    for stmt_node in stmt_result.nodes:
        batch.add_statement_node(stmt_node)
    for stmt_edge in stmt_result.edges:
        batch.add_statement_edge(stmt_edge)

    # Extract variable nodes and edges
    var_result = extract_variables(source, rel_path, result.nodes, stmt_result.nodes, tree=tree)
    for var_node in var_result.nodes:
        batch.add_variable_node(var_node)
    for var_edge in var_result.edges:
        batch.add_variable_edge(var_edge)

    # Extract data flow edges (PASSES_TO, FEEDS)
    df_result = extract_dataflow(
        source, rel_path, result.nodes, rel_edges, var_result.nodes, var_result.edges, tree=tree
    )
    for df_edge in df_result.edges:
        batch.add_dataflow_edge(df_edge)

    # Flush all batched queries at once
    batch.flush()

    return result


# ---------------------------------------------------------------------------
# Repository indexing (sync + async)
# ---------------------------------------------------------------------------


def _collect_python_files(repo_path: str) -> list[str]:
    """Collect all Python file paths in a repository.

    Args:
        repo_path: Absolute path to the repository root.

    Returns:
        Sorted list of absolute file paths.
    """
    skip_dirs = {"__pycache__", "node_modules", ".venv", "venv"}
    files: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(repo_path):
        rel_dir = os.path.relpath(dirpath, repo_path)
        if any(part.startswith(".") or part in skip_dirs for part in Path(rel_dir).parts):
            continue
        for filename in filenames:
            if filename.endswith(".py"):
                files.append(os.path.join(dirpath, filename))
    return sorted(files)


def index_repository(repo_path: str) -> dict[str, int]:
    """Index all Python files in a repository.

    Walks the directory tree, skipping hidden directories and common non-source
    directories, and indexes each .py file into the graph.

    Args:
        repo_path: Path to the repository root.

    Returns:
        Statistics dict with keys: files_indexed, files_skipped, nodes_created, edges_created.

    Raises:
        IndexingError: If the repository path does not exist.
    """
    repo_path = os.path.abspath(repo_path)
    if not os.path.isdir(repo_path):
        raise IndexingError(f"Repository path does not exist: {repo_path}")

    stats: dict[str, int] = {"files_indexed": 0, "files_skipped": 0, "nodes_created": 0, "edges_created": 0}
    files = _collect_python_files(repo_path)

    for abs_file in files:
        try:
            result = index_file(abs_file, repo_root=repo_path)
            stats["files_indexed"] += 1
            stats["nodes_created"] += len(result.nodes)
            stats["edges_created"] += len(result.edges)
        except IndexingError:
            logger.exception("Failed to index: %s", abs_file)
            stats["files_skipped"] += 1

    logger.info("Indexing complete: %s", stats)
    return stats


async def index_repository_async(
    repo_path: str,
    progress_callback: Callable[[str, int, int], Awaitable[None]] | None = None,
) -> dict[str, int]:
    """Index all Python files in a repository asynchronously with progress reporting.

    Runs file indexing in a thread pool to avoid blocking the event loop,
    and invokes the progress callback after each file.

    Args:
        repo_path: Path to the repository root.
        progress_callback: Optional async callback(file_path, done, total) for progress.

    Returns:
        Statistics dict with keys: files_indexed, files_skipped, nodes_created, edges_created.

    Raises:
        IndexingError: If the repository path does not exist.
    """
    repo_path = os.path.abspath(repo_path)
    if not os.path.isdir(repo_path):
        raise IndexingError(f"Repository path does not exist: {repo_path}")

    stats: dict[str, int] = {"files_indexed": 0, "files_skipped": 0, "nodes_created": 0, "edges_created": 0}
    files = _collect_python_files(repo_path)
    total = len(files)

    for i, abs_file in enumerate(files, 1):
        try:
            result = await asyncio.to_thread(index_file, abs_file, repo_path)
            stats["files_indexed"] += 1
            stats["nodes_created"] += len(result.nodes)
            stats["edges_created"] += len(result.edges)
        except IndexingError:
            logger.exception("Failed to index: %s", abs_file)
            stats["files_skipped"] += 1

        if progress_callback is not None:
            rel_file = os.path.relpath(abs_file, repo_path)
            await progress_callback(rel_file, i, total)

    logger.info("Async indexing complete: %s", stats)
    return stats
