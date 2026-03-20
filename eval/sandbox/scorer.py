"""Scoring functions for comparing model answers against gold answers."""

from __future__ import annotations

import json
from typing import Any


def normalize_value(value: Any) -> Any:
    """Normalize a value for comparison: strip strings, sort dicts.

    Args:
        value: Any JSON-serializable value.

    Returns:
        Normalized value.
    """
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, dict):
        return {k: normalize_value(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [normalize_value(v) for v in value]
    return value


def score_exact_match(actual: Any, expected: Any) -> float:
    """Score 1.0 if actual matches expected exactly (after normalization).

    Args:
        actual: Model's answer.
        expected: Gold answer.

    Returns:
        1.0 or 0.0.
    """
    return 1.0 if normalize_value(actual) == normalize_value(expected) else 0.0


def score_contains(actual: Any, expected: Any) -> float:
    """Score based on how many expected key-value pairs appear in actual.

    Works recursively for nested dicts. For non-dict values, falls back
    to exact match.

    Args:
        actual: Model's answer.
        expected: Gold answer (subset that must be present).

    Returns:
        Float between 0.0 and 1.0.
    """
    if not isinstance(expected, dict):
        return score_exact_match(actual, expected)

    if not isinstance(actual, dict):
        return 0.0

    if not expected:
        return 1.0

    matches = 0
    total = len(expected)

    for key, exp_val in expected.items():
        if key in actual:
            if isinstance(exp_val, dict) and isinstance(actual[key], dict):
                matches += score_contains(actual[key], exp_val)
            elif normalize_value(actual[key]) == normalize_value(exp_val):
                matches += 1
        # Key missing → 0 for this field

    return matches / total


def score_type_match(actual: Any, expected: Any) -> float:
    """Score based on structural similarity: same keys, same types.

    Doesn't compare values — only checks that the shape matches.

    Args:
        actual: Model's answer.
        expected: Gold answer (defines expected structure).

    Returns:
        Float between 0.0 and 1.0.
    """
    if type(actual) is not type(expected):
        return 0.0

    if isinstance(expected, dict):
        if not expected:
            return 1.0 if not actual else 0.0

        exp_keys = set(expected.keys())
        act_keys = set(actual.keys()) if isinstance(actual, dict) else set()

        if not exp_keys:
            return 1.0

        key_overlap = len(exp_keys & act_keys) / len(exp_keys)

        # Check types of shared keys
        type_matches = 0
        shared = exp_keys & act_keys
        for key in shared:
            if isinstance(expected[key], dict) and isinstance(actual[key], dict):
                type_matches += score_type_match(actual[key], expected[key])
            elif type(actual[key]) is type(expected[key]):
                type_matches += 1

        type_score = type_matches / len(shared) if shared else 0.0
        return (key_overlap + type_score) / 2

    if isinstance(expected, list):
        if len(expected) == 0:
            return 1.0 if isinstance(actual, list) and len(actual) == 0 else 0.0
        # Check first element type matches
        if isinstance(actual, list) and len(actual) > 0:
            return 1.0 if type(actual[0]) is type(expected[0]) else 0.5
        return 0.0

    return 1.0  # Same type for scalars (checked above)


def score(actual: Any, expected: Any, validation: str = "exact_match") -> float:
    """Score an answer using the specified validation strategy.

    Args:
        actual: Model's answer.
        expected: Gold answer.
        validation: One of 'exact_match', 'contains', 'type_match'.

    Returns:
        Float between 0.0 and 1.0.
    """
    scorers = {
        "exact_match": score_exact_match,
        "contains": score_contains,
        "type_match": score_type_match,
    }

    scorer = scorers.get(validation, score_exact_match)
    return scorer(actual, expected)
