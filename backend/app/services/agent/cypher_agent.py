"""NL-to-Cypher agent: translates natural language into FalkorDB graph queries (TICKET-502)."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.graph.client import get_graph
from app.graph.schema_description import CYPHER_SYSTEM_PROMPT, FEW_SHOT_EXAMPLES, GRAPH_SCHEMA
from app.models.exceptions import GraphQueryError
from app.services.agent.model_adapter import ModelAdapter

logger = logging.getLogger(__name__)

# Re-export for backward compat
SYSTEM_PROMPT = CYPHER_SYSTEM_PROMPT


def _extract_cypher(text: str) -> str:
    """Extract a Cypher query from model output, stripping markdown fences.

    Args:
        text: Raw model response text.

    Returns:
        Cleaned Cypher query string.
    """
    # Strip markdown code fences
    fenced = re.search(r"```(?:cypher)?\s*\n?(.*?)```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()

    # Try to find a MATCH statement
    match = re.search(r"(MATCH\s+.+)", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return text.strip()


def _is_read_only(cypher: str) -> bool:
    """Check that a Cypher query is read-only.

    Args:
        cypher: Cypher query string.

    Returns:
        True if the query is read-only.
    """
    write_keywords = {"CREATE", "SET", "DELETE", "DETACH", "MERGE", "REMOVE", "DROP"}
    upper = cypher.upper()
    return not any(kw in upper for kw in write_keywords)


def _make_fuzzy(cypher: str) -> str:
    """Convert exact name matches to fuzzy CONTAINS matches.

    Transforms patterns like {name: 'X'} into WHERE ... CONTAINS 'X'.

    Args:
        cypher: Original Cypher query.

    Returns:
        Modified query using CONTAINS for name matching.
    """
    # Replace {name: 'value'} with CONTAINS pattern
    # This handles the common case where exact match returns nothing
    pattern = r"\{name:\s*'([^']+)'\}"
    matches = list(re.finditer(pattern, cypher))
    if not matches:
        return cypher

    result = cypher
    for m in reversed(matches):
        value = m.group(1)
        # Replace the property constraint with empty braces and add WHERE clause
        result = result[:m.start()] + "" + result[m.end():]
        # Find the variable name for this node (the character before the opening paren/colon)
        prefix = cypher[:m.start()]
        # Find the variable binding like (f:Function or (f
        var_match = re.search(r"\((\w+)(?::\w+)?\s*$", prefix)
        if var_match:
            var_name = var_match.group(1)
            # Add CONTAINS clause before RETURN
            return_idx = result.upper().find("RETURN")
            if return_idx > 0:
                where_clause = f" WHERE {var_name}.name CONTAINS '{value}' "
                # Check if there's already a WHERE clause
                if "WHERE" in result[:return_idx].upper():
                    where_clause = f" AND {var_name}.name CONTAINS '{value}' "
                result = result[:return_idx] + where_clause + result[return_idx:]

    return result


def _execute_cypher(cypher: str) -> list[dict[str, Any]]:
    """Execute a Cypher query against FalkorDB and return results as dicts.

    Args:
        cypher: Valid read-only Cypher query.

    Returns:
        List of result row dicts.

    Raises:
        GraphQueryError: If the query execution fails.
    """
    graph = get_graph()
    try:
        result = graph.query(cypher)
    except Exception as exc:
        raise GraphQueryError(f"Cypher execution failed: {exc}") from exc

    rows: list[dict[str, Any]] = []
    header = result.header if hasattr(result, "header") else []
    column_names = [h[1] if isinstance(h, (list, tuple)) else str(h) for h in header]

    for record in result.result_set:
        row: dict[str, Any] = {}
        for idx, value in enumerate(record):
            col_name = column_names[idx] if idx < len(column_names) else f"col_{idx}"
            # Convert FalkorDB nodes/edges to dicts
            if hasattr(value, "properties"):
                labels = value.labels if hasattr(value, "labels") else []
                row[col_name] = {
                    "labels": labels,
                    "properties": dict(value.properties),
                }
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

    return rows


async def query_with_nl(question: str, model_adapter: ModelAdapter) -> dict[str, Any]:
    """Translate a natural language question into a Cypher query and execute it.

    This is the main entry point for the NL-to-Cypher agent. It:
    1. Sends the question with SYSTEM_PROMPT to the model.
    2. Extracts the Cypher query from the response.
    3. Executes it against FalkorDB.
    4. If zero results, retries with fuzzy matching (CONTAINS instead of exact match).
    5. Returns structured results.

    Args:
        question: Natural language question about the codebase.
        model_adapter: The model adapter to use for NL-to-Cypher translation.

    Returns:
        Dict with 'cypher', 'results', and 'row_count' keys.
    """
    start = time.perf_counter()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    try:
        response = await model_adapter.chat(messages)
    except Exception as exc:
        logger.error("Model call failed for NL query: %s", exc)
        elapsed = (time.perf_counter() - start) * 1000
        return {"cypher": "", "results": [], "row_count": 0, "latency_ms": round(elapsed, 1), "error": str(exc)}

    raw_content = response.get("message", {}).get("content", "")
    cypher = _extract_cypher(raw_content)

    if not cypher:
        elapsed = (time.perf_counter() - start) * 1000
        return {"cypher": "", "results": [], "row_count": 0, "latency_ms": round(elapsed, 1), "error": "No Cypher query generated"}

    if not _is_read_only(cypher):
        elapsed = (time.perf_counter() - start) * 1000
        return {"cypher": cypher, "results": [], "row_count": 0, "latency_ms": round(elapsed, 1), "error": "Write operations are not allowed"}

    # First attempt: execute as-is
    try:
        results = _execute_cypher(cypher)
    except GraphQueryError as exc:
        logger.warning("Cypher query failed: %s", exc)
        elapsed = (time.perf_counter() - start) * 1000
        return {"cypher": cypher, "results": [], "row_count": 0, "latency_ms": round(elapsed, 1), "error": str(exc)}

    # If zero results, retry with fuzzy matching
    if not results:
        fuzzy_cypher = _make_fuzzy(cypher)
        if fuzzy_cypher != cypher:
            logger.info("Retrying with fuzzy query: %s", fuzzy_cypher)
            try:
                results = _execute_cypher(fuzzy_cypher)
                cypher = fuzzy_cypher
            except GraphQueryError:
                pass  # Return the original empty result

    elapsed = (time.perf_counter() - start) * 1000
    return {"cypher": cypher, "results": results, "row_count": len(results), "latency_ms": round(elapsed, 1)}
