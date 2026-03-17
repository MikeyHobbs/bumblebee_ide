"""Write-back service: update graph → codegen → validate → write to disk (TICKET-403)."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.graph.client import get_graph
from app.graph import queries
from app.models.exceptions import BumblebeeError, GraphQueryError, NodeNotFoundError
from app.services.parsing.ast_parser import _get_parser

logger = logging.getLogger(__name__)


def append_function_to_file(source_text: str, module_path: str, repo_root: str) -> None:
    """Append a new function's source text to the end of a module file.

    Creates the file (and intermediate directories) if it does not exist.
    Two blank lines are inserted before the appended function to follow PEP 8.

    Args:
        source_text: The complete source text of the function to append.
        module_path: Relative module file path (e.g. ``pkg/utils.py``).
        repo_root: Absolute path to the repository root.
    """
    abs_path = os.path.join(os.path.abspath(repo_root), module_path) if repo_root else os.path.abspath(module_path)

    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    if os.path.isfile(abs_path):
        with open(abs_path, encoding="utf-8") as f:
            existing = f.read()
        separator = "\n\n\n" if existing and not existing.endswith("\n\n") else "\n\n" if existing else ""
    else:
        existing = ""
        separator = ""

    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(existing + separator + source_text + "\n")

    logger.info("Appended function to %s", abs_path)


def replace_function_in_file(new_source: str, file_path: str, start_line: int, end_line: int) -> None:
    """Replace lines ``start_line`` through ``end_line`` (1-based, inclusive) in a file.

    Args:
        new_source: Replacement source text.
        file_path: Absolute path to the target file.
        start_line: First line to replace (1-based).
        end_line: Last line to replace (1-based, inclusive).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If start_line or end_line are out of range.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Cannot replace function: file not found: {file_path}")

    with open(file_path, encoding="utf-8") as f:
        lines = f.readlines()

    if start_line < 1 or end_line > len(lines) or start_line > end_line:
        raise ValueError(
            f"Invalid line range {start_line}..{end_line} for file with {len(lines)} lines"
        )

    new_lines = [line + "\n" for line in new_source.split("\n") if line != ""] if new_source else []
    # Ensure the last replacement line ends with a newline
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    lines[start_line - 1:end_line] = new_lines

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    logger.info("Replaced lines %d-%d in %s", start_line, end_line, file_path)


class WriteBackError(BumblebeeError):
    """Raised when a write-back operation fails."""


def update_statement(statement_id: str, new_source_text: str) -> dict[str, str]:
    """Update a statement's source text in the graph and regenerate the file.

    Args:
        statement_id: Qualified name of the statement node.
        new_source_text: New source text for the statement.

    Returns:
        Dict with updated statement info.

    Raises:
        NodeNotFoundError: If the statement does not exist.
        WriteBackError: If validation or write-back fails.
    """
    graph = get_graph()

    # Verify statement exists
    result = graph.query(
        "MATCH (s) WHERE s.name = $name AND (s:Statement OR s:ControlFlow OR s:Branch) RETURN s",
        params={"name": statement_id},
    )
    if not result.result_set:
        raise NodeNotFoundError(statement_id)

    node = result.result_set[0][0]
    old_source = node.properties.get("source_text", "") if hasattr(node, "properties") else ""
    module_path = node.properties.get("module_path", "") if hasattr(node, "properties") else ""

    # Update the node's source_text
    graph.query(
        "MATCH (s {name: $name}) SET s.source_text = $source_text RETURN s",
        params={"name": statement_id, "source_text": new_source_text},
    )

    # Regenerate the function source and validate
    function_name = _get_containing_function(statement_id)
    if function_name:
        new_func_source = _regenerate_function_source(function_name)
        _validate_python(new_func_source)

        # Write back to disk if module_path is set
        if module_path:
            _write_function_to_file(function_name, new_func_source, module_path)

    return {
        "statement_id": statement_id,
        "old_source": old_source,
        "new_source": new_source_text,
        "module_path": module_path,
    }


