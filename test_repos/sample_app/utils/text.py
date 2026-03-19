"""Text processing utilities."""

from __future__ import annotations

import re


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug.

    Lowercases the string, replaces spaces and special characters with hyphens,
    collapses consecutive hyphens, and strips leading/trailing hyphens.
    """
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


def truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len characters, appending '...' if truncated."""
    if len(text) <= max_len:
        return text
    if max_len < 4:
        return text[:max_len]
    return text[: max_len - 3] + "..."


def title_case(text: str) -> str:
    """Capitalize the first letter of each word in the text."""
    words = text.split()
    capitalized = []
    for word in words:
        if len(word) > 0:
            capitalized.append(word[0].upper() + word[1:])
    return " ".join(capitalized)


def count_words(text: str) -> int:
    """Count the number of whitespace-separated words in the text."""
    stripped = text.strip()
    if not stripped:
        return 0
    return len(stripped.split())
