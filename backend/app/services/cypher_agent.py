"""NL-to-Cypher agent: translates natural language into FalkorDB graph queries (TICKET-502)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.graph.client import get_graph
from app.models.exceptions import GraphQueryError
from app.services.model_adapter import ModelAdapter

logger = logging.getLogger(__name__)

GRAPH_SCHEMA = """
Node Labels and Properties:
- Module: {name, file_path, language}
- Class: {name, file_path, start_line, end_line, source_text, bases}
- Function: {name, file_path, start_line, end_line, source_text, is_async, params, return_type, origin_func}
- Variable: {name, var_type, origin_func, file_path}
- Statement: {name, stmt_type, start_line, end_line, source_text}
- ControlFlow: {name, cf_type, start_line, end_line, source_text, condition}
- Branch: {name, branch_type, start_line, end_line, source_text, condition}

Edge Types (source -> target):
- DEFINES: Module -> Class, Module -> Function, Class -> Function
- CALLS: Function -> Function
- INHERITS: Class -> Class (child -> parent)
- IMPORTS: Module -> Module
- ASSIGNS: Function -> Variable (function assigns a value to variable)
- MUTATES: Function -> Variable (function mutates a variable)
- READS: Function -> Variable (function reads a variable)
- RETURNS: Function -> Variable (function returns a variable)
- PASSES_TO: Variable -> Variable (data flow: value passed from one variable to another)
- FEEDS: Variable -> Variable (data dependency: one variable feeds into another)
- CONTAINS: Function -> Statement, Function -> ControlFlow, ControlFlow -> Branch
- NEXT: Statement -> Statement, Branch -> Statement (control flow order)
""".strip()

FEW_SHOT_EXAMPLES = """
Examples of natural language questions and their Cypher translations:

1. "What functions does main call?"
   MATCH (f:Function {name: 'main'})-[:CALLS]->(g:Function) RETURN g.name AS callee, g.file_path AS file

2. "What variables does process_data mutate?"
   MATCH (f:Function)-[:MUTATES]->(v:Variable) WHERE f.name CONTAINS 'process_data' RETURN v.name AS variable, v.var_type AS type

3. "Show the inheritance tree for Shape"
   MATCH path=(c:Class)-[:INHERITS*]->(p:Class) WHERE c.name CONTAINS 'Shape' RETURN [n IN nodes(path) | n.name] AS chain

4. "What reads variable x?"
   MATCH (f:Function)-[:READS]->(v:Variable) WHERE v.name CONTAINS 'x' RETURN f.name AS reader, f.file_path AS file

5. "Trace request.body through the codebase"
   MATCH (v:Variable)-[:PASSES_TO|FEEDS*1..5]->(target:Variable) WHERE v.name CONTAINS 'request.body' RETURN v.name AS source, target.name AS destination

6. "What's the impact of changing save_record?"
   MATCH (f:Function {name: 'save_record'})-[:MUTATES]->(v:Variable)<-[:READS]-(consumer:Function) RETURN v.name AS variable, consumer.name AS affected_function

7. "Show me all async functions"
   MATCH (f:Function {is_async: true}) RETURN f.name AS name, f.file_path AS file

8. "What does validate_payload contain?"
   MATCH (f:Function)-[:CONTAINS]->(s) WHERE f.name CONTAINS 'validate_payload' RETURN labels(s)[0] AS type, s.name AS name, s.start_line AS line

9. "Find all classes in module X"
   MATCH (m:Module)-[:DEFINES]->(c:Class) WHERE m.name CONTAINS 'X' RETURN c.name AS class_name, c.file_path AS file

10. "What passes data to parse_json?"
    MATCH (v1:Variable)-[:PASSES_TO]->(v2:Variable) WHERE v2.name CONTAINS 'parse_json' RETURN v1.name AS source, v2.name AS target
""".strip()

SYSTEM_PROMPT = f"""You are a Cypher query generator for a FalkorDB graph database that models a code repository.

{GRAPH_SCHEMA}

{FEW_SHOT_EXAMPLES}

Instructions:
- Generate ONLY a valid Cypher query. No explanations, no markdown code blocks.
- Use CONTAINS for fuzzy name matching unless the user gives an exact name.
- Always RETURN meaningful properties (name, file_path, start_line) rather than raw nodes when possible.
- For traversal queries, use variable-length relationships like [:CALLS*1..3].
- If the question is ambiguous, prefer a broader query that returns more results.
- NEVER use CREATE, SET, DELETE, DETACH, MERGE, or any write operations.
"""


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
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    try:
        response = await model_adapter.chat(messages)
    except Exception as exc:
        logger.error("Model call failed for NL query: %s", exc)
        return {"cypher": "", "results": [], "row_count": 0, "error": str(exc)}

    raw_content = response.get("message", {}).get("content", "")
    cypher = _extract_cypher(raw_content)

    if not cypher:
        return {"cypher": "", "results": [], "row_count": 0, "error": "No Cypher query generated"}

    if not _is_read_only(cypher):
        return {"cypher": cypher, "results": [], "row_count": 0, "error": "Write operations are not allowed"}

    # First attempt: execute as-is
    try:
        results = _execute_cypher(cypher)
    except GraphQueryError as exc:
        logger.warning("Cypher query failed: %s", exc)
        return {"cypher": cypher, "results": [], "row_count": 0, "error": str(exc)}

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

    return {"cypher": cypher, "results": results, "row_count": len(results)}