def insert_statement(
    function_id: str,
    after_statement_id: str | None,
    source_text: str,
    kind: str = "expression",
) -> dict[str, str]:
    """Insert a new statement into a function.

    Args:
        function_id: Qualified name of the containing function.
        after_statement_id: Insert after this statement (None = prepend).
        source_text: Source text for the new statement.
        kind: Statement kind (expression, assignment, return, etc.).

    Returns:
        Dict with new statement info.
    """
    graph = get_graph()

    # Determine the seq for the new statement
    if after_statement_id:
        result = graph.query(
            "MATCH (s {name: $name}) RETURN s.seq",
            params={"name": after_statement_id},
        )
        if not result.result_set:
            raise NodeNotFoundError(after_statement_id)
        after_seq = int(result.result_set[0][0] or 0)
        new_seq = after_seq + 1
    else:
        new_seq = 0

    # Shift existing statements with seq >= new_seq
    graph.query(
        "MATCH (f:Function {name: $func_name})-[:CONTAINS]->(s) "
        "WHERE s.seq >= $new_seq "
        "SET s.seq = s.seq + 1",
        params={"func_name": function_id, "new_seq": new_seq},
    )

    # Get module_path from function
    func_result = graph.query(
        "MATCH (f:Function {name: $name}) RETURN f.module_path",
        params={"name": function_id},
    )
    module_path = func_result.result_set[0][0] if func_result.result_set else ""

    # Create the new statement node
    stmt_name = f"{function_id}.stmt_{new_seq}"
    graph.query(
        queries.MERGE_STATEMENT,
        params={
            "name": stmt_name,
            "kind": kind,
            "source_text": source_text,
            "start_line": 0,
            "end_line": 0,
            "start_col": 0,
            "end_col": 0,
            "seq": new_seq,
            "module_path": module_path,
        },
    )

    # Add CONTAINS edge
    graph.query(
        queries.MERGE_CONTAINS,
        params={"source_name": function_id, "target_name": stmt_name},
    )

    # Update NEXT edges
    if after_statement_id:
        # Remove old NEXT from after_statement
        graph.query(
            "MATCH (a {name: $after})-[r:NEXT]->(b) DELETE r",
            params={"after": after_statement_id},
        )
        # NEXT: after → new
        graph.query(
            queries.MERGE_NEXT,
            params={"source_name": after_statement_id, "target_name": stmt_name},
        )

    # Find the next statement and add NEXT edge
    next_result = graph.query(
        "MATCH (f:Function {name: $func_name})-[:CONTAINS]->(s) "
        "WHERE s.seq = $next_seq AND s.name <> $new_name "
        "RETURN s.name",
        params={"func_name": function_id, "next_seq": new_seq + 1, "new_name": stmt_name},
    )
    if next_result.result_set:
        next_name = next_result.result_set[0][0]
        graph.query(
            queries.MERGE_NEXT,
            params={"source_name": stmt_name, "target_name": next_name},
        )

    # Regenerate and write back
    new_func_source = _regenerate_function_source(function_id)
    _validate_python(new_func_source)
    if module_path:
        _write_function_to_file(function_id, new_func_source, module_path)

    return {
        "statement_id": stmt_name,
        "function_id": function_id,
        "source_text": source_text,
        "seq": str(new_seq),
    }


def delete_statement(statement_id: str) -> dict[str, str]:
    """Delete a statement from the graph and regenerate the file.

    Args:
        statement_id: Qualified name of the statement to delete.

    Returns:
        Dict with deletion info.
    """
    graph = get_graph()

    # Get statement info
    result = graph.query(
        "MATCH (s {name: $name}) RETURN s.module_path, s.seq",
        params={"name": statement_id},
    )
    if not result.result_set:
        raise NodeNotFoundError(statement_id)

    module_path = result.result_set[0][0] or ""
    deleted_seq = int(result.result_set[0][1] or 0)
    function_name = _get_containing_function(statement_id)

    # Fix NEXT chain: bridge over deleted node
    prev_result = graph.query(
        "MATCH (prev)-[:NEXT]->(s {name: $name}) RETURN prev.name",
        params={"name": statement_id},
    )
    next_result = graph.query(
        "MATCH (s {name: $name})-[:NEXT]->(next) RETURN next.name",
        params={"name": statement_id},
    )

    prev_name = prev_result.result_set[0][0] if prev_result.result_set else None
    next_name = next_result.result_set[0][0] if next_result.result_set else None

    # Delete the node
    graph.query(
        "MATCH (s {name: $name}) DETACH DELETE s",
        params={"name": statement_id},
    )

    # Bridge NEXT edge
    if prev_name and next_name:
        graph.query(
            queries.MERGE_NEXT,
            params={"source_name": prev_name, "target_name": next_name},
        )

    # Regenerate and write back
    if function_name:
        new_func_source = _regenerate_function_source(function_name)
        _validate_python(new_func_source)
        if module_path:
            _write_function_to_file(function_name, new_func_source, module_path)

    return {
        "statement_id": statement_id,
        "function_id": function_name or "",
        "module_path": module_path,
    }


def reorder_statements(function_id: str, statement_ids: list[str]) -> dict[str, Any]:
    """Reorder statements within a function.

    Args:
        function_id: Qualified name of the function.
        statement_ids: Statement names in new order.

    Returns:
        Dict with reorder results.
    """
    graph = get_graph()

    # Update seq values
    for i, stmt_id in enumerate(statement_ids):
        graph.query(
            "MATCH (s {name: $name}) SET s.seq = $seq",
            params={"name": stmt_id, "seq": i},
        )

    # Rebuild NEXT chain
    # First remove all NEXT edges from this function's statements
    graph.query(
        "MATCH (a)-[r:NEXT]->(b) "
        "WHERE a.name STARTS WITH $prefix "
        "DELETE r",
        params={"prefix": function_id + "."},
    )

    # Rebuild NEXT edges in new order
    for i in range(len(statement_ids) - 1):
        graph.query(
            queries.MERGE_NEXT,
            params={"source_name": statement_ids[i], "target_name": statement_ids[i + 1]},
        )

    # Get module_path and regenerate
    func_result = graph.query(
        "MATCH (f:Function {name: $name}) RETURN f.module_path",
        params={"name": function_id},
    )
    module_path = func_result.result_set[0][0] if func_result.result_set else ""

    new_func_source = _regenerate_function_source(function_id)
    _validate_python(new_func_source)
    if module_path:
        _write_function_to_file(function_id, new_func_source, module_path)

    return {
        "function_id": function_id,
        "statement_order": statement_ids,
        "module_path": module_path,
    }


