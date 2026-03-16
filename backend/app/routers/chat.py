"""Chat router: SSE streaming chat with tool-use support (TICKET-502)."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.models.exceptions import ModelAdapterError
from app.services.cypher_agent import SYSTEM_PROMPT as CYPHER_SYSTEM_PROMPT
from app.services.model_adapter import get_adapter
from app.services.tool_executor import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])

# Maximum number of tool-use rounds before forcing a final answer
MAX_TOOL_ROUNDS = 5

ORCHESTRATOR_SYSTEM_PROMPT = """You are Bumblebee, an AI assistant for understanding and navigating codebases.
You have access to a graph database that models the codebase as nodes (Module, Class, Function, Variable, Statement, ControlFlow, Branch) and edges (DEFINES, CALLS, INHERITS, IMPORTS, ASSIGNS, MUTATES, READS, RETURNS, PASSES_TO, FEEDS, CONTAINS, NEXT).

Use the available tools to answer questions about the code. When you need to explore the graph, use query_graph with a Cypher query. For common analysis patterns, use the specialized tools (mutation_timeline, impact_analysis, get_logic_pack, read_file).

Always provide clear, concise answers. When showing code or graph results, format them readably.
"""


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    message: str = Field(..., description="User message text")
    model: str | None = Field(None, description="Model name to use. 'mock' for testing.")
    history: list[dict[str, Any]] | None = Field(None, description="Previous conversation messages")


class ToolResultRequest(BaseModel):
    """Request body for accepting a tool result from the frontend."""

    tool_call_id: str = Field(..., description="ID of the tool call this result is for")
    name: str = Field(..., description="Tool name")
    result: dict[str, Any] = Field(..., description="Tool execution result")
    model: str | None = Field(None, description="Model name to continue with")
    history: list[dict[str, Any]] = Field(..., description="Full conversation history including tool call")


def _sse_event(data: dict[str, Any]) -> str:
    """Format a dict as an SSE event line.

    Args:
        data: Event data to serialize.

    Returns:
        SSE-formatted string.
    """
    return f"data: {json.dumps(data)}\n\n"


async def _stream_chat_response(
    adapter_model: str | None,
    messages: list[dict[str, Any]],
) -> AsyncGenerator[str, None]:
    """Stream a full chat interaction including tool-use loops.

    Sends SSE events for tokens, tool calls, tool results, and done signal.

    Args:
        adapter_model: Model name for the adapter.
        messages: Full message history to send.

    Yields:
        SSE-formatted event strings.
    """
    adapter = get_adapter(adapter_model)
    current_messages = list(messages)
    tool_rounds = 0

    while tool_rounds < MAX_TOOL_ROUNDS:
        collected_content = ""
        tool_calls_batch: list[dict[str, Any]] = []

        try:
            async for chunk in adapter.stream_chat(current_messages, tools=TOOL_DEFINITIONS):
                chunk_type = chunk.get("type", "")

                if chunk_type == "token":
                    content = chunk.get("content", "")
                    collected_content += content
                    yield _sse_event({"type": "token", "content": content})

                elif chunk_type == "tool_call":
                    tool_calls_batch.append(chunk)

        except ModelAdapterError as exc:
            yield _sse_event({"type": "error", "content": str(exc)})
            yield _sse_event({"type": "done"})
            return

        # If no tool calls were made, we're done
        if not tool_calls_batch:
            break

        # Process tool calls
        # Add assistant message with tool calls to history
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": collected_content,
            "tool_calls": [
                {"function": {"name": tc["name"], "arguments": tc["arguments"]}}
                for tc in tool_calls_batch
            ],
        }
        current_messages.append(assistant_msg)

        for tc in tool_calls_batch:
            tool_name = tc["name"]
            tool_args = tc["arguments"]

            yield _sse_event({
                "type": "tool_call",
                "name": tool_name,
                "arguments": tool_args,
            })

            # Execute the tool
            tool_result = await execute_tool(tool_name, tool_args)

            yield _sse_event({
                "type": "tool_result",
                "name": tool_name,
                "result": tool_result,
            })

            # Add tool result to message history
            current_messages.append({
                "role": "tool",
                "content": json.dumps(tool_result),
            })

        tool_rounds += 1

    yield _sse_event({"type": "done"})


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """Main chat endpoint with SSE streaming.

    Accepts a user message, optional model selection, and conversation history.
    Streams back tokens, tool calls, tool results, and a done signal.

    Args:
        request: Chat request with message, model, and history.

    Returns:
        SSE streaming response.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": ORCHESTRATOR_SYSTEM_PROMPT},
    ]

    # Add conversation history if provided
    if request.history:
        messages.extend(request.history)

    # Add the new user message
    messages.append({"role": "user", "content": request.message})

    return StreamingResponse(
        _stream_chat_response(request.model, messages),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/tool-result")
async def chat_tool_result(request: ToolResultRequest) -> StreamingResponse:
    """Accept a tool result from the frontend and continue the conversation.

    This endpoint is used when the frontend executes a tool on the client side
    and needs to send the result back for the model to continue.

    Args:
        request: Tool result with conversation history.

    Returns:
        SSE streaming response continuing the conversation.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": ORCHESTRATOR_SYSTEM_PROMPT},
    ]
    messages.extend(request.history)

    # Add the tool result
    messages.append({
        "role": "tool",
        "content": json.dumps({"name": request.name, "result": request.result}),
    })

    return StreamingResponse(
        _stream_chat_response(request.model, messages),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/models")
async def list_models() -> dict[str, list[dict[str, str]]]:
    """List available LLM models.

    Queries Ollama for available models and always includes 'mock' for testing.

    Returns:
        Dict with 'models' key containing list of model info dicts.
    """
    models: list[dict[str, str]] = [
        {"name": "mock", "description": "Mock adapter for testing (no LLM needed)"},
    ]

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.ollama_host}/api/tags")
            response.raise_for_status()
            data = response.json()
            for model_info in data.get("models", []):
                name = model_info.get("name", "")
                if name:
                    models.append({
                        "name": name,
                        "description": f"Ollama model: {name}",
                    })
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("Could not fetch Ollama models: %s", exc)

    return {"models": models}
