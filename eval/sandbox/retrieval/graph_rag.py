"""Graph RAG retrieval: queries the graph directly via Cypher for eval context.

This is the Bumblebee condition. Given a question, it:
1. Identifies focal node(s) via keyword matching against the graph
2. Retrieves the neighborhood via Cypher (calls, variables, types)
3. Serializes into a compact text format the model can reason over

This deliberately uses the same Cypher query path as the agent condition's
query_graph tool — the difference is that graph_rag pre-computes the context
in one shot, while the agent discovers it iteratively.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Add backend to path so we can import the graph modules
_BACKEND_ROOT = Path(__file__).resolve().parents[3] / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _init_graph() -> None:
    """Ensure the FalkorDB client is initialized."""
    from app.graph.client import init_client
    init_client()


def _get_graph():  # type: ignore[no-untyped-def]
    """Get the graph instance."""
    from app.graph.client import get_graph
    return get_graph()


def find_focal_nodes(question: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Find the most relevant graph nodes for a question via keyword matching.

    Args:
        question: Natural language question.
        max_results: Maximum number of focal nodes to return.

    Returns:
        List of node dicts with id, name, kind, module_path, signature.
    """
    _init_graph()
    graph = _get_graph()

    stop_words = {
        "what", "does", "how", "when", "where", "which", "who", "why",
        "is", "are", "do", "the", "a", "an", "of", "in", "to", "for",
        "on", "with", "from", "by", "it", "this", "that", "if", "can",
        "return", "returns", "give", "show", "find", "get", "list",
        "call", "run", "execute", "output", "result", "value", "all",
        "me", "about", "between", "through", "into", "using",
    }
    words = [w.strip("?.,!'\"()") for w in question.lower().split()]
    keywords = [w for w in words if w and w not in stop_words and len(w) > 2]

    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for keyword in keywords:
        try:
            res = graph.query(
                "MATCH (n:LogicNode) "
                "WHERE n.name CONTAINS $kw AND n.status = 'active' "
                "RETURN n.id AS id, n.name AS name, n.kind AS kind, "
                "       n.module_path AS module_path, n.signature AS signature "
                "LIMIT $limit",
                params={"kw": keyword, "limit": max_results},
            )
            for row in res.result_set:
                node_id = row[0]
                if node_id not in seen_ids:
                    seen_ids.add(node_id)
                    results.append({
                        "id": node_id,
                        "name": row[1],
                        "kind": row[2],
                        "module_path": row[3],
                        "signature": row[4],
                    })
        except Exception:
            continue

    return results[:max_results]


def retrieve_neighborhood(node_id: str, hops: int = 2) -> dict[str, Any]:
    """Retrieve a node's neighborhood from the graph via Cypher.

    Fetches:
    - The focal node itself (with source_text)
    - Outgoing calls up to N hops
    - Variables it assigns/reads/mutates/returns
    - TypeShapes it accepts/produces
    - Incoming callers (1 hop)

    Args:
        node_id: UUID of the focal node.
        hops: Traversal depth for call chains.

    Returns:
        Dict with 'focal', 'callees', 'callers', 'variables', 'types', 'edges'.
    """
    graph = _get_graph()
    result: dict[str, Any] = {
        "focal": None,
        "callees": [],
        "callers": [],
        "variables": [],
        "types": [],
        "edges": [],
    }

    # Focal node with source
    try:
        res = graph.query(
            "MATCH (n:LogicNode {id: $id}) "
            "RETURN n.name, n.kind, n.module_path, n.signature, "
            "       n.source_text, n.params, n.return_type",
            params={"id": node_id},
        )
        if res.result_set:
            row = res.result_set[0]
            result["focal"] = {
                "name": row[0], "kind": row[1], "module_path": row[2],
                "signature": row[3], "source_text": row[4],
                "params": row[5], "return_type": row[6],
            }
    except Exception:
        pass

    # Outgoing calls (up to N hops)
    try:
        res = graph.query(
            f"MATCH (n:LogicNode {{id: $id}})-[:CALLS*1..{hops}]->(callee:LogicNode) "
            "WHERE callee.status = 'active' "
            "RETURN DISTINCT callee.name, callee.kind, callee.module_path, "
            "       callee.signature, callee.source_text, callee.return_type",
            params={"id": node_id},
        )
        for row in res.result_set:
            result["callees"].append({
                "name": row[0], "kind": row[1], "module_path": row[2],
                "signature": row[3], "source_text": row[4], "return_type": row[5],
            })
    except Exception:
        pass

    # Incoming callers (1 hop — who calls this?)
    try:
        res = graph.query(
            "MATCH (caller:LogicNode)-[:CALLS]->(n:LogicNode {id: $id}) "
            "WHERE caller.status = 'active' "
            "RETURN DISTINCT caller.name, caller.kind, caller.module_path, caller.signature",
            params={"id": node_id},
        )
        for row in res.result_set:
            result["callers"].append({
                "name": row[0], "kind": row[1],
                "module_path": row[2], "signature": row[3],
            })
    except Exception:
        pass

    # Variables (assigns, reads, mutates, returns)
    try:
        res = graph.query(
            "MATCH (n:LogicNode {id: $id})-[r:ASSIGNS|READS|MUTATES|RETURNS]->(v:Variable) "
            "RETURN type(r) AS rel, v.name, v.type_hint, v.is_parameter, v.origin_line",
            params={"id": node_id},
        )
        for row in res.result_set:
            result["variables"].append({
                "relationship": row[0], "name": row[1], "type_hint": row[2],
                "is_parameter": row[3], "origin_line": row[4],
            })
    except Exception:
        pass

    # TypeShapes (accepts, produces)
    try:
        res = graph.query(
            "MATCH (n:LogicNode {id: $id})-[r:ACCEPTS|PRODUCES]->(ts:TypeShape) "
            "RETURN type(r) AS rel, ts.base_type, ts.kind, ts.definition",
            params={"id": node_id},
        )
        for row in res.result_set:
            result["types"].append({
                "relationship": row[0], "base_type": row[1],
                "kind": row[2], "definition": row[3],
            })
    except Exception:
        pass

    # Direct edges from focal node (for the relationship summary)
    try:
        res = graph.query(
            "MATCH (n:LogicNode {id: $id})-[r]->(m) "
            "WHERE m.name IS NOT NULL "
            "RETURN type(r), n.name, m.name "
            "LIMIT 30",
            params={"id": node_id},
        )
        for row in res.result_set:
            result["edges"].append({
                "type": row[0], "source": row[1], "target": row[2],
            })
    except Exception:
        pass

    return result


