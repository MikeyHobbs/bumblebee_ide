"""Cypher evaluation router: compare NL-to-Cypher output across models (TICKET-NL2C)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.agent.cypher_agent import query_with_nl
from app.services.agent.model_adapter import OllamaAdapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cypher-eval", tags=["cypher-eval"])

EVAL_RESULTS_PATH = Path(__file__).resolve().parents[2] / "data" / "cypher_eval_results.jsonl"


class CompareRequest(BaseModel):
    """Request body for the compare endpoint."""

    question: str = Field(..., description="Natural language question about the codebase")
    model_a: str = Field(..., description="First model name (e.g. 'llama3.2:latest')")
    model_b: str = Field(..., description="Second model name (e.g. 'cypher-specialist')")


class RateRequest(BaseModel):
    """Request body for the rate endpoint."""

    eval_id: str = Field(..., description="ID of the evaluation to rate")
    winner: str = Field(..., description="Winner: 'a', 'b', 'tie', or 'both_bad'")
    notes: str = Field("", description="Optional notes about the rating")


class ModelResult(BaseModel):
    """Result from a single model's NL-to-Cypher attempt."""

    model: str
    cypher: str
    results: list[dict[str, Any]]
    row_count: int
    latency_ms: float
    error: str | None = None


class CompareResponse(BaseModel):
    """Response from the compare endpoint."""

    eval_id: str
    question: str
    model_a: ModelResult
    model_b: ModelResult


class RateResponse(BaseModel):
    """Response from the rate endpoint."""

    eval_id: str
    winner: str
    notes: str


class EvalStats(BaseModel):
    """Aggregate statistics for model evaluations."""

    total: int
    rated: int
    wins: dict[str, int]


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append a JSON record to a JSONL file.

    Args:
        path: Path to the JSONL file.
        record: Dict to serialize and append.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read all records from a JSONL file.

    Args:
        path: Path to the JSONL file.

    Returns:
        List of parsed dicts.
    """
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


async def _run_model(question: str, model_name: str) -> ModelResult:
    """Run a single model against a question and capture timing.

    Args:
        question: Natural language question.
        model_name: Ollama model name.

    Returns:
        ModelResult with cypher, results, latency, and any error.
    """
    adapter = OllamaAdapter(model_name=model_name)
    start = time.perf_counter()
    result = await query_with_nl(question, adapter)
    elapsed_ms = (time.perf_counter() - start) * 1000

    return ModelResult(
        model=model_name,
        cypher=result.get("cypher", ""),
        results=result.get("results", []),
        row_count=result.get("row_count", 0),
        latency_ms=round(elapsed_ms, 1),
        error=result.get("error"),
    )


@router.post("/compare", response_model=CompareResponse)
async def compare(request: CompareRequest) -> CompareResponse:
    """Compare two models' NL-to-Cypher output for a given question.

    Args:
        request: Compare request with question and two model names.

    Returns:
        Side-by-side results from both models.
    """
    result_a = await _run_model(request.question, request.model_a)
    result_b = await _run_model(request.question, request.model_b)

    eval_id = str(uuid.uuid4())

    # Persist the comparison
    record = {
        "eval_id": eval_id,
        "question": request.question,
        "model_a": result_a.model_dump(),
        "model_b": result_b.model_dump(),
        "rating": None,
    }
    _append_jsonl(EVAL_RESULTS_PATH, record)

    return CompareResponse(
        eval_id=eval_id,
        question=request.question,
        model_a=result_a,
        model_b=result_b,
    )


@router.post("/rate", response_model=RateResponse)
async def rate(request: RateRequest) -> RateResponse:
    """Rate the winner of a comparison.

    Args:
        request: Rating request with eval_id and winner.

    Returns:
        Confirmation of the rating.

    Raises:
        HTTPException: If eval_id not found or winner is invalid.
    """
    valid_winners = {"a", "b", "tie", "both_bad"}
    if request.winner not in valid_winners:
        raise HTTPException(status_code=400, detail=f"winner must be one of: {valid_winners}")

    records = _read_jsonl(EVAL_RESULTS_PATH)
    found = False
    for rec in records:
        if rec.get("eval_id") == request.eval_id:
            rec["rating"] = {"winner": request.winner, "notes": request.notes}
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Evaluation {request.eval_id} not found")

    # Rewrite the file with the updated record
    EVAL_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVAL_RESULTS_PATH, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    return RateResponse(eval_id=request.eval_id, winner=request.winner, notes=request.notes)


@router.get("/history")
async def history(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """Get evaluation history.

    Args:
        limit: Maximum number of records to return.
        offset: Number of records to skip.

    Returns:
        Dict with 'items' list and 'total' count.
    """
    records = _read_jsonl(EVAL_RESULTS_PATH)
    # Most recent first
    records.reverse()
    total = len(records)
    items = records[offset : offset + limit]
    return {"items": items, "total": total}


@router.get("/stats", response_model=EvalStats)
async def stats() -> EvalStats:
    """Get aggregate evaluation statistics.

    Returns:
        Stats including total evals, rated count, and win counts per model.
    """
    records = _read_jsonl(EVAL_RESULTS_PATH)
    total = len(records)
    rated = 0
    wins: dict[str, int] = {}

    for rec in records:
        rating = rec.get("rating")
        if not rating:
            continue
        rated += 1
        winner = rating.get("winner", "")
        if winner == "a":
            model_name = rec.get("model_a", {}).get("model", "unknown")
            wins[model_name] = wins.get(model_name, 0) + 1
        elif winner == "b":
            model_name = rec.get("model_b", {}).get("model", "unknown")
            wins[model_name] = wins.get(model_name, 0) + 1
        elif winner in ("tie", "both_bad"):
            wins[winner] = wins.get(winner, 0) + 1

    return EvalStats(total=total, rated=rated, wins=wins)
