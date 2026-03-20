"""Tool executor: intercepts LLM tool calls and routes to backend services (TICKET-502)."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.config import settings
from app.graph.client import get_graph
from app.graph.logic_pack import (
    build_call_chain_pack,
    build_class_hierarchy_pack,
    build_function_flow_pack,
    build_impact_pack,
    build_mutation_timeline_pack,
)
from app.models.exceptions import GraphQueryError, ToolExecutionError

logger = logging.getLogger(__name__)

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_graph",
            "description": (
                "Execute a read-only Cypher query against the FalkorDB code graph. "
                "Use this for ALL questions about the codebase. "
                "Node names are module-qualified — always use CONTAINS for matching."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cypher": {
                        "type": "string",
                        "description": "A read-only Cypher query to execute against the code graph.",
                    }
                },
                "required": ["cypher"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the content of a source file from the indexed repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path within the indexed repository.",
                    }
                },
                "required": ["path"],
            },
        },
    },
]


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Route a tool call to the appropriate handler.

    Args:
        tool_name: Name of the tool to execute.
        arguments: Tool arguments dict.

    Returns:
        Dict with 'result' key on success, or 'error' key on failure.
    """
    handlers: dict[str, Any] = {
        "query_graph": _handle_query_graph,
        "read_file": _handle_read_file,
    }

    handler = handlers.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        result = await handler(arguments)
        return {"result": result}
    except ToolExecutionError as exc:
        logger.warning("Tool execution error for %s: %s", tool_name, exc)
        return {"error": str(exc)}
    except Exception as exc:
        logger.error("Unexpected error executing tool %s: %s", tool_name, exc, exc_info=True)
        return {"error": f"Internal error executing {tool_name}: {exc}"}


async def _handle_query_graph(arguments: dict[str, Any]) -> Any:
    """Execute an ad-hoc Cypher query.

    Args:
        arguments: Dict with 'cypher' key.

    Returns:
        Query results as list of dicts.

    Raises:
        ToolExecutionError: If the query is invalid or fails.
    """
    cypher = arguments.get("cypher", "")
    if not cypher:
        raise ToolExecutionError("Missing 'cypher' argument")

    # Block write operations
    write_keywords = {"CREATE", "SET", "DELETE", "DETACH", "MERGE", "REMOVE", "DROP"}
    upper = cypher.upper()
    if any(kw in upper for kw in write_keywords):
        raise ToolExecutionError("Write operations are not allowed")

    graph = get_graph()
    try:
        result = graph.query(cypher)
    except Exception as exc:
        raise ToolExecutionError(f"Cypher execution failed: {exc}") from exc

    rows: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()
    header = result.header if hasattr(result, "header") else []
    column_names = [h[1] if isinstance(h, (list, tuple)) else str(h) for h in header]

    for record in result.result_set:
        row: dict[str, Any] = {}
        for idx, value in enumerate(record):
            col_name = column_names[idx] if idx < len(column_names) else f"col_{idx}"
            if hasattr(value, "properties"):
                labels = value.labels if hasattr(value, "labels") else []
                props = {k: (v if isinstance(v, (str, int, bool)) or v is None else str(v))
                         for k, v in value.properties.items()}
                node_id = str(props.get("id", props.get("name", "")))
                row[col_name] = {"labels": labels, "properties": props}
                # Collect unique nodes for graph display
                if node_id and node_id not in seen_node_ids:
                    seen_node_ids.add(node_id)
                    label = labels[0] if labels else "Unknown"
                    nodes.append({"id": node_id, "label": label, "properties": props})
            elif isinstance(value, list):
                converted = []
                for item in value:
                    if hasattr(item, "properties"):
                        labels = item.labels if hasattr(item, "labels") else []
                        converted.append({"labels": labels, "properties": dict(item.properties)})
                    else:
                        converted.append(item)
                row[col_name] = converted
            else:
                row[col_name] = value
        rows.append(row)

    # Fallback: resolve scalar strings that might be node names/ids
    if not seen_node_ids:
        candidate_names: set[str] = set()
        for row in rows:
            for v in row.values():
                if isinstance(v, str) and ("." in v or "-" in v):
                    candidate_names.add(v)
        if candidate_names:
            try:
                resolve_result = graph.query(
                    "MATCH (n) WHERE n.name IN $names OR n.id IN $names RETURN n",
                    params={"names": list(candidate_names)},
                )
                for rrow in resolve_result.result_set:
                    for rval in rrow:
                        if hasattr(rval, "properties"):
                            labels = rval.labels if hasattr(rval, "labels") else []
                            props = {k: (v if isinstance(v, (str, int, bool)) or v is None else str(v))
                                     for k, v in rval.properties.items()}
                            node_id = str(props.get("id", props.get("name", "")))
                            if node_id and node_id not in seen_node_ids:
                                seen_node_ids.add(node_id)
                                label = labels[0] if labels else "Unknown"
                                nodes.append({"id": node_id, "label": label, "properties": props})
            except Exception:
                logger.debug("Fallback node resolution failed", exc_info=True)

    # Fetch edges between collected nodes for graph highlighting
    edges: list[dict[str, Any]] = []
    if len(seen_node_ids) > 1:
        try:
            id_list = list(seen_node_ids)
            edge_result = graph.query(
                "MATCH (a)-[r]->(b) WHERE a.id IN $ids AND b.id IN $ids RETURN type(r) AS type, a.id AS source, b.id AS target",
                params={"ids": id_list},
            )
            for erow in edge_result.result_set:
                edges.append({"type": erow[0], "source": erow[1], "target": erow[2], "properties": {}})
        except Exception:
            pass

    return {"rows": rows, "nodes": nodes, "edges": edges}


