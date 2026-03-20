"""Graph RAG retrieval: converts Logic Packs into compact text context for LLM prompts.

This is the Bumblebee condition. Given a question, it:
1. Identifies focal node(s) via NL-to-Cypher or keyword match
2. Builds a Logic Pack (call chain + variable flow + type shapes)
3. Serializes the pack into a structured text format the model can reason over

The serialized format is NOT raw JSON — it's a compact, readable representation
that prioritizes the information a model needs to write correct execution code:
function signatures, call relationships, and source snippets.
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


def retrieve_logic_pack(
    focal_name: str,
    pack_type: str = "call_chain",
    hops: int = 2,
) -> dict[str, Any]:
    """Retrieve a Logic Pack from the graph for a focal entity.

    Args:
        focal_name: Name of the function/class/variable to center the pack on.
        pack_type: Type of Logic Pack (call_chain, mutation_timeline, impact,
                   class_hierarchy, function_flow).
        hops: Traversal depth for call_chain packs.

    Returns:
        Raw Logic Pack dict with nodes, edges, and snippets.
    """
    _init_graph()

    from app.graph.logic_pack import (
        build_call_chain_pack,
        build_class_hierarchy_pack,
        build_function_flow_pack,
        build_impact_pack,
        build_mutation_timeline_pack,
    )

    builders = {
        "call_chain": lambda: build_call_chain_pack(focal_name, hops=hops),
        "mutation_timeline": lambda: build_mutation_timeline_pack(focal_name),
        "impact": lambda: build_impact_pack(focal_name),
        "class_hierarchy": lambda: build_class_hierarchy_pack(focal_name),
        "function_flow": lambda: build_function_flow_pack(focal_name),
    }

    builder = builders.get(pack_type)
    if not builder:
        raise ValueError(f"Unknown pack_type: {pack_type}")

    return builder()


def find_focal_nodes(question: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Find the most relevant graph nodes for a question via Cypher.

    Uses CONTAINS matching on node names and semantic_intent to find candidates.

    Args:
        question: Natural language question.
        max_results: Maximum number of focal nodes to return.

    Returns:
        List of node dicts with id, name, kind, module_path, signature.
    """
    _init_graph()
    from app.graph.client import get_graph

    graph = get_graph()

    # Extract keywords from the question (simple heuristic: nouns and function-like tokens)
    # Strip common question words
    stop_words = {
        "what", "does", "how", "when", "where", "which", "who", "why",
        "is", "are", "do", "the", "a", "an", "of", "in", "to", "for",
        "on", "with", "from", "by", "it", "this", "that", "if", "can",
        "return", "returns", "give", "show", "find", "get", "list",
        "call", "run", "execute", "output", "result", "value",
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
                "       n.module_path AS module_path, n.signature AS signature, "
                "       n.semantic_intent AS semantic_intent "
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
                        "semantic_intent": row[5],
                    })
        except Exception:
            continue

    return results[:max_results]


def serialize_logic_pack(pack: dict[str, Any]) -> str:
    """Serialize a Logic Pack into compact text for LLM consumption.

    Output format prioritizes what the model needs to write correct execution code:
    1. Function signatures with full params and return types
    2. Call relationships (who calls who)
    3. Variable flow (what gets passed where)
    4. Source code snippets for the functions the model will need to call

    Args:
        pack: Raw Logic Pack dict from retrieve_logic_pack().

    Returns:
        Structured text representation.
    """
    lines: list[str] = []

    # Group nodes by type
    functions: list[dict[str, Any]] = []
    variables: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []

    for node in pack.get("nodes", []):
        props = node.get("properties", {})
        kind = props.get("kind", node.get("label", ""))
        if kind in ("function", "method", "class", "module", "flow_function"):
            functions.append(node)
        elif node.get("label") == "Variable" or kind == "Variable":
            variables.append(node)
        else:
            others.append(node)

    # Section 1: Functions with signatures
    if functions:
        lines.append("## Functions")
        lines.append("")
        for fn in functions:
            props = fn.get("properties", {})
            name = props.get("name", fn.get("id", "?"))
            sig = props.get("signature", "")
            kind = props.get("kind", "function")
            module = props.get("module_path", "")
            ret = props.get("return_type", "")
            intent = props.get("semantic_intent", "")

            header = f"- **{name}** ({kind})"
            if module:
                header += f" in `{module}`"
            lines.append(header)

            if sig:
                lines.append(f"  Signature: `{sig}`")
            if ret:
                lines.append(f"  Returns: `{ret}`")
            if intent:
                lines.append(f"  Purpose: {intent}")
            lines.append("")

    # Section 2: Variables
    if variables:
        lines.append("## Variables")
        lines.append("")
        for var in variables:
            props = var.get("properties", {})
            name = props.get("name", var.get("id", "?"))
            type_hint = props.get("type_hint", "")
            scope = props.get("scope", "")
            line = f"- **{name}**"
            if type_hint:
                line += f": `{type_hint}`"
            if scope:
                line += f" (scope: {scope})"
            lines.append(line)
        lines.append("")

    # Section 3: Relationships
    edges = pack.get("edges", [])
    if edges:
        lines.append("## Relationships")
        lines.append("")
        for edge in edges:
            etype = edge.get("type", "?")
            src = edge.get("source", "?")
            tgt = edge.get("target", "?")
            lines.append(f"- {src} --[{etype}]--> {tgt}")
        lines.append("")

    # Section 4: Source code (the critical part for execution)
    snippets = pack.get("snippets", {})
    if snippets:
        lines.append("## Source Code")
        lines.append("")
        for name, source in snippets.items():
            lines.append(f"### {name}")
            lines.append("```python")
            lines.append(source.strip())
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def build_graph_context(question: str, hops: int = 2) -> str:
    """Full pipeline: question → focal nodes → Logic Packs → serialized context.

    This is the main entry point for the Graph RAG condition.

    Args:
        question: Natural language question about the codebase.
        hops: Traversal depth for call chain packs.

    Returns:
        Serialized context string ready to prepend to the LLM prompt.
    """
    focal_nodes = find_focal_nodes(question)

    if not focal_nodes:
        return "No relevant code entities found in the graph for this question."

    sections: list[str] = []
    seen_snippets: set[str] = set()

    for node in focal_nodes[:3]:  # Top 3 focal nodes
        name = node["name"]
        kind = node["kind"]

        # Choose pack type based on node kind and question
        if kind in ("class",):
            pack_type = "class_hierarchy"
        elif "variable" in question.lower() or "mutate" in question.lower():
            pack_type = "impact"
        else:
            pack_type = "call_chain"

        try:
            pack = retrieve_logic_pack(name, pack_type=pack_type, hops=hops)
            # Deduplicate snippets across packs
            for snippet_id in list(pack.get("snippets", {}).keys()):
                if snippet_id in seen_snippets:
                    del pack["snippets"][snippet_id]
                else:
                    seen_snippets.add(snippet_id)

            serialized = serialize_logic_pack(pack)
            if serialized.strip():
                sections.append(f"# Context for: {name}\n\n{serialized}")
        except Exception:
            continue

    if not sections:
        return "Graph query returned no results for this question."

    return "\n---\n\n".join(sections)
