"""Tests for model adapter text-based tool call detection (TICKET-502).

Verifies that _try_parse_text_tool_call handles all output formats
that small models (llama3.2, phi3) produce when they don't support
native tool_calls.
"""

from __future__ import annotations

import pytest

from app.services.agent.model_adapter import _try_extract_cypher_as_tool_call, _try_parse_text_tool_call


class TestTextToolCallDetection:
    """Verify extraction of tool calls from LLM text output."""

    # --- Should match ---

    def test_clean_json(self) -> None:
        """Bare JSON object with 'arguments' key."""
        text = '{"name": "query_graph", "arguments": {"cypher": "MATCH (n) RETURN n"}}'
        result = _try_parse_text_tool_call(text)
        assert result is not None
        assert result["name"] == "query_graph"
        assert result["arguments"]["cypher"] == "MATCH (n) RETURN n"

    def test_parameters_key(self) -> None:
        """Some models use 'parameters' instead of 'arguments'."""
        text = '{"name": "query_graph", "parameters": {"cypher": "MATCH (n) RETURN n"}}'
        result = _try_parse_text_tool_call(text)
        assert result is not None
        assert result["name"] == "query_graph"
        assert result["arguments"]["cypher"] == "MATCH (n) RETURN n"

    def test_markdown_json_block(self) -> None:
        """LLM wraps the call in ```json ... ``` fences."""
        text = '```json\n{"name": "query_graph", "arguments": {"cypher": "MATCH (n) RETURN n"}}\n```'
        result = _try_parse_text_tool_call(text)
        assert result is not None
        assert result["name"] == "query_graph"

    def test_markdown_plain_block(self) -> None:
        """LLM wraps the call in ``` ... ``` without language tag."""
        text = '```\n{"name": "query_graph", "arguments": {"cypher": "MATCH (n) RETURN n"}}\n```'
        result = _try_parse_text_tool_call(text)
        assert result is not None
        assert result["name"] == "query_graph"

    def test_preamble_then_json(self) -> None:
        """LLM adds explanation text before the JSON block."""
        text = (
            "I'll query the graph to find what register_user calls.\n\n"
            '```json\n{"name": "query_graph", "arguments": {"cypher": '
            '"MATCH (f:LogicNode)-[:CALLS]->(g:LogicNode) WHERE f.name CONTAINS '
            "'register_user' RETURN g.name\"}}\n```"
        )
        result = _try_parse_text_tool_call(text)
        assert result is not None
        assert result["name"] == "query_graph"
        assert "register_user" in result["arguments"]["cypher"]

    def test_preamble_then_bare_json(self) -> None:
        """LLM adds explanation text then bare JSON (no fences)."""
        text = (
            "Let me look that up.\n\n"
            '{"name": "query_graph", "arguments": {"cypher": "MATCH (n) RETURN n"}}'
        )
        result = _try_parse_text_tool_call(text)
        assert result is not None
        assert result["name"] == "query_graph"

    def test_whitespace_padding(self) -> None:
        """Extra whitespace around JSON."""
        text = '  \n  {"name": "query_graph", "arguments": {"cypher": "MATCH (n) RETURN n"}}  \n  '
        result = _try_parse_text_tool_call(text)
        assert result is not None
        assert result["name"] == "query_graph"

    def test_read_file_tool(self) -> None:
        """read_file is a known tool."""
        text = '{"name": "read_file", "arguments": {"path": "services/auth.py"}}'
        result = _try_parse_text_tool_call(text)
        assert result is not None
        assert result["name"] == "read_file"

    # --- Should NOT match ---

    def test_unknown_tool_rejected(self) -> None:
        """Hallucinated function name is not a known tool."""
        text = '{"name": "register_user", "parameters": {"email": null}}'
        assert _try_parse_text_tool_call(text) is None

    def test_removed_tool_rejected(self) -> None:
        """Previously-valid tools that were removed should not match."""
        text = '{"name": "get_logic_pack", "arguments": {"pack_type": "call_chain", "entity_name": "foo"}}'
        assert _try_parse_text_tool_call(text) is None

    def test_plain_text(self) -> None:
        """Normal assistant text."""
        assert _try_parse_text_tool_call("Here is the answer") is None

    def test_partial_json(self) -> None:
        """Incomplete JSON."""
        assert _try_parse_text_tool_call('{"name": "query_graph"') is None

    def test_empty_string(self) -> None:
        assert _try_parse_text_tool_call("") is None

    def test_json_without_name(self) -> None:
        """Valid JSON but missing 'name' key."""
        assert _try_parse_text_tool_call('{"cypher": "MATCH (n) RETURN n"}') is None

    def test_json_array(self) -> None:
        """JSON array, not object."""
        assert _try_parse_text_tool_call('[{"name": "query_graph"}]') is None

    def test_prose_with_json_example(self) -> None:
        """Long prose that happens to contain JSON — should NOT match."""
        text = (
            "You can use something like this to query:\n"
            "MATCH (n) RETURN n\n"
            "This will return all nodes in the graph."
        )
        assert _try_parse_text_tool_call(text) is None

    def test_multiline_cypher_in_block(self) -> None:
        """Multiline Cypher inside the JSON arguments."""
        text = (
            '```json\n'
            '{"name": "query_graph", "arguments": {"cypher": '
            '"MATCH (a:LogicNode)-[:CALLS]->(b:LogicNode)\\n'
            'WHERE a.module_path <> b.module_path\\n'
            'RETURN a.name, b.name LIMIT 20"}}\n'
            '```'
        )
        result = _try_parse_text_tool_call(text)
        assert result is not None
        assert result["name"] == "query_graph"


