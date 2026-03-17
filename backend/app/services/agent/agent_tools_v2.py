"""Agent tool executor for the 800-series schema (TICKET-870).

Implements 17 tools for AI agents to interact with the Code-as-Data graph.
All tools are registered in OpenAI-compatible tool-use format for Ollama.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# --- Tool definitions in OpenAI-compatible format ---

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    # Query tools (read-only)
    {
        "type": "function",
        "function": {
            "name": "find_node",
            "description": "Search LogicNodes by name, tag, or semantic intent",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term"},
                    "kind": {"type": "string", "description": "Filter by kind (function, method, class, constant, type_alias, flow_function)", "default": ""},
                    "limit": {"type": "integer", "description": "Max results", "default": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_node",
            "description": "Get a LogicNode by UUID with full source and signature",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "UUID of the LogicNode"},
                },
                "required": ["node_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dependencies",
            "description": "Get outgoing dependency edges from a LogicNode",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "depth": {"type": "integer", "default": 2},
                    "edge_types": {"type": "array", "items": {"type": "string"}, "description": "Filter by edge types"},
                },
                "required": ["node_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dependents",
            "description": "Get incoming dependent edges to a LogicNode",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "depth": {"type": "integer", "default": 2},
                },
                "required": ["node_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_variable_timeline",
            "description": "Get the full mutation timeline for a variable: origin, mutations, reads, passes, feeds",
            "parameters": {
                "type": "object",
                "properties": {
                    "variable_id": {"type": "string", "description": "UUID of the Variable"},
                },
                "required": ["variable_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trace_variable",
            "description": "Find a variable by name and trace its lifecycle across all LogicNodes",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Variable name"},
                    "scope": {"type": "string", "description": "Optional scope filter"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_logic_pack",
            "description": "Get a pre-processed subgraph (Logic Pack) for LLM consumption",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "hops": {"type": "integer", "default": 2},
                },
                "required": ["node_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_flow",
            "description": "Get a named end-to-end flow with its steps and sub-flows",
            "parameters": {
                "type": "object",
                "properties": {
                    "flow_id": {"type": "string"},
                },
                "required": ["flow_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_gaps",
            "description": "Find missing connections, dead ends, orphans, circular deps",
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "description": "Module path filter"},
                    "analysis_type": {"type": "string", "enum": ["dead_ends", "orphans", "missing_error_handling", "circular_deps", "untested_mutations", "all"]},
                },
                "required": ["analysis_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_cypher",
            "description": "Run a raw Cypher graph query",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Cypher query"},
                    "params": {"type": "object", "description": "Query parameters"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "project_vfs",
            "description": "Generate virtual file from graph (VFS projection)",
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "description": "Module path to project"},
                    "format": {"type": "string", "default": "python"},
                },
                "required": ["scope"],
            },
        },
    },
    # Mutation tools (write operations)
    {
        "type": "function",
        "function": {
            "name": "create_node",
            "description": "Create a new LogicNode with auto-computed hash and variable extraction",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "kind": {"type": "string", "enum": ["function", "method", "class", "constant", "type_alias", "flow_function"]},
                    "source_text": {"type": "string"},
                    "semantic_intent": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "kind", "source_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_node",
            "description": "Update a LogicNode's source (same UUID, new hash, re-extracted variables)",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "source_text": {"type": "string"},
                },
                "required": ["node_id", "source_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deprecate_node",
            "description": "Soft-delete a LogicNode (edges preserved as history)",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "replacement": {"type": "string", "description": "UUID of replacement node"},
                },
                "required": ["node_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_edge",
            "description": "Create a typed edge between two nodes",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "type": {"type": "string"},
                    "properties": {"type": "object"},
                },
                "required": ["source", "target", "type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_edge",
            "description": "Remove an edge between two nodes",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "type": {"type": "string"},
                },
                "required": ["source", "target", "type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_flow",
            "description": "Define a named end-to-end process from a sequence of LogicNodes",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "node_ids": {"type": "array", "items": {"type": "string"}},
                    "entry_point": {"type": "string"},
                    "exit_points": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "node_ids", "entry_point"],
            },
        },
    },
]


def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute an agent tool and return structured results.

    Args:
        tool_name: Name of the tool to execute.
        arguments: Tool arguments.

    Returns:
        Dict with tool results or error message.
    """
    try:
        handler = _TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return {"error": f"Unknown tool: {tool_name}"}
        return handler(arguments)
    except Exception as exc:
        logger.error("Tool execution error (%s): %s", tool_name, exc)
        return {"error": str(exc)}


# --- Tool handlers ---