def _get_containing_function(statement_name: str) -> str | None:
    """Find the function that contains a statement.

    Args:
        statement_name: Qualified statement name.

    Returns:
        Function name or None.
    """
    graph = get_graph()
    result = graph.query(
        "MATCH (f:Function)-[:CONTAINS*1..8]->(s {name: $name}) RETURN f.name",
        params={"name": statement_name},
    )
    if result.result_set:
        return result.result_set[0][0]
    return None


def _regenerate_function_source(function_name: str) -> str:
    """Regenerate a function's source from its statement subgraph.

    Args:
        function_name: Qualified function name.

    Returns:
        Generated Python source code for the function.
    """
    graph = get_graph()

    # Get function node for signature
    func_result = graph.query(
        "MATCH (f:Function {name: $name}) RETURN f",
        params={"name": function_name},
    )
    if not func_result.result_set:
        raise NodeNotFoundError(function_name)

    func_node = func_result.result_set[0][0]
    func_props = func_node.properties if hasattr(func_node, "properties") else {}

    # If no statement-level edits, return original source_text
    source_text = func_props.get("source_text", "")

    # Get direct children ordered by seq
    children_result = graph.query(
        "MATCH (f:Function {name: $name})-[:CONTAINS]->(child) "
        "RETURN child ORDER BY child.seq",
        params={"name": function_name},
    )

    if not children_result.result_set:
        return source_text

    # Build function signature
    params = func_props.get("params", "")
    decorators = func_props.get("decorators", "")
    is_async = func_props.get("is_async", False)
    docstring = func_props.get("docstring", "")

    lines: list[str] = []

    # Add decorators
    if decorators and isinstance(decorators, list):
        for dec in decorators:
            lines.append(f"@{dec}")
    elif decorators and isinstance(decorators, str) and decorators.startswith("["):
        # Handle string-encoded list
        pass

    # Function signature
    func_short_name = function_name.rsplit(".", 1)[-1]
    prefix = "async def" if is_async else "def"
    if isinstance(params, list):
        params_str = ", ".join(params)
    elif isinstance(params, str):
        params_str = params
    else:
        params_str = ""
    lines.append(f"{prefix} {func_short_name}({params_str}):")

    # Docstring
    if docstring:
        lines.append(f'    """' + str(docstring) + '"""')

    # Statements from children
    for row in children_result.result_set:
        child = row[0]
        child_props = child.properties if hasattr(child, "properties") else {}
        child_source = child_props.get("source_text", "")
        if child_source:
            # Indent each line of the source
            for line in str(child_source).split("\n"):
                lines.append("    " + line)

    return "\n".join(lines)


def _validate_python(source: str) -> None:
    """Validate that source code is parseable Python.

    Args:
        source: Python source code string.

    Raises:
        WriteBackError: If the source contains syntax errors.
    """
    parser = _get_parser()
    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node

    # Check for ERROR nodes
    def _has_error(node: Any) -> bool:
        if node.type == "ERROR":
            return True
        for child in node.children:
            if _has_error(child):
                return True
        return False

    if _has_error(root):
        raise WriteBackError(f"Generated source has syntax errors:\n{source[:500]}")


def _write_function_to_file(function_name: str, new_source: str, module_path: str) -> None:
    """Replace a function's source in a file on disk.

    Args:
        function_name: Qualified function name.
        new_source: New function source code.
        module_path: Relative module path.
    """
    from app.config import settings

    if not settings.watch_path:
        logger.warning("No watch_path set, skipping file write")
        return

    abs_path = os.path.join(os.path.abspath(settings.watch_path), module_path)
    if not os.path.isfile(abs_path):
        logger.warning("File not found: %s", abs_path)
        return

    graph = get_graph()

    # Get original line range
    func_result = graph.query(
        "MATCH (f:Function {name: $name}) RETURN f.start_line, f.end_line",
        params={"name": function_name},
    )
    if not func_result.result_set:
        return

    start_line = int(func_result.result_set[0][0] or 1)
    end_line = int(func_result.result_set[0][1] or start_line)

    with open(abs_path, encoding="utf-8") as f:
        lines = f.readlines()

    # Replace the function lines (1-based)
    new_lines = [line + "\n" for line in new_source.split("\n")]
    lines[start_line - 1:end_line] = new_lines

    with open(abs_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    logger.info("Wrote updated function %s to %s", function_name, abs_path)

    # Update source_text in graph
    graph.query(
        "MATCH (f:Function {name: $name}) SET f.source_text = $source_text",
        params={"name": function_name, "source_text": new_source},
    )
