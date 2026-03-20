"""Generate a summary report from evaluation results.

Usage:
    python -m eval.scripts.report eval/results/eval_1234.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_results(path: Path) -> list[dict[str, Any]]:
    """Load evaluation results from JSONL.

    Args:
        path: Path to results file.

    Returns:
        List of result dicts.
    """
    results: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def compute_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute aggregate statistics from results.

    Args:
        results: List of result dicts.

    Returns:
        Nested stats dict by condition and category.
    """
    by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_condition_category: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

    for r in results:
        cond = r["condition"]
        by_condition[cond].append(r)

        # Infer category from task_id or from the task data
        task_id = r.get("task_id", "")
        # Try to get category from the question content (heuristic)
        by_condition_category[cond]["all"].append(r)

    stats: dict[str, Any] = {"conditions": {}, "total_tasks": 0}

    for cond, cond_results in sorted(by_condition.items()):
        n = len(cond_results)
        correct = sum(1 for r in cond_results if r.get("correctness", 0) >= 0.5)
        exec_ok = sum(
            1 for r in cond_results
            if r.get("execution", {}).get("exit_code") == 0
        )
        avg_steps = sum(r.get("steps", 1) for r in cond_results) / max(n, 1)
        avg_tokens = sum(r.get("context_tokens", 0) for r in cond_results) / max(n, 1)
        avg_latency = sum(r.get("total_latency_ms", 0) for r in cond_results) / max(n, 1)
        avg_retrieval = sum(r.get("retrieval_latency_ms", 0) for r in cond_results) / max(n, 1)
        avg_exec = sum(r.get("execution_latency_ms", 0) for r in cond_results) / max(n, 1)

        avg_correctness = sum(r.get("correctness", 0) for r in cond_results) / max(n, 1)

        stats["conditions"][cond] = {
            "n": n,
            "correct": correct,
            "correct_pct": round(correct / max(n, 1) * 100, 1),
            "exec_ok": exec_ok,
            "exec_ok_pct": round(exec_ok / max(n, 1) * 100, 1),
            "avg_correctness": round(avg_correctness, 3),
            "avg_steps": round(avg_steps, 1),
            "avg_tokens": round(avg_tokens, 0),
            "avg_latency_ms": round(avg_latency, 0),
            "avg_retrieval_ms": round(avg_retrieval, 0),
            "avg_exec_ms": round(avg_exec, 0),
        }

    stats["total_tasks"] = len(set(r.get("task_id") for r in results))
    return stats


def print_report(stats: dict[str, Any], results: list[dict[str, Any]]) -> None:
    """Print a formatted report to stdout.

    Args:
        stats: Aggregate statistics.
        results: Raw result dicts (for per-task details).
    """
    print("=" * 70)
    print("  BUMBLEBEE EVALUATION REPORT")
    print("=" * 70)
    print(f"\nTotal unique tasks: {stats['total_tasks']}")
    print()

    # Summary table
    header = f"{'Condition':<15} {'Correct':>10} {'Exec OK':>10} {'Avg Score':>10} {'Avg Tokens':>11} {'Avg ms':>8}"
    print(header)
    print("-" * len(header))

    for cond, s in sorted(stats["conditions"].items()):
        print(
            f"{cond:<15} "
            f"{s['correct']:>3}/{s['n']:<3} ({s['correct_pct']:>4}%) "
            f"{s['exec_ok']:>3}/{s['n']:<3} ({s['exec_ok_pct']:>4}%) "
            f"{s['avg_correctness']:>10.3f} "
            f"{s['avg_tokens']:>11.0f} "
            f"{s['avg_latency_ms']:>8.0f}"
        )

    # Per-task comparison
    print(f"\n{'Task':<12} ", end="")
    conditions = sorted(stats["conditions"].keys())
    for cond in conditions:
        print(f"{'| ' + cond:>18} ", end="")
    print()
    print("-" * (12 + 19 * len(conditions)))

    # Group results by task
    by_task: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in results:
        by_task[r["task_id"]][r["condition"]] = r

    for task_id in sorted(by_task.keys()):
        print(f"{task_id:<12} ", end="")
        for cond in conditions:
            r = by_task[task_id].get(cond)
            if r:
                score = r.get("correctness", 0)
                marker = "PASS" if score >= 0.5 else "FAIL"
                print(f"| {marker:>4} ({score:.1f}) ", end="")
            else:
                print("|       —     ", end="")
        print()

    # Failures detail
    failures = [r for r in results if r.get("correctness", 0) < 0.5]
    if failures:
        print(f"\n{'='*70}")
        print(f"  FAILURES ({len(failures)})")
        print(f"{'='*70}")
        for r in sorted(failures, key=lambda x: (x["condition"], x["task_id"])):
            print(f"\n  {r['task_id']} [{r['condition']}]")
            print(f"    Question: {r['question'][:80]}")
            error = r.get("execution", {}).get("error") or r.get("execution", {}).get("stderr", "")[:100]
            if error:
                print(f"    Error: {error[:100]}")
            print(f"    Expected: {json.dumps(r.get('gold_answer'))[:80]}")
            print(f"    Got:      {json.dumps(r.get('actual_answer'))[:80]}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Generate evaluation report")
    parser.add_argument("results", type=str, help="Path to results JSONL file")
    parser.add_argument("--json", action="store_true", help="Output stats as JSON instead of text")
    args = parser.parse_args()

    path = Path(args.results)
    if not path.exists():
        print(f"Results file not found: {path}", file=sys.stderr)
        sys.exit(1)

    results = load_results(path)
    stats = compute_stats(results)

    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print_report(stats, results)


if __name__ == "__main__":
    main()
