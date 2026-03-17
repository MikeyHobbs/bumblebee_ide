"""LLM-powered semantic intent generation (TICKET-871)."""

from __future__ import annotations

import logging

from app.models.logic_models import LogicNodeResponse, LogicNodeUpdate
from app.services.edge_service import get_edges
from app.services.logic_node_service import get_node, update_node
from app.services.model_adapter import get_adapter

logger = logging.getLogger(__name__)

# Simple cache keyed by ast_hash to avoid re-generating unchanged nodes
_intent_cache: dict[str, str] = {}


async def generate_intent(node_id: str) -> str:
    """Generate a semantic intent description for a LogicNode.

    Builds a prompt with source_text, signature, and immediate edges,
    then calls the LLM to generate a one-line description.

    Args:
        node_id: UUID of the LogicNode.

    Returns:
        Generated semantic intent string.
    """
    node = get_node(node_id)

    # Check cache
    if node.ast_hash in _intent_cache:
        return _intent_cache[node.ast_hash]

    # Build context from edges
    edges = get_edges(node_id, direction="outgoing")
    edge_descriptions: list[str] = []
    for edge in edges[:10]:  # Limit to 10 edges
        edge_descriptions.append(f"  - {edge.type}: {edge.target}")

    prompt = _build_prompt(node, edge_descriptions)

    adapter = get_adapter()
    response = await adapter.chat([
        {
            "role": "system",
            "content": (
                "You are a code documentation assistant. Generate a concise one-sentence description of what a"
                " function/method/class does based on its source code and graph relationships. Be specific and"
                " technical. Do not use phrases like 'This function' — start with a verb."
            ),
        },
        {"role": "user", "content": prompt},
    ])

    intent = response.get("message", {}).get("content", "").strip()
    if not intent:
        intent = f"{node.kind.value}: {node.name}"

    # Cache and persist
    _intent_cache[node.ast_hash] = intent

    # Update the node with the generated intent
    update_node(node_id, LogicNodeUpdate(semantic_intent=intent))

    return intent


async def batch_generate_intents(node_ids: list[str]) -> dict[str, str]:
    """Generate semantic intents for multiple nodes.

    Args:
        node_ids: List of LogicNode UUIDs.

    Returns:
        Dict mapping node_id to generated intent string.
    """
    results: dict[str, str] = {}
    for node_id in node_ids:
        try:
            intent = await generate_intent(node_id)
            results[node_id] = intent
        except Exception as exc:  # pylint: disable=broad-except  # best-effort per node
            logger.error("Failed to generate intent for %s: %s", node_id, exc)
            results[node_id] = ""
    return results


def _build_prompt(node: LogicNodeResponse, edge_descriptions: list[str]) -> str:
    """Build the LLM prompt for intent generation.

    Args:
        node: The LogicNode to describe.
        edge_descriptions: Pre-formatted edge relationship strings.

    Returns:
        Assembled prompt string for the LLM.
    """
    parts: list[str] = [
        f"Function: {node.signature}",
        f"Kind: {node.kind.value}",
    ]
    if node.docstring:
        parts.append(f"Docstring: {node.docstring}")
    if node.return_type:
        parts.append(f"Returns: {node.return_type}")
    parts.append(f"Source:\n```python\n{node.source_text}\n```")
    if edge_descriptions:
        parts.append("Graph relationships:\n" + "\n".join(edge_descriptions))
    parts.append("\nGenerate a concise one-sentence semantic intent for this code:")
    return "\n".join(parts)
