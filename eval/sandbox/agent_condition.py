"""Agent condition: a tool-use loop that simulates a real coding agent.

The model gets NO pre-retrieved context. Instead, it gets tools to explore
the repo itself: list files, read files, search for text, and execute code.
This is how real coding agents (Cursor, aider, Claude Code) work — they
iterate through tool calls until they have enough context to write and
execute code that answers the question.

The agent loop:
1. Model receives the question + tool definitions
2. Model calls tools (list_files, read_file, search, execute_code)
3. Tool results are appended to the conversation
4. Repeat until the model produces a final answer or hits max rounds

This measures the full agent experience: retrieval quality, planning,
error recovery, and token efficiency — all in one condition.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from eval.sandbox.executor import execute_code
from eval.sandbox.loader import LOADER_SETUP

logger = logging.getLogger(__name__)

MAX_AGENT_ROUNDS = 10
AGENT_TIMEOUT = 180.0  # total seconds for the full agent loop

# Tools available to the agent
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "List files and directories at a path relative to the repo root. "
                "Returns a list of entries. Use this to explore the codebase structure."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path. Use '.' for root.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the contents of a file relative to the repo root. "
                "Use this to inspect source code and understand function signatures."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative file path (e.g., 'utils/math_helpers.py').",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": (
                "Search for a text pattern across all Python files in the repo. "
                "Returns matching lines with file paths and line numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Text or regex pattern to search for.",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": (
                "Execute Python code in a sandbox with the repo on sys.path. "
                "A helper function load_module(path) is available to import any file. "
                "Example: `mod = load_module('utils/math_helpers.py')`. "
                "To return an answer, assign to __result__ or define answer()."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute.",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_answer",
            "description": (
                "Submit your final answer to the question. Call this when you have "
                "determined the answer through code execution or reasoning."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {
                        "description": "The answer to the question. Can be any JSON value.",
                    },
                },
                "required": ["answer"],
            },
        },
    },
]

AGENT_SYSTEM_PROMPT = """\
You are a coding agent answering questions about a Python codebase. You have tools to \
explore the repo, read files, search for code, and execute Python.

Your goal: find and run the right code to answer the question, then call submit_answer \
with the result.

Strategy:
1. List files to understand the repo structure
2. Read relevant files to find the right functions
3. Execute code to compute the answer
4. Submit the answer

Be efficient — don't read every file. Use search to find relevant code quickly.\
"""


def _execute_agent_tool(
    tool_name: str,
    arguments: dict[str, Any],
    repo_path: Path,
) -> str:
    """Execute an agent tool and return the result as a string.

    Args:
        tool_name: Name of the tool to execute.
        arguments: Tool arguments.
        repo_path: Path to the target repository.

    Returns:
        String result for the model's context.
    """
    if tool_name == "list_files":
        rel_path = arguments.get("path", ".")
        target = (repo_path / rel_path).resolve()
        # Safety: stay within repo
        if not str(target).startswith(str(repo_path.resolve())):
            return "Error: path outside repository"
        if not target.is_dir():
            return f"Error: not a directory: {rel_path}"
        try:
            entries = sorted(os.listdir(target))
            labeled: list[str] = []
            for e in entries:
                full = target / e
                if e.startswith(".") or e == "__pycache__":
                    continue
                suffix = "/" if full.is_dir() else ""
                labeled.append(f"{e}{suffix}")
            return "\n".join(labeled) if labeled else "(empty directory)"
        except OSError as exc:
            return f"Error: {exc}"

    elif tool_name == "read_file":
        rel_path = arguments.get("path", "")
        target = (repo_path / rel_path).resolve()
        if not str(target).startswith(str(repo_path.resolve())):
            return "Error: path outside repository"
        if not target.is_file():
            return f"Error: file not found: {rel_path}"
        try:
            content = target.read_text(encoding="utf-8")
            # Truncate very large files
            if len(content) > 8000:
                content = content[:8000] + "\n... (truncated)"
            return content
        except (OSError, UnicodeDecodeError) as exc:
            return f"Error: {exc}"

    elif tool_name == "search":
        pattern = arguments.get("pattern", "")
        if not pattern:
            return "Error: empty search pattern"
        results: list[str] = []
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            # Fall back to literal search
            compiled = re.compile(re.escape(pattern), re.IGNORECASE)
        for py_file in sorted(repo_path.rglob("*.py")):
            rel = py_file.relative_to(repo_path)
            parts = rel.parts
            if any(p.startswith(".") or p == "__pycache__" for p in parts):
                continue
            try:
                lines = py_file.read_text(encoding="utf-8").splitlines()
                for i, line in enumerate(lines, 1):
                    if compiled.search(line):
                        results.append(f"{rel}:{i}: {line.strip()}")
            except (OSError, UnicodeDecodeError):
                continue
            if len(results) >= 30:
                break
        return "\n".join(results) if results else "No matches found."

    elif tool_name == "execute_code":
        code = arguments.get("code", "")
        if not code:
            return "Error: no code provided"
        full_code = LOADER_SETUP + "\n\n" + code
        result = execute_code(full_code, repo_path)
        parts: list[str] = []
        if result.stdout:
            parts.append(f"stdout:\n{result.stdout}")
        if result.stderr:
            parts.append(f"stderr:\n{result.stderr}")
        if result.return_value is not None:
            parts.append(f"return_value: {json.dumps(result.return_value)}")
        if result.error:
            parts.append(f"error: {result.error}")
        if not parts:
            parts.append("(no output)")
        return "\n".join(parts)

    elif tool_name == "submit_answer":
        # This is handled by the caller, not executed
        return "Answer submitted."

    return f"Error: unknown tool: {tool_name}"


