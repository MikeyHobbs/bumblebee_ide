"""A calculator module for testing."""


class Calculator:
    """A simple calculator class."""

    def __init__(self, value: int = 0) -> None:
        """Initialize with a value."""
        self.value = value

    def add(self, x: int) -> int:
        """Add x to the current value."""
        self.value += x
        return self.value

    def subtract(self, x: int) -> int:
        """Subtract x from the current value."""
        self.value -= x
        return self.value

    def reset(self) -> None:
        """Reset value to zero."""
        self.value = 0