def serialize_neighborhood(neighborhood: dict[str, Any]) -> str:
    """Serialize a neighborhood into compact text for LLM consumption.

    Prioritizes what the model needs to write correct execution code:
    function signatures, call relationships, variable info, and source snippets.

    Args:
        neighborhood: Dict from retrieve_neighborhood().

    Returns:
        Structured text representation.
    """
    lines: list[str] = []
    focal = neighborhood.get("focal")

    if not focal:
        return ""

    # Focal node
    lines.append(f"## {focal['name']} ({focal['kind']})")
    if focal.get("module_path"):
        lines.append(f"File: `{focal['module_path']}`")
    if focal.get("signature"):
        lines.append(f"Signature: `{focal['signature']}`")
    if focal.get("return_type"):
        lines.append(f"Returns: `{focal['return_type']}`")
    lines.append("")

    # Source code of focal node
    if focal.get("source_text"):
        lines.append("```python")
        lines.append(focal["source_text"].strip())
        lines.append("```")
        lines.append("")

    # Callees
    callees = neighborhood.get("callees", [])
    if callees:
        lines.append("## Functions it calls")
        lines.append("")
        for callee in callees:
            sig = callee.get("signature") or callee["name"]
            ret = f" -> {callee['return_type']}" if callee.get("return_type") else ""
            lines.append(f"- `{sig}`{ret}")
            if callee.get("source_text"):
                lines.append(f"  ```python")
                lines.append(f"  {callee['source_text'].strip()}")
                lines.append(f"  ```")
        lines.append("")

    # Callers
    callers = neighborhood.get("callers", [])
    if callers:
        lines.append("## Called by")
        lines.append("")
        for caller in callers:
            sig = caller.get("signature") or caller["name"]
            lines.append(f"- `{sig}`")
        lines.append("")

    # Variables
    variables = neighborhood.get("variables", [])
    if variables:
        lines.append("## Variables")
        lines.append("")
        for var in variables:
            hint = f": {var['type_hint']}" if var.get("type_hint") else ""
            param = " (parameter)" if var.get("is_parameter") else ""
            lines.append(f"- [{var['relationship']}] {var['name']}{hint}{param}")
        lines.append("")

    # Types
    types = neighborhood.get("types", [])
    if types:
        lines.append("## Type Shapes")
        lines.append("")
        for ts in types:
            lines.append(f"- [{ts['relationship']}] {ts['base_type']} ({ts['kind']})")
        lines.append("")

    return "\n".join(lines)


def build_graph_context(question: str, hops: int = 2) -> str:
    """Full pipeline: question -> focal nodes -> Cypher neighborhood -> serialized context.

    This is the main entry point for the Graph RAG condition.

    Args:
        question: Natural language question about the codebase.
        hops: Traversal depth for call chain queries.

    Returns:
        Serialized context string ready to prepend to the LLM prompt.
    """
    _init_graph()

    focal_nodes = find_focal_nodes(question)

    if not focal_nodes:
        return "No relevant code entities found in the graph for this question."

    sections: list[str] = []

    for node in focal_nodes[:3]:
        try:
            neighborhood = retrieve_neighborhood(node["id"], hops=hops)
            serialized = serialize_neighborhood(neighborhood)
            if serialized.strip():
                sections.append(serialized)
        except Exception:
            continue

    if not sections:
        return "Graph query returned no results for this question."

    return "\n---\n\n".join(sections)
