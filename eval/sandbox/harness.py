"""Evaluation harness: runs all conditions against a task set and collects metrics.

Usage:
    python -m eval.sandbox.harness --tasks eval/tasks/sample_tasks.jsonl --repo test_repos/sample_app

This is the main orchestrator. For each task, it:
1. Builds context using each retrieval condition (none, file_rag, graph_rag)
2. Sends context + question to the model
3. Extracts executable code from the model response
4. Runs the code in the sandbox
5. Scores the result against the gold answer
6. Records all metrics to a JSONL results file
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eval.sandbox.executor import ExecutionResult, execute_code
from eval.sandbox.loader import LOADER_SETUP
from eval.sandbox.retrieval.file_rag import build_file_context
from eval.sandbox.scorer import score

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"

# Conditions to evaluate
CONDITIONS = ["no_retrieval", "file_rag", "graph_rag", "agent"]

# Prompt template for the model
TASK_PROMPT_TEMPLATE = """\
You are answering a question about a Python codebase. You have access to an execution
environment where you can run Python code. The codebase is on sys.path, so you can
import its modules directly.

{context_section}

## Question

{question}

## Instructions

Write Python code that answers the question by importing and calling functions from the codebase.

You have a helper function `load_module(path)` that loads any Python file by relative path.
Example: `math_helpers = load_module('utils/math_helpers.py')`

Your code MUST either:
- Define a function called `answer()` that returns the answer, OR
- Assign the answer to a variable called `__result__`

Output ONLY the Python code block. No explanations.

