"""File RAG retrieval: standard embedding-based code retrieval baseline.

This is the standard coding agent condition. Given a question, it:
1. Chunks all source files in the target repo
2. Embeds the question using the same embedding model
3. Retrieves top-k most similar chunks
4. Returns them as context for the LLM

This intentionally uses a simple, well-known approach (no tricks) so
the comparison against Graph RAG is fair. A real coding agent would
do something similar — the point is that flat text retrieval lacks
structural understanding.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def _chunk_file(file_path: Path, chunk_size: int = 60, overlap: int = 10) -> list[dict[str, Any]]:
    """Split a Python file into overlapping line-based chunks.

    Args:
        file_path: Path to the source file.
        chunk_size: Number of lines per chunk.
        overlap: Number of overlapping lines between chunks.

    Returns:
        List of chunk dicts with content, file path, and line range.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    lines = content.splitlines()
    if not lines:
        return []

    chunks: list[dict[str, Any]] = []
    step = max(chunk_size - overlap, 1)

    for start in range(0, len(lines), step):
        end = min(start + chunk_size, len(lines))
        chunk_lines = lines[start:end]
        chunk_text = "\n".join(chunk_lines)

        if chunk_text.strip():
            chunks.append({
                "content": chunk_text,
                "file": str(file_path),
                "start_line": start + 1,
                "end_line": end,
                "id": hashlib.md5(f"{file_path}:{start}".encode()).hexdigest(),
            })

        if end >= len(lines):
            break

    return chunks


def index_repository(repo_path: str | Path) -> list[dict[str, Any]]:
    """Index all Python files in a repository into chunks.

    Args:
        repo_path: Root path of the repository.

    Returns:
        List of all chunk dicts.
    """
    repo_path = Path(repo_path).resolve()
    all_chunks: list[dict[str, Any]] = []

    for py_file in sorted(repo_path.rglob("*.py")):
        # Skip __pycache__, .venv, etc.
        parts = py_file.relative_to(repo_path).parts
        if any(p.startswith(".") or p == "__pycache__" or p == "node_modules" for p in parts):
            continue
        chunks = _chunk_file(py_file)
        # Store relative path for readability
        for chunk in chunks:
            chunk["file"] = str(py_file.relative_to(repo_path))
        all_chunks.extend(chunks)

    return all_chunks


def _keyword_score(query: str, text: str) -> float:
    """Simple keyword-overlap scoring as a baseline retriever.

    In a real experiment you'd use an embedding model (e.g., nomic-embed-code).
    This keyword scorer is a placeholder that still produces a fair baseline
    because it simulates what a grep-based agent would find.

    Args:
        query: Search query.
        text: Document text.

    Returns:
        Score between 0 and 1 based on keyword overlap.
    """
    query_tokens = set(re.findall(r"\w+", query.lower()))
    text_tokens = set(re.findall(r"\w+", text.lower()))

    if not query_tokens:
        return 0.0

    # Jaccard-ish: intersection over query length
    overlap = query_tokens & text_tokens
    return len(overlap) / len(query_tokens)


def retrieve_chunks(
    question: str,
    chunks: list[dict[str, Any]],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Retrieve the most relevant chunks for a question.

    Uses keyword scoring as a baseline. Replace with embedding-based
    retrieval for a stronger baseline in the actual experiment.

    Args:
        question: Natural language question.
        chunks: Pre-indexed chunks from index_repository().
        top_k: Number of chunks to return.

    Returns:
        Top-k chunks sorted by relevance score.
    """
    scored = []
    for chunk in chunks:
        score = _keyword_score(question, chunk["content"])
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]


def serialize_chunks(chunks: list[dict[str, Any]]) -> str:
    """Serialize retrieved chunks into context text for the LLM.

    Args:
        chunks: Retrieved chunk dicts.

    Returns:
        Formatted context string.
    """
    if not chunks:
        return "No relevant code found."

    sections: list[str] = []
    for chunk in chunks:
        header = f"# {chunk['file']} (lines {chunk['start_line']}-{chunk['end_line']})"
        sections.append(f"{header}\n```python\n{chunk['content']}\n```")

    return "\n\n".join(sections)


def build_file_context(question: str, repo_path: str | Path, top_k: int = 5) -> str:
    """Full pipeline: question → chunk retrieval → serialized context.

    This is the main entry point for the File RAG condition.

    Args:
        question: Natural language question about the codebase.
        repo_path: Path to the target repository.
        top_k: Number of chunks to retrieve.

    Returns:
        Serialized context string ready to prepend to the LLM prompt.
    """
    chunks = index_repository(repo_path)
    relevant = retrieve_chunks(question, chunks, top_k=top_k)
    return serialize_chunks(relevant)
