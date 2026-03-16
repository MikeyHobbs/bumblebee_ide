"""Service module with cross-function calls for testing relationships."""

from calculator import Calculator
from utils import validate_positive, clamp


def create_and_compute(initial: int, amount: int) -> int:
    """Create a calculator and perform operations."""
    if validate_positive(initial):
        calc = Calculator(initial)
        calc.add(amount)
        result = calc.add(clamp(amount, 0, 100))
        return result
    return 0


def process_batch(values: list) -> list:
    """Process a batch of values."""
    results = []
    for val in values:
        result = create_and_compute(val, 10)
        results.append(result)
    return results


def main() -> None:
    """Entry point."""
    batch = [1, 2, 3, 4, 5]
    results = process_batch(batch)
    print(results)
