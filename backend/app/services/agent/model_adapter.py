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
                return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama HTTP error: %s %s", exc.response.status_code, exc.response.text)
            raise ModelAdapterError(f"Ollama returned status {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            logger.error("Ollama request error: %s", exc)
            raise ModelAdapterError(f"Cannot reach Ollama at {self.base_url}: {exc}") from exc

    async def stream_chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream responses from Ollama.

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
                        tool_calls = message.get("tool_calls")

                        if tool_calls:
                            for tc in tool_calls:
                                yield {
                                    "type": "tool_call",
                                    "name": tc.get("function", {}).get("name", ""),
                                    "arguments": tc.get("function", {}).get("arguments", {}),
                                }
                        elif message.get("content"):
                            yield {"type": "token", "content": message["content"]}

                        if chunk.get("done", False):
                            return
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama stream HTTP error: %s", exc.response.status_code)
            raise ModelAdapterError(f"Ollama returned status {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            logger.error("Ollama stream request error: %s", exc)
            raise ModelAdapterError(f"Cannot reach Ollama at {self.base_url}: {exc}") from exc


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
