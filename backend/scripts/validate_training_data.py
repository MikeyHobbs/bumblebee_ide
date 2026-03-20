"""Validate training data by running each Cypher query against the live graph.

Usage:
    uv run python -m scripts.validate_training_data
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph.client import get_graph, init_client  # noqa: E402

TRAINING_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "cypher_training.jsonl"


def main() -> None:
    """Validate all training queries against the live FalkorDB graph."""
    if not TRAINING_DATA_PATH.exists():
        print(f"Training data not found at {TRAINING_DATA_PATH}")
        sys.exit(1)

    init_client()
    graph = get_graph()

    records: list[dict[str, str]] = []
    with open(TRAINING_DATA_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    total = len(records)
    passed = 0
    failed = 0
    errors: list[tuple[str, str, str]] = []

    for rec in records:
        query_id = rec.get("id", "?")
        cypher = rec.get("cypher", "")
        nl = rec.get("nl", "")

        try:
            result = graph.query(cypher)
            row_count = len(result.result_set) if hasattr(result, "result_set") else 0
            print(f"  PASS  {query_id}: {nl[:50]:<50} ({row_count} rows)")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {query_id}: {nl[:50]:<50} -> {exc}")
            errors.append((query_id, nl, str(exc)))
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} passed, {failed}/{total} failed")

    if errors:
        print(f"\nFailed queries:")
        for qid, nl, err in errors:
            print(f"  {qid}: {nl}")
            print(f"    Error: {err}")
        sys.exit(1)
    else:
        print("\nAll queries valid!")


if __name__ == "__main__":
    main()
