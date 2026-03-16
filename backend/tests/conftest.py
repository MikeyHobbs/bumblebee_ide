"""Shared test fixtures for Bumblebee backend tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_python_source() -> str:
    """Return a sample Python source string for testing."""
    return '''
class Calculator:
    """A simple calculator class."""

    def __init__(self, value: int = 0) -> None:
        self.value = value

    def add(self, x: int) -> int:
        """Add x to the current value."""
        self.value += x
        return self.value

    def reset(self) -> None:
        """Reset value to zero."""
        self.value = 0


def create_calculator(initial: int = 0) -> Calculator:
    """Factory function for Calculator."""
    calc = Calculator(initial)
    return calc
'''
