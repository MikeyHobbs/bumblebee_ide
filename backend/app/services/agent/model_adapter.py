"""Model adapter abstraction for LLM backends (TICKET-502)."""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.config import settings
from app.models.exceptions import ModelAdapterError

logger = logging.getLogger(__name__)


class ModelAdapter(ABC):
    """Abstract base class for LLM model adapters."""

    @abstractmethod
    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Send messages to the model and get a response.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            tools: Optional list of tool definitions in OpenAI tool-use format.

        Returns:
            Response dict with 'message' key containing the assistant reply.
        """

    @abstractmethod
    async def stream_chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream messages from the model.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            tools: Optional list of tool definitions in OpenAI tool-use format.

        Yields:
            Dicts with partial content or tool call information.
        """
        yield {}  # pragma: no cover — abstract generator needs yield


# Known tool names — text-based tool calls for unknown names are ignored
_KNOWN_TOOLS = {"query_graph", "read_file"}


def _try_extract_cypher_as_tool_call(text: str) -> dict[str, Any] | None:
    """Detect a raw Cypher query in the text and wrap it as a query_graph tool call.

    Models sometimes output the Cypher in a code fence instead of calling the tool.
    We detect MATCH ... RETURN patterns and convert them.

    Args:
        text: The accumulated content text from the model.

    Returns:
        A tool_call dict if Cypher detected, None otherwise.
    """
    # Try markdown fenced block first
    fence_match = re.search(r"```(?:cypher)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()
    else:
        candidate = text.strip()

    # Check if it looks like a Cypher query (starts with MATCH/OPTIONAL/WITH/CALL)
    upper = candidate.lstrip().upper()
    if not any(upper.startswith(kw) for kw in ("MATCH", "OPTIONAL MATCH", "WITH", "CALL", "UNWIND")):
        return None
    if "RETURN" not in upper:
        return None

    return {"type": "tool_call", "name": "query_graph", "arguments": {"cypher": candidate}}


def _extract_json_from_text(text: str) -> str | None:
    """Extract a JSON object from text that may contain markdown fences or preamble.

    Handles:
      - Bare JSON: '{"name": ...}'
      - Markdown fenced: '```json\\n{"name": ...}\\n```'
      - Preamble + JSON: 'Some text\\n{"name": ...}'
      - Preamble + fenced: 'Some text\\n```json\\n{"name": ...}\\n```'

    Args:
        text: Raw text from the model.

    Returns:
        Extracted JSON string, or None if no JSON object found.
    """
    # Try markdown code fence first: ```json ... ``` or ``` ... ```
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()
        if candidate.startswith("{"):
            return candidate

    # Try to find a JSON object in the text (handles preamble + bare JSON)
    # Search for the first { that could start a JSON object
    brace_start = text.find("{")
    if brace_start == -1:
        return None
    candidate = text[brace_start:].strip()
    # Walk backwards from end to find the matching closing brace
    brace_end = candidate.rfind("}")
    if brace_end == -1:
        return None
    return candidate[: brace_end + 1]


def _try_parse_text_tool_call(text: str) -> dict[str, Any] | None:
    """Detect a tool call embedded as JSON text in the model's content.

    Some models (e.g. llama3.2) don't use the native tool_calls field and
    instead output the call as JSON in content. Handles markdown fences,
    preamble text, and both 'arguments' and 'parameters' keys.

    Only recognises known tool names to avoid treating hallucinated function
    calls (e.g. {"name": "register_user", ...}) as real tool invocations.

    Args:
        text: The accumulated content text from the model.

    Returns:
        A tool_call dict if detected, None otherwise.
    """
    json_str = _extract_json_from_text(text)
    if not json_str:
        return None

    try:
        parsed = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(parsed, dict) or "name" not in parsed or "arguments" not in parsed and "parameters" not in parsed:
        return None

    name = parsed["name"]
    if name not in _KNOWN_TOOLS:
        return None

    # Models may use "arguments" or "parameters"
    args = parsed.get("arguments") or parsed.get("parameters") or {}
    if not isinstance(args, dict):
        return None

    return {"type": "tool_call", "name": name, "arguments": args}


class OllamaAdapter(ModelAdapter):
    """Adapter for Ollama's /api/chat endpoint using OpenAI-compatible tool-use format."""

    def __init__(self, model_name: str | None = None) -> None:
        """Initialize the Ollama adapter.

        Args:
            model_name: Model name to use. Defaults to settings.orchestrator_model.
        """
        self.model_name = model_name or settings.orchestrator_model
        self.base_url = settings.ollama_host
        self.timeout = 120.0

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Send messages to Ollama and get a complete response.

        Args:
            messages: List of message dicts.
            tools: Optional tool definitions.

        Returns:
            Response dict with 'message' key.

        Raises:
            ModelAdapterError: If the request fails.
        """
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama HTTP error: %s %s", exc.response.status_code, exc.response.text)
            raise ModelAdapterError(f"Ollama returned status {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            logger.error("Ollama request error: %s", exc)
            raise ModelAdapterError(f"Cannot reach Ollama at {self.base_url}: {exc}") from exc

        # Detect text-based tool calls (models that don't use native tool_calls)
        msg = data.get("message", {})
        if tools and not msg.get("tool_calls") and msg.get("content"):
            text_call = _try_parse_text_tool_call(msg["content"])
            if not text_call:
                text_call = _try_extract_cypher_as_tool_call(msg["content"])
            if text_call:
                logger.info("Detected text-based tool call in chat: %s", text_call["name"])
                data["message"] = {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": text_call["name"], "arguments": text_call["arguments"]}}
                    ],
                }

        return data  # type: ignore[no-any-return]

    async def stream_chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream responses from Ollama.

        Handles two tool-call formats:
        1. Native: model sets ``tool_calls`` in the message (e.g. qwen2.5-coder).
        2. Text-based: model outputs the tool call as JSON in ``content``
           (e.g. llama3.2). Detected after the stream ends and converted.

        When tools are provided, content tokens are buffered until the stream
        finishes so we can detect text-based tool calls without partial emission.

        Args:
            messages: List of message dicts.
            tools: Optional tool definitions.

        Yields:
            Dicts with partial content chunks or tool calls.

        Raises:
            ModelAdapterError: If the request fails.
        """
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        native_tool_calls: list[dict[str, Any]] = []
        buffered_content = ""

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        message = chunk.get("message", {})
                        tool_calls_list = message.get("tool_calls")

                        if tool_calls_list:
                            # Native tool-use format — yield immediately
                            for tc in tool_calls_list:
                                call = {
                                    "type": "tool_call",
                                    "name": tc.get("function", {}).get("name", ""),
                                    "arguments": tc.get("function", {}).get("arguments", {}),
                                }
                                native_tool_calls.append(call)
                                yield call
                        elif message.get("content"):
                            content = message["content"]
                            if tools:
                                # Buffer when tools are available — might be a text tool call
                                buffered_content += content
                            else:
                                yield {"type": "token", "content": content}

                        if chunk.get("done", False):
                            break

        except httpx.HTTPStatusError as exc:
            logger.error("Ollama stream HTTP error: %s", exc.response.status_code)
            raise ModelAdapterError(f"Ollama returned status {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            logger.error("Ollama stream request error: %s", exc)
            raise ModelAdapterError(f"Cannot reach Ollama at {self.base_url}: {exc}") from exc

        # If we already got native tool calls, nothing more to do
        if native_tool_calls:
            return

        # Check if the buffered content is a text-based tool call
        if buffered_content and tools:
            text_call = _try_parse_text_tool_call(buffered_content)
            if text_call:
                logger.info("Detected text-based tool call: %s", text_call["name"])
                yield text_call
                return

            # Fallback: detect raw Cypher in code blocks or plain text
            cypher_call = _try_extract_cypher_as_tool_call(buffered_content)
            if cypher_call:
                logger.info("Detected raw Cypher in text, converting to query_graph call")
                yield cypher_call
                return

        # Not a tool call — flush buffered content as tokens
        if buffered_content:
            yield {"type": "token", "content": buffered_content}


class MockAdapter(ModelAdapter):
    """Mock adapter that returns predefined responses for testing.

    Supports tool calls by pattern matching on user message content.
    """

    # Mapping of keyword patterns to tool call responses
    TOOL_PATTERNS: list[tuple[str, str, dict[str, Any]]] = [
        (r"timeline.*(\w+)", "mutation_timeline", {}),
        (r"impact.*(\w+)", "impact_analysis", {}),
        (r"call.*chain.*(\w+)", "get_logic_pack", {"pack_type": "call_chain"}),
        (r"hierarchy.*(\w+)", "get_logic_pack", {"pack_type": "class_hierarchy"}),
        (r"class(?:es)?.*module.*(\w+)", "query_graph", {}),
        (r"inherits?.*(\w+)", "query_graph", {}),
        (r"reads?\s+variable.*(\w+)", "query_graph", {}),
        (r"calls?\s+(\w+)", "query_graph", {}),
        (r"async\s+function", "query_graph", {}),
        (r"contains?.*(\w+)", "query_graph", {}),
        (r"pass(?:es)?.*to.*(\w+)", "query_graph", {}),
        (r"read.*file.*(\S+)", "read_file", {}),
    ]

    def _match_tool_call(self, user_message: str) -> dict[str, Any] | None:
        """Try to match user message to a tool call pattern.

        Args:
            user_message: The user's message text.

        Returns:
            Tool call dict if matched, None otherwise.
        """
        text = user_message.lower()

        for pattern, tool_name, extra_args in self.TOOL_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Extract the captured entity name
                entity = match.group(1) if match.lastindex and match.lastindex >= 1 else ""
                arguments: dict[str, Any] = dict(extra_args)

                if tool_name == "mutation_timeline":
                    arguments["variable_name"] = entity
                elif tool_name == "impact_analysis":
                    arguments["function_name"] = entity
                elif tool_name == "get_logic_pack":
                    if arguments.get("pack_type") == "call_chain":
                        arguments["function_name"] = entity
                    elif arguments.get("pack_type") == "class_hierarchy":
                        arguments["class_name"] = entity
                elif tool_name == "query_graph":
                    arguments["cypher"] = self._generate_mock_cypher(text, entity)
                elif tool_name == "read_file":
                    arguments["path"] = entity

                return {
                    "type": "tool_call",
                    "name": tool_name,
                    "arguments": arguments,
                }
        return None

    def _generate_mock_cypher(self, text: str, entity: str) -> str:
        """Generate a mock Cypher query based on text keywords.

        Args:
            text: Lowered user message.
            entity: Extracted entity name.

        Returns:
            A Cypher query string.
        """
        if "inherits" in text or "hierarchy" in text:
            return f"MATCH path=(c:LogicNode {{kind: 'class'}})-[:INHERITS*]->(p:LogicNode) WHERE c.name CONTAINS '{entity}' RETURN path"
        if "calls" in text:
            return f"MATCH (f:LogicNode)-[:CALLS]->(g:LogicNode) WHERE f.name CONTAINS '{entity}' RETURN g"
        if "reads" in text and "variable" in text:
            return f"MATCH (f:LogicNode)-[:READS]->(v:Variable) WHERE v.name CONTAINS '{entity}' RETURN f, v"
        if "class" in text and "module" in text:
            return f"MATCH (n:LogicNode {{kind: 'class'}}) WHERE n.module_path CONTAINS '{entity}' RETURN n"
        if "member" in text or "method" in text:
            return f"MATCH (m:LogicNode)-[:MEMBER_OF]->(c:LogicNode {{kind: 'class'}}) WHERE c.name CONTAINS '{entity}' RETURN m"
        if "pass" in text:
            return (
                f"MATCH (v1:Variable)-[:PASSES_TO]->(v2:Variable) WHERE v2.name CONTAINS '{entity}' RETURN v1, v2"
            )
        return f"MATCH (n:LogicNode) WHERE n.name CONTAINS '{entity}' RETURN n LIMIT 10"

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Return a mock response, optionally with tool calls.

        Args:
            messages: List of message dicts.
            tools: Optional tool definitions.

        Returns:
            Mock response dict.
        """
        # Find the last user message
        user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break

        # Try to match a tool call
        tool_call = self._match_tool_call(user_msg) if tools else None

        if tool_call:
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": tool_call["name"],
                                "arguments": tool_call["arguments"],
                            }
                        }
                    ],
                }
            }

        return {
            "message": {
                "role": "assistant",
                "content": f"Mock response to: {user_msg}",
            }
        }

    async def stream_chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a mock response.

        Args:
            messages: List of message dicts.
            tools: Optional tool definitions.

        Yields:
            Mock content chunks or tool calls.
        """
        # Find the last user message
        user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break

        # Try to match a tool call
        tool_call = self._match_tool_call(user_msg) if tools else None

        if tool_call:
            yield tool_call
        else:
            # Stream the response word by word
            response_text = f"Mock response to: {user_msg}"
            words = response_text.split()
            for word in words:
                yield {"type": "token", "content": word + " "}


def get_adapter(model_name: str | None = None) -> ModelAdapter:
    """Factory function to create the appropriate model adapter.

    Args:
        model_name: Model identifier. Use "mock" for testing.
            Defaults to settings.orchestrator_model.

    Returns:
        A ModelAdapter instance.
    """
    name = model_name or settings.orchestrator_model
    if name == "mock":
        return MockAdapter()
    return OllamaAdapter(model_name=name)