async def _handle_mutation_timeline(arguments: dict[str, Any]) -> Any:
    """Build a mutation timeline for a variable.

    Args:
        arguments: Dict with 'variable_name' key.

    Returns:
        Mutation timeline Logic Pack.

    Raises:
        ToolExecutionError: If variable_name is missing.
    """
    variable_name = arguments.get("variable_name", "")
    if not variable_name:
        raise ToolExecutionError("Missing 'variable_name' argument")

    try:
        return build_mutation_timeline_pack(variable_name)
    except Exception as exc:
        raise ToolExecutionError(f"Failed to build mutation timeline: {exc}") from exc


async def _handle_impact_analysis(arguments: dict[str, Any]) -> Any:
    """Build an impact analysis for a function.

    Args:
        arguments: Dict with 'function_name' key.

    Returns:
        Impact analysis Logic Pack.

    Raises:
        ToolExecutionError: If function_name is missing.
    """
    function_name = arguments.get("function_name", "")
    if not function_name:
        raise ToolExecutionError("Missing 'function_name' argument")

    try:
        return build_impact_pack(function_name)
    except Exception as exc:
        raise ToolExecutionError(f"Failed to build impact analysis: {exc}") from exc


async def _handle_get_logic_pack(arguments: dict[str, Any]) -> Any:
    """Build the requested Logic Pack.

    Args:
        arguments: Dict with 'pack_type' and 'entity_name' keys, optional 'hops'.

    Returns:
        Logic Pack dict.

    Raises:
        ToolExecutionError: If required arguments are missing or pack_type is invalid.
    """
    pack_type = arguments.get("pack_type", "")
    entity_name = arguments.get("entity_name", "")
    if not pack_type or not entity_name:
        raise ToolExecutionError("Missing 'pack_type' or 'entity_name' argument")

    builders = {
        "call_chain": lambda: build_call_chain_pack(entity_name, arguments.get("hops", 2)),
        "mutation_timeline": lambda: build_mutation_timeline_pack(entity_name),
        "impact": lambda: build_impact_pack(entity_name),
        "class_hierarchy": lambda: build_class_hierarchy_pack(entity_name),
        "function_flow": lambda: build_function_flow_pack(entity_name),
    }

    builder = builders.get(pack_type)
    if builder is None:
        raise ToolExecutionError(f"Unknown pack_type: {pack_type}")

    try:
        return builder()
    except Exception as exc:
        raise ToolExecutionError(f"Failed to build {pack_type} pack: {exc}") from exc


async def _handle_read_file(arguments: dict[str, Any]) -> Any:
    """Read a file from the indexed repository.

    Args:
        arguments: Dict with 'path' key.

    Returns:
        Dict with 'path' and 'content' keys.

    Raises:
        ToolExecutionError: If the file cannot be read.
    """
    path = arguments.get("path", "")
    if not path:
        raise ToolExecutionError("Missing 'path' argument")

    if not settings.watch_path:
        raise ToolExecutionError("No repository indexed. Use POST /api/v1/index first.")

    abs_path = os.path.join(os.path.abspath(settings.watch_path), path)
    repo_root = os.path.abspath(settings.watch_path)

    # Prevent directory traversal
    if not os.path.abspath(abs_path).startswith(repo_root):
        raise ToolExecutionError("Path traversal not allowed")

    if not os.path.isfile(abs_path):
        raise ToolExecutionError(f"File not found: {path}")

    try:
        with open(abs_path, encoding="utf-8") as f:
            content = f.read()
        return {"path": path, "content": content}
    except UnicodeDecodeError as exc:
        raise ToolExecutionError("File is not valid UTF-8 text") from exc
    except OSError as exc:
        raise ToolExecutionError(f"Cannot read file: {exc}") from exc