class TestCypherExtractionFallback:
    """Verify extraction of raw Cypher from LLM text when tool call JSON is absent."""

    def test_cypher_in_code_fence(self) -> None:
        """LLM outputs Cypher in a ```cypher ... ``` block."""
        text = (
            "Here's the query:\n\n"
            "```cypher\n"
            "MATCH (v:Variable)-[:PASSES_TO]->(p:Variable)\n"
            "WHERE v.scope CONTAINS 'run'\n"
            "RETURN v.name AS source, p.name AS target\n"
            "```"
        )
        result = _try_extract_cypher_as_tool_call(text)
        assert result is not None
        assert result["name"] == "query_graph"
        assert "PASSES_TO" in result["arguments"]["cypher"]

    def test_cypher_in_plain_fence(self) -> None:
        """LLM outputs Cypher in ``` ... ``` without language tag."""
        text = "```\nMATCH (n:LogicNode)-[:CALLS]->(m) RETURN n.name, m.name\n```"
        result = _try_extract_cypher_as_tool_call(text)
        assert result is not None
        assert result["arguments"]["cypher"].startswith("MATCH")

    def test_bare_cypher(self) -> None:
        """LLM outputs raw Cypher without any fencing."""
        text = "MATCH (f:LogicNode)-[:CALLS]->(g:LogicNode) WHERE f.name CONTAINS 'run' RETURN g.name"
        result = _try_extract_cypher_as_tool_call(text)
        assert result is not None

    def test_preamble_then_fenced_cypher(self) -> None:
        """LLM explains then shows fenced Cypher — the real failure case."""
        text = (
            "To trace the data flow from the `run` function, we need to find all "
            "variables that are passed between function calls.\n\n"
            "```cypher\n"
            "MATCH (v1:Variable)-[:PASSES_TO]->(v2:Variable)\n"
            "WHERE v1.scope CONTAINS 'run'\n"
            "RETURN v1.name AS source, v2.name AS target\n"
            "ORDER BY v1.origin_line\n"
            "```\n\n"
            "This query will return variable assignments within the run function."
        )
        result = _try_extract_cypher_as_tool_call(text)
        assert result is not None
        assert "PASSES_TO" in result["arguments"]["cypher"]

    def test_not_cypher(self) -> None:
        """Plain text should not match."""
        assert _try_extract_cypher_as_tool_call("Here is the answer") is None

    def test_no_return_clause(self) -> None:
        """Cypher without RETURN is invalid — should not match."""
        assert _try_extract_cypher_as_tool_call("MATCH (n) DELETE n") is None
