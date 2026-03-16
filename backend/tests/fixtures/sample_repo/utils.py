"""Utility functions for testing."""


def validate_positive(value: int) -> bool:
    """Check if a value is positive."""
    return value > 0


def clamp(value: int, min_val: int, max_val: int) -> int:
    """Clamp a value between min and max."""
    if value < min_val:
        return min_val
    if value > max_val:
        return max_val
    return value


async def fetch_data(url: str) -> dict:
    """Async function for testing async detection."""
    return {"url": url, "data": None}
