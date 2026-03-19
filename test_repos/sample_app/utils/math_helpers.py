"""Pure math, geometry, and statistics utilities."""

from __future__ import annotations

import math
import re


def distance(x1: float, y1: float, x2: float, y2: float) -> float:
    """Compute Euclidean distance between two 2D points."""
    dx = x2 - x1
    dy = y2 - y1
    return math.sqrt(dx * dx + dy * dy)


def normalize(value: float, min_val: float, max_val: float) -> float:
    """Normalize a value to the 0..1 range given min and max bounds.

    Returns 0.0 if min_val == max_val to avoid division by zero.
    """
    if max_val == min_val:
        return 0.0
    return (value - min_val) / (max_val - min_val)


def clamp_float(value: float, lo: float, hi: float) -> float:
    """Clamp a float value between lo and hi inclusive."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between a and b by factor t.

    When t=0 returns a, when t=1 returns b.
    """
    return a + (b - a) * t


def inverse_lerp(value: float, a: float, b: float) -> float:
    """Compute the interpolation factor t such that lerp(a, b, t) == value.

    Returns 0.0 if a == b to avoid division by zero.
    """
    if a == b:
        return 0.0
    return (value - a) / (b - a)


def weighted_average(values: list, weights: list) -> float:
    """Compute the weighted average of a list of values.

    Args:
        values: Numeric values.
        weights: Corresponding weights (must be same length as values).

    Returns:
        The weighted average. Returns 0.0 if total weight is zero.
    """
    if len(values) != len(weights):
        raise ValueError("values and weights must have the same length")
    total_weight = 0.0
    weighted_sum = 0.0
    for i in range(len(values)):
        weighted_sum += values[i] * weights[i]
        total_weight += weights[i]
    if total_weight == 0.0:
        return 0.0
    return weighted_sum / total_weight


def factorial(n: int) -> int:
    """Compute the factorial of n iteratively.

    Args:
        n: A non-negative integer.

    Returns:
        n! as an integer.
    """
    if n < 0:
        raise ValueError("factorial is not defined for negative numbers")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def fibonacci(n: int) -> int:
    """Compute the nth Fibonacci number iteratively.

    Uses the convention: fib(0)=0, fib(1)=1, fib(2)=1, ...
    """
    if n < 0:
        raise ValueError("fibonacci is not defined for negative indices")
    if n == 0:
        return 0
    if n == 1:
        return 1
    prev, curr = 0, 1
    for _ in range(2, n + 1):
        prev, curr = curr, prev + curr
    return curr


def gcd(a: int, b: int) -> int:
    """Compute greatest common divisor using Euclid's algorithm."""
    a = abs(a)
    b = abs(b)
    while b != 0:
        a, b = b, a % b
    return a


def lcm(a: int, b: int) -> int:
    """Compute the least common multiple of two integers."""
    if a == 0 or b == 0:
        return 0
    return abs(a * b) // gcd(a, b)


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug.

    Lowercases the string, replaces non-alphanumeric characters with hyphens,
    collapses consecutive hyphens, and strips leading/trailing hyphens.
    """
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    text = text.strip("-")
    return text


def truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len characters, appending '...' if truncated.

    If max_len is less than 4, the text is simply sliced without a suffix.
    """
    if len(text) <= max_len:
        return text
    if max_len < 4:
        return text[:max_len]
    return text[: max_len - 3] + "..."


def dot_product_2d(a, b) -> float:
    """Compute the 2D dot product of two vectors.

    Args:
        a: Object with .x and .y attributes.
        b: Object with .x and .y attributes.

    Returns:
        The scalar dot product a.x*b.x + a.y*b.y.
    """
    return float(a.x * b.x + a.y * b.y)


def cross_product_2d(a, b) -> float:
    """Compute the 2D cross product (z-component of the 3D cross product).

    Args:
        a: Object with .x and .y attributes.
        b: Object with .x and .y attributes.

    Returns:
        The scalar a.x*b.y - a.y*b.x.
    """
    return float(a.x * b.y - a.y * b.x)


def vector_magnitude_3d(vec) -> float:
    """Compute the magnitude of a 3D vector.

    Args:
        vec: Object with .x, .y, and .z attributes.

    Returns:
        The Euclidean length of the vector.
    """
    return math.sqrt(vec.x * vec.x + vec.y * vec.y + vec.z * vec.z)


def matrix_dimensions(matrix) -> tuple:
    """Return the dimensions of a matrix as (rows, cols).

    Args:
        matrix: Object with .rows and .cols attributes.
    """
    return (matrix.rows, matrix.cols)


def matrix_flatten(matrix) -> list:
    """Flatten a matrix into a single list in row-major order.

    Args:
        matrix: Object with .rows, .cols, and .data attributes.
            .data is expected to be a list of lists (rows x cols).

    Returns:
        A flat list of all elements.
    """
    flat = []
    for r in range(matrix.rows):
        for c in range(matrix.cols):
            flat.append(matrix.data[r][c])
    return flat


def compute_stats(values: list) -> dict:
    """Compute basic descriptive statistics for a list of numeric values.

    Returns a dict with keys: mean, median, std, count, min, max.
    """
    if not values:
        return {"mean": 0.0, "median": 0.0, "std": 0.0, "count": 0, "min": 0.0, "max": 0.0}

    n = len(values)
    total = 0.0
    for v in values:
        total += v
    mean = total / n

    sorted_vals = sorted(values)
    if n % 2 == 1:
        median = float(sorted_vals[n // 2])
    else:
        median = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0

    variance_sum = 0.0
    for v in values:
        diff = v - mean
        variance_sum += diff * diff
    std = math.sqrt(variance_sum / n)

    return {
        "mean": mean,
        "median": median,
        "std": std,
        "count": n,
        "min": float(min(values)),
        "max": float(max(values)),
    }


def summarize_stats(stats: dict) -> str:
    """Create a human-readable summary string from a stats dict.

    Args:
        stats: Dict with keys "mean", "median", "std", "count".

    Returns:
        A formatted summary string.
    """
    mean = stats["mean"]
    median = stats["median"]
    std = stats["std"]
    count = stats["count"]
    parts = [
        f"count={count}",
        f"mean={mean:.4f}",
        f"median={median:.4f}",
        f"std={std:.4f}",
    ]
    return "Stats(" + ", ".join(parts) + ")"