def _handle_find_node(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.crud.logic_node_service import find_nodes
    nodes = find_nodes(query=args["query"], kind=args.get("kind"), limit=args.get("limit", 10))
    return {"nodes": [n.model_dump() for n in nodes]}


def _handle_get_node(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.crud.logic_node_service import get_node
    node = get_node(args["node_id"])
    return {"node": node.model_dump()}


def _handle_get_dependencies(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.crud.edge_service import get_dependencies
    edges = get_dependencies(args["node_id"], depth=args.get("depth", 2), edge_types=args.get("edge_types"))
    return {"edges": [e.model_dump() for e in edges]}


def _handle_get_dependents(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.crud.edge_service import get_dependents
    edges = get_dependents(args["node_id"], depth=args.get("depth", 2))
    return {"edges": [e.model_dump() for e in edges]}


def _handle_get_variable_timeline(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.crud.variable_timeline_service import get_variable_timeline
    timeline = get_variable_timeline(args["variable_id"])
    return {"timeline": timeline.model_dump()}


def _handle_trace_variable(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.crud.variable_timeline_service import trace_variable
    timelines = trace_variable(args["name"], scope=args.get("scope"))
    return {"timelines": [t.model_dump() for t in timelines]}


def _handle_get_logic_pack(args: dict[str, Any]) -> dict[str, Any]:
    from app.graph.client import get_graph
    from app.graph import logic_queries as lq
    graph = get_graph()
    result = graph.query(lq.LOGIC_PACK_SUBGRAPH, params={"node_id": args["node_id"], "depth": args.get("hops", 2)})
    if not result.result_set:
        return {"nodes": [], "edges": []}
    return {"result": "Logic pack query executed", "row_count": len(result.result_set)}


def _handle_get_flow(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.crud.flow_service import get_flow
    flow = get_flow(args["flow_id"])
    return {"flow": flow.model_dump()}


def _handle_find_gaps(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.analysis import gap_analysis
    analysis_type = args["analysis_type"]
    scope = args.get("scope")

    if analysis_type == "all":
        report = gap_analysis.get_full_report(scope)
        return {"report": report.model_dump()}
    elif analysis_type == "dead_ends":
        return {"nodes": [n.model_dump() for n in gap_analysis.find_dead_ends(scope)]}
    elif analysis_type == "orphans":
        return {"nodes": [n.model_dump() for n in gap_analysis.find_orphans(scope)]}
    elif analysis_type == "missing_error_handling":
        return {"issues": gap_analysis.find_missing_error_handling(scope)}
    elif analysis_type == "circular_deps":
        return {"cycles": gap_analysis.find_circular_deps(scope)}
    elif analysis_type == "untested_mutations":
        return {"issues": gap_analysis.find_untested_mutations(scope)}
    return {"error": f"Unknown analysis type: {analysis_type}"}


def _handle_run_cypher(args: dict[str, Any]) -> dict[str, Any]:
    from app.graph.client import get_graph
    graph = get_graph()
    result = graph.query(args["query"], params=args.get("params", {}))
    return {"result_set": [[str(col) for col in row] for row in result.result_set]}


def _handle_project_vfs(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.persistence.vfs_engine import project_module
    source = project_module(args["scope"])
    return {"source": source}


def _handle_create_node(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.crud.logic_node_service import create_node
    from app.models.logic_models import LogicNodeCreate, LogicNodeKind
    data = LogicNodeCreate(
        name=args["name"],
        kind=LogicNodeKind(args["kind"]),
        source_text=args["source_text"],
        semantic_intent=args.get("semantic_intent"),
        tags=args.get("tags", []),
    )
    node = create_node(data)
    return {"node": node.model_dump()}


def _handle_update_node(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.crud.logic_node_service import update_node
    from app.models.logic_models import LogicNodeUpdate
    data = LogicNodeUpdate(source_text=args["source_text"])
    node = update_node(args["node_id"], data)
    return {"node": node.model_dump()}


def _handle_deprecate_node(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.crud.logic_node_service import deprecate_node
    deprecate_node(args["node_id"], replacement_id=args.get("replacement"))
    return {"status": "deprecated", "node_id": args["node_id"]}


def _handle_add_edge(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.crud.edge_service import add_edge
    from app.models.logic_models import EdgeCreate, EdgeType
    data = EdgeCreate(
        source_id=args["source"],
        target_id=args["target"],
        edge_type=EdgeType(args["type"]),
        properties=args.get("properties", {}),
    )
    edge = add_edge(data)
    return {"edge": edge.model_dump()}


def _handle_remove_edge(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.crud.edge_service import remove_edge
    remove_edge(args["source"], args["target"], args["type"])
    return {"status": "removed"}


def _handle_create_flow(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.crud.flow_service import create_flow
    from app.models.logic_models import FlowCreate
    data = FlowCreate(
        name=args["name"],
        node_ids=args["node_ids"],
        entry_point=args["entry_point"],
        exit_points=args.get("exit_points", []),
    )
    flow = create_flow(data)
    return {"flow": flow.model_dump()}


_TOOL_HANDLERS: dict[str, Any] = {
    "find_node": _handle_find_node,
    "get_node": _handle_get_node,
    "get_dependencies": _handle_get_dependencies,
    "get_dependents": _handle_get_dependents,
    "get_variable_timeline": _handle_get_variable_timeline,
    "trace_variable": _handle_trace_variable,
    "get_logic_pack": _handle_get_logic_pack,
    "get_flow": _handle_get_flow,
    "find_gaps": _handle_find_gaps,
    "run_cypher": _handle_run_cypher,
    "project_vfs": _handle_project_vfs,
    "create_node": _handle_create_node,
    "update_node": _handle_update_node,
    "deprecate_node": _handle_deprecate_node,
    "add_edge": _handle_add_edge,
    "remove_edge": _handle_remove_edge,
    "create_flow": _handle_create_flow,
}
