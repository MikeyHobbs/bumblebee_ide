"""Export training data to formats suitable for fine-tuning.

Supports:
- Alpaca format (for Unsloth/QLoRA)
- Chat format (for Ollama fine-tuning)

Usage:
    uv run python -m scripts.export_for_finetuning --format alpaca --output data/train_alpaca.json
    uv run python -m scripts.export_for_finetuning --format chat --output data/train_chat.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph.schema_description import CYPHER_SYSTEM_PROMPT  # noqa: E402

TRAINING_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "cypher_training.jsonl"


def load_training_data() -> list[dict[str, str]]:
    """Load training records from JSONL file.

    Returns:
        List of training record dicts.
    """
    records: list[dict[str, str]] = []
    with open(TRAINING_DATA_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def to_alpaca(records: list[dict[str, str]]) -> list[dict[str, str]]:
    """Convert to Alpaca instruction format.

    Args:
        records: Training records.

    Returns:
        List of Alpaca-format dicts.
    """
    out: list[dict[str, str]] = []
    for rec in records:
        out.append({
            "instruction": CYPHER_SYSTEM_PROMPT,
            "input": rec["nl"],
            "output": rec["cypher"],
        })
    return out


def to_chat(records: list[dict[str, str]]) -> list[dict[str, list[dict[str, str]]]]:
    """Convert to OpenAI chat format.

    Args:
        records: Training records.

    Returns:
        List of chat-format conversation dicts.
    """
    out: list[dict[str, list[dict[str, str]]]] = []
    for rec in records:
        out.append({
            "messages": [
                {"role": "system", "content": CYPHER_SYSTEM_PROMPT},
                {"role": "user", "content": rec["nl"]},
                {"role": "assistant", "content": rec["cypher"]},
            ]
        })
    return out


def main() -> None:
    """Export training data in the requested format."""
    parser = argparse.ArgumentParser(description="Export training data for fine-tuning")
    parser.add_argument("--format", choices=["alpaca", "chat"], default="alpaca", help="Output format")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    args = parser.parse_args()

    if not TRAINING_DATA_PATH.exists():
        print(f"Training data not found at {TRAINING_DATA_PATH}")
        sys.exit(1)

    records = load_training_data()
    print(f"Loaded {len(records)} training examples")

    if args.format == "alpaca":
        data = to_alpaca(records)
        default_output = "data/train_alpaca.json"
    else:
        data = to_chat(records)
        default_output = "data/train_chat.json"

    output_path = Path(args.output) if args.output else Path(__file__).resolve().parents[1] / default_output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Exported {len(data)} examples to {output_path} ({args.format} format)")


if __name__ == "__main__":
    main()