def _call_model_chat(
    messages: list[dict[str, Any]],
    model_name: str,
) -> dict[str, Any]:
    """Call Ollama's chat endpoint with tool definitions.

    Args:
        messages: Conversation messages.
        model_name: Ollama model name.

    Returns:
        Response dict from Ollama.
    """
    response = httpx.post(
        "http://localhost:11434/api/chat",
        json={
            "model": model_name,
            "messages": messages,
            "tools": AGENT_TOOLS,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 2048},
        },
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()


@dataclass
class AgentResult:
    """Result of running the agent condition on a task."""

    answer: Any
    steps: int
    total_tokens: int
    tool_calls: list[dict[str, str]]
    model_responses: list[str]
    execution_results: list[dict[str, Any]]
    final_execution: dict[str, Any] | None
    error: str | None


def run_agent(
    question: str,
    repo_path: Path,
    model_name: str,
    setup_code: str = "",
) -> AgentResult:
    """Run the agent condition: multi-turn tool-use loop.

    Args:
        question: Natural language question.
        repo_path: Path to the target repository.
        model_name: Ollama model name.
        setup_code: Optional setup code to prepend to executions.

    Returns:
        AgentResult with the final answer and all metrics.
    """
    repo_path = Path(repo_path).resolve()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_call_log: list[dict[str, str]] = []
    model_responses: list[str] = []
    execution_results: list[dict[str, Any]] = []
    final_answer: Any = None
    final_execution: dict[str, Any] | None = None
    steps = 0
    total_tokens = 0
    deadline = time.perf_counter() + AGENT_TIMEOUT

    for round_num in range(MAX_AGENT_ROUNDS):
        if time.perf_counter() > deadline:
            return AgentResult(
                answer=None,
                steps=steps,
                total_tokens=total_tokens,
                tool_calls=tool_call_log,
                model_responses=model_responses,
                execution_results=execution_results,
                final_execution=final_execution,
                error=f"Agent timed out after {AGENT_TIMEOUT}s",
            )

        try:
            response = _call_model_chat(messages, model_name)
        except Exception as exc:
            return AgentResult(
                answer=None,
                steps=steps,
                total_tokens=total_tokens,
                tool_calls=tool_call_log,
                model_responses=model_responses,
                execution_results=execution_results,
                final_execution=final_execution,
                error=f"Model call failed: {exc}",
            )

        steps += 1

        # Track tokens
        if "eval_count" in response:
            total_tokens += response.get("prompt_eval_count", 0) + response.get("eval_count", 0)

        message = response.get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])

        if content:
            model_responses.append(content)

        # No tool calls — model is done (or confused)
        if not tool_calls:
            # Try to extract an answer from the text response
            if content:
                # Check if there's a JSON value in the response
                try:
                    final_answer = json.loads(content)
                except (json.JSONDecodeError, ValueError):
                    final_answer = content.strip()
            break

        # Add assistant message to history
        messages.append(message)

        # Process tool calls
        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            arguments = func.get("arguments", {})

            tool_call_log.append({
                "round": str(round_num),
                "tool": tool_name,
                "arguments": json.dumps(arguments)[:200],
            })

            # Handle submit_answer specially
            if tool_name == "submit_answer":
                final_answer = arguments.get("answer")
                # Add the tool response and break
                messages.append({
                    "role": "tool",
                    "content": "Answer submitted.",
                })
                return AgentResult(
                    answer=final_answer,
                    steps=steps,
                    total_tokens=total_tokens,
                    tool_calls=tool_call_log,
                    model_responses=model_responses,
                    execution_results=execution_results,
                    final_execution=final_execution,
                    error=None,
                )

            # Execute the tool
            tool_result = _execute_agent_tool(tool_name, arguments, repo_path)

            # Track execution results
            if tool_name == "execute_code":
                exec_record = {
                    "round": round_num,
                    "code": arguments.get("code", "")[:500],
                    "result": tool_result[:500],
                }
                execution_results.append(exec_record)

                # Check if execution produced a return value
                if "return_value:" in tool_result:
                    rv_line = [l for l in tool_result.split("\n") if l.startswith("return_value:")][0]
                    rv_str = rv_line.split("return_value:", 1)[1].strip()
                    try:
                        final_execution = {"return_value": json.loads(rv_str)}
                    except (json.JSONDecodeError, ValueError):
                        final_execution = {"return_value": rv_str}

            # Add tool result to conversation
            messages.append({
                "role": "tool",
                "content": tool_result[:4000],  # Truncate large tool outputs
            })

    return AgentResult(
        answer=final_answer if final_answer is not None else (
            final_execution.get("return_value") if final_execution else None
        ),
        steps=steps,
        total_tokens=total_tokens,
        tool_calls=tool_call_log,
        model_responses=model_responses,
        execution_results=execution_results,
        final_execution=final_execution,
        error=None,
    )