```python
"""


def _build_prompt(question: str, context: str) -> str:
    """Build the full prompt for the model.

    Args:
        question: The task question.
        context: Retrieved context (empty string for no_retrieval condition).

    Returns:
        Complete prompt string.
    """
    if context:
        context_section = f"## Codebase Context\n\n{context}"
    else:
        context_section = (
            "No context provided. You must explore the codebase by importing modules "
            "and inspecting their contents."
        )

    return TASK_PROMPT_TEMPLATE.format(
        context_section=context_section,
        question=question,
    )


def _extract_code(model_response: str) -> str:
    """Extract Python code from a model response.

    Looks for code in markdown fences, or treats the entire response as code.

    Args:
        model_response: Raw model output.

    Returns:
        Extracted Python code string.
    """
    # Try markdown code block
    fenced = re.search(r"```(?:python)?\s*\n(.*?)```", model_response, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()

    # If the response looks like code (starts with import/def/from), use it directly
    stripped = model_response.strip()
    if stripped and (
        stripped.startswith("import ")
        or stripped.startswith("from ")
        or stripped.startswith("def ")
        or stripped.startswith("__result__")
    ):
        return stripped

    return stripped


@dataclass
class TaskResult:
    """Result of evaluating one task under one condition."""

    task_id: str
    condition: str
    question: str
    context_tokens: int  # approximate, from context length
    model_response: str
    extracted_code: str
    execution: dict[str, Any]
    gold_answer: Any
    actual_answer: Any
    correctness: float
    validation: str
    steps: int  # number of model calls (1 for now, extensible for agentic loop)
    total_latency_ms: float
    retrieval_latency_ms: float
    execution_latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSONL output."""
        return {
            "task_id": self.task_id,
            "condition": self.condition,
            "question": self.question,
            "context_tokens": self.context_tokens,
            "model_response": self.model_response,
            "extracted_code": self.extracted_code,
            "execution": self.execution,
            "gold_answer": self.gold_answer,
            "actual_answer": self.actual_answer,
            "correctness": self.correctness,
            "validation": self.validation,
            "steps": self.steps,
            "total_latency_ms": self.total_latency_ms,
            "retrieval_latency_ms": self.retrieval_latency_ms,
            "execution_latency_ms": self.execution_latency_ms,
        }


def _call_model(prompt: str, model_name: str) -> str:
    """Call the model and return its response text.

    Uses Ollama's HTTP API directly to avoid FastAPI dependency.

    Args:
        prompt: Full prompt string.
        model_name: Ollama model name.

    Returns:
        Model response text.
    """
    import httpx

    response = httpx.post(
        "http://localhost:11434/api/generate",
        json={
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 2048},
        },
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json().get("response", "")


def _run_agent_task(
    task: dict[str, Any],
    repo_path: Path,
    model_name: str,
) -> TaskResult:
    """Run a task using the agent condition (multi-turn tool-use loop).

    Args:
        task: Task dict from the JSONL file.
        repo_path: Path to the target repository.
        model_name: Ollama model name.

    Returns:
        TaskResult with all metrics.
    """
    from eval.sandbox.agent_condition import run_agent

    task_id = task["id"]
    question = task["question"]
    gold_answer = task.get("gold_answer")
    validation = task.get("validation", "exact_match")
    setup_code = task.get("setup_code", "")

    total_start = time.perf_counter()

    agent_result = run_agent(question, repo_path, model_name, setup_code=setup_code)

    total_ms = (time.perf_counter() - total_start) * 1000

    actual_answer = agent_result.answer
    correctness = 0.0
    if gold_answer is not None and actual_answer is not None:
        correctness = score(actual_answer, gold_answer, validation)
    elif gold_answer is None and actual_answer is not None:
        correctness = 0.5

    # Build execution dict from agent's last execution
    execution = agent_result.final_execution or {}
    if agent_result.error:
        execution["error"] = agent_result.error

    return TaskResult(
        task_id=task_id,
        condition="agent",
        question=question,
        context_tokens=agent_result.total_tokens,
        model_response="\n---\n".join(agent_result.model_responses),
        extracted_code=json.dumps(agent_result.tool_calls, indent=2),
        execution=execution,
        gold_answer=gold_answer,
        actual_answer=actual_answer,
        correctness=correctness,
        validation=validation,
        steps=agent_result.steps,
        total_latency_ms=round(total_ms, 1),
        retrieval_latency_ms=0.0,  # agent does its own retrieval within the loop
        execution_latency_ms=0.0,
    )


def run_task(
    task: dict[str, Any],
    condition: str,
    repo_path: Path,
    model_name: str,
) -> TaskResult:
    """Run a single task under a single condition.

    Args:
        task: Task dict from the JSONL file.
        condition: One of 'no_retrieval', 'file_rag', 'graph_rag', 'agent'.
        repo_path: Path to the target repository.
        model_name: Ollama model name.

    Returns:
        TaskResult with all metrics.
    """
    # Agent condition has its own loop — delegate entirely
    if condition == "agent":
        return _run_agent_task(task, repo_path, model_name)

    task_id = task["id"]
    question = task["question"]
    gold_answer = task.get("gold_answer")
    validation = task.get("validation", "exact_match")
    setup_code = task.get("setup_code", "")

    total_start = time.perf_counter()

    # Step 1: Retrieve context
    retrieval_start = time.perf_counter()
    context = ""

    if condition == "file_rag":
        context = build_file_context(question, repo_path)
    elif condition == "graph_rag":
        try:
            from eval.sandbox.retrieval.graph_rag import build_graph_context
            context = build_graph_context(question)
        except Exception as exc:
            logger.warning("Graph RAG retrieval failed for task %s: %s", task_id, exc)
            context = f"Graph retrieval error: {exc}"

    retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

    # Step 2: Build prompt and call model
    prompt = _build_prompt(question, context)
    context_tokens = len(prompt) // 4  # rough approximation

    try:
        model_response = _call_model(prompt, model_name)
    except Exception as exc:
        logger.error("Model call failed for task %s: %s", task_id, exc)
        total_ms = (time.perf_counter() - total_start) * 1000
        return TaskResult(
            task_id=task_id,
            condition=condition,
            question=question,
            context_tokens=context_tokens,
            model_response="",
            extracted_code="",
            execution={"error": str(exc)},
            gold_answer=gold_answer,
            actual_answer=None,
            correctness=0.0,
            validation=validation,
            steps=1,
            total_latency_ms=round(total_ms, 1),
            retrieval_latency_ms=round(retrieval_ms, 1),
            execution_latency_ms=0.0,
        )

    # Step 3: Extract and execute code
    extracted_code = _extract_code(model_response)

    # Prepend loader helper and any setup code
    parts = [LOADER_SETUP]
    if setup_code:
        parts.append(setup_code)
    parts.append(extracted_code)
    full_code = "\n\n".join(parts)

    exec_result = execute_code(full_code, repo_path)

    # Step 4: Score
    actual_answer = exec_result.return_value
    correctness = 0.0
    if gold_answer is not None and actual_answer is not None:
        correctness = score(actual_answer, gold_answer, validation)
    elif gold_answer is None and exec_result.succeeded():
        # No gold answer but code ran successfully — partial credit
        correctness = 0.5

    total_ms = (time.perf_counter() - total_start) * 1000

    return TaskResult(
        task_id=task_id,
        condition=condition,
        question=question,
        context_tokens=context_tokens,
        model_response=model_response,
        extracted_code=extracted_code,
        execution=exec_result.to_dict(),
        gold_answer=gold_answer,
        actual_answer=actual_answer,
        correctness=correctness,
        validation=validation,
        steps=1,
        total_latency_ms=round(total_ms, 1),
        retrieval_latency_ms=round(retrieval_ms, 1),
        execution_latency_ms=round(exec_result.duration_ms, 1),
    )


def run_eval(
    tasks_path: Path,
    repo_path: Path,
    model_name: str,
    conditions: list[str] | None = None,
    output_path: Path | None = None,
) -> list[TaskResult]:
    """Run the full evaluation: all tasks × all conditions.

    Args:
        tasks_path: Path to tasks JSONL file.
        repo_path: Path to the target repository.
        model_name: Ollama model name.
        conditions: Which conditions to run. Defaults to all.
        output_path: Path to write results JSONL. Defaults to results dir.

    Returns:
        List of all TaskResults.
    """
    conditions = conditions or CONDITIONS

    # Load tasks
    tasks: list[dict[str, Any]] = []
    with open(tasks_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))

    print(f"Loaded {len(tasks)} tasks, running {len(conditions)} conditions")

    # Prepare output
    if output_path is None:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = RESULTS_DIR / f"eval_{int(time.time())}.jsonl"

    all_results: list[TaskResult] = []

    for i, task in enumerate(tasks):
        for condition in conditions:
            task_id = task["id"]
            print(f"  [{i+1}/{len(tasks)}] {task_id} | {condition}", end=" ... ", flush=True)

            result = run_task(task, condition, repo_path, model_name)
            all_results.append(result)

            status = "PASS" if result.correctness >= 0.5 else "FAIL"
            print(f"{status} (score={result.correctness:.1f}, {result.total_latency_ms:.0f}ms)")

            # Append to JSONL incrementally
            with open(output_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result.to_dict()) + "\n")

    # Print summary
    print(f"\nResults written to {output_path}")
    _print_summary(all_results)

    return all_results


def _print_summary(results: list[TaskResult]) -> None:
    """Print a summary table of results by condition.

    Args:
        results: List of all task results.
    """
    from collections import defaultdict

    by_condition: dict[str, list[TaskResult]] = defaultdict(list)
    for r in results:
        by_condition[r.condition].append(r)

    print(f"\n{'Condition':<15} {'Correct':>8} {'Exec OK':>8} {'Avg Steps':>10} {'Avg Tokens':>11} {'Avg ms':>8}")
    print("-" * 65)

    for condition in CONDITIONS:
        cond_results = by_condition.get(condition, [])
        if not cond_results:
            continue

        n = len(cond_results)
        correct = sum(1 for r in cond_results if r.correctness >= 0.5)
        exec_ok = sum(1 for r in cond_results if r.execution.get("exit_code") == 0)
        avg_steps = sum(r.steps for r in cond_results) / n
        avg_tokens = sum(r.context_tokens for r in cond_results) / n
        avg_ms = sum(r.total_latency_ms for r in cond_results) / n

        print(f"{condition:<15} {correct:>3}/{n:<4} {exec_ok:>3}/{n:<4} {avg_steps:>10.1f} {avg_tokens:>11.0f} {avg_ms:>8.0f}")


def main() -> None:
    """CLI entry point for the evaluation harness."""
    parser = argparse.ArgumentParser(description="Run NL-to-code evaluation")
    parser.add_argument("--tasks", type=str, required=True, help="Path to tasks JSONL")
    parser.add_argument("--repo", type=str, required=True, help="Path to target repository")
    parser.add_argument("--model", type=str, default="mistral:latest", help="Ollama model name")
    parser.add_argument("--conditions", type=str, nargs="*", default=None, help="Conditions to run")
    parser.add_argument("--output", type=str, default=None, help="Output JSONL path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    run_eval(
        tasks_path=Path(args.tasks),
        repo_path=Path(args.repo),
        model_name=args.model,
        conditions=args.conditions,
        output_path=Path(args.output) if args.output else None,
    )


if __name__ == "__main__":
    main()
