"""Ghost preview service: apply diff in memory, compare shadow graph vs current (TICKET-602)."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.config import settings
from app.graph.client import get_graph
from app.graph.indexer import index_file
from app.services.parsing.ast_parser import ParseResult, parse_file
from app.services.parsing.relationship_extractor import extract_relationships
from app.services.parsing.statement_extractor import extract_statements
from app.services.parsing.variable_extractor import extract_variables
from app.services.parsing.dataflow_extractor import extract_dataflow

logger = logging.getLogger(__name__)


def compute_ghost_preview(path: str, old_text: str, new_text: str) -> dict[str, list[dict[str, Any]]]:
    """Compute the graph diff that would result from an edit.

    Applies the diff in memory, runs the full parser pipeline on the
    modified source, and compares the resulting nodes/edges against
    the current graph state.

    Args:
        path: Relative file path within the repository.
        old_text: Text to find and replace.
        new_text: Replacement text.

    Returns:
        Dict with added_nodes, removed_nodes, added_edges, removed_edges.
    """
    if not settings.watch_path:
        return {"added_nodes": [], "removed_nodes": [], "added_edges": [], "removed_edges": []}

    abs_path = os.path.join(os.path.abspath(settings.watch_path), path)
    if not os.path.isfile(abs_path):
        return {"added_nodes": [], "removed_nodes": [], "added_edges": [], "removed_edges": []}

    with open(abs_path, encoding="utf-8") as f:
        original_source = f.read()

    # Apply the edit in memory
    if old_text not in original_source:
        return {"added_nodes": [], "removed_nodes": [], "added_edges": [], "removed_edges": []}

    modified_source = original_source.replace(old_text, new_text, 1)

    # Parse the original (current state)
    current_result = parse_file(original_source, path)
    current_nodes = {n.name for n in current_result.nodes}
    current_edges = {(e.source_name, e.target_name, e.edge_type) for e in current_result.edges}

    # Parse the modified (shadow state)
    shadow_result = parse_file(modified_source, path)
    shadow_nodes = {n.name for n in shadow_result.nodes}
    shadow_edges = {(e.source_name, e.target_name, e.edge_type) for e in shadow_result.edges}

    # Extract relationships for both
    current_rels = extract_relationships(original_source, path, current_result.nodes)
    shadow_rels = extract_relationships(modified_source, path, shadow_result.nodes)

    for rel in current_rels:
        current_edges.add((rel.source_name, rel.target_name, rel.edge_type))
    for rel in shadow_rels:
        shadow_edges.add((rel.source_name, rel.target_name, rel.edge_type))

    # Extract statements
    current_stmts = extract_statements(original_source, path, current_result.nodes)
    shadow_stmts = extract_statements(modified_source, path, shadow_result.nodes)

    for n in current_stmts.nodes:
        current_nodes.add(n.name)
    for n in shadow_stmts.nodes:
        shadow_nodes.add(n.name)

    for e in current_stmts.edges:
        current_edges.add((e.source_name, e.target_name, e.edge_type))
    for e in shadow_stmts.edges:
        shadow_edges.add((e.source_name, e.target_name, e.edge_type))

    # Compute diffs
    added_nodes = [{"name": n, "action": "add"} for n in shadow_nodes - current_nodes]
    removed_nodes = [{"name": n, "action": "remove"} for n in current_nodes - shadow_nodes]
    added_edges = [{"source": e[0], "target": e[1], "type": e[2], "action": "add"} for e in shadow_edges - current_edges]
    removed_edges = [{"source": e[0], "target": e[1], "type": e[2], "action": "remove"} for e in current_edges - shadow_edges]

    return {
        "added_nodes": added_nodes,
        "removed_nodes": removed_nodes,
        "added_edges": added_edges,
        "removed_edges": removed_edges,
    }


def apply_edit(path: str, old_text: str, new_text: str) -> dict[str, str]:
    """Apply an edit: write to disk and re-index the file.

    Args:
        path: Relative file path within the repository.
        old_text: Text to find and replace.
        new_text: Replacement text.

    Returns:
        Dict with status info.
    """
    if not settings.watch_path:
        return {"status": "error", "detail": "No repository indexed"}

    abs_path = os.path.join(os.path.abspath(settings.watch_path), path)

    # Prevent directory traversal
    repo_root = os.path.abspath(settings.watch_path)
    if not os.path.abspath(abs_path).startswith(repo_root):
        return {"status": "error", "detail": "Path traversal not allowed"}

    if not os.path.isfile(abs_path):
        return {"status": "error", "detail": f"File not found: {path}"}

    with open(abs_path, encoding="utf-8") as f:
        content = f.read()

    if old_text not in content:
        return {"status": "error", "detail": "old_text not found in file"}

    # Apply the edit
    new_content = content.replace(old_text, new_text, 1)

    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    # Re-index the file
    try:
        index_file(abs_path, repo_root=settings.watch_path)
    except Exception:
        logger.exception("Failed to re-index after edit: %s", path)

    # Broadcast event
    try:
        import asyncio
        from app.routers.websocket import broadcast

        module_name = path.replace("/", ".").replace("\\", ".").removesuffix(".py")
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(broadcast("graph:updated", {"affected_modules": [module_name]}))
    except Exception:
        logger.debug("Could not broadcast graph:updated event")

    return {"status": "ok", "path": path}
