class Counter:
    """A simple counter class."""

    def __init__(self, start: int = 0) -> None:
        """Initialize the counter."""
        self.value = start

    def increment(self) -> None:
        """Increment the counter by one."""
        self.value += 1

    def decrement(self) -> None:
        """Decrement the counter by one."""
        self.value -= 1

    def reset(self) -> None:
        """Reset the counter to zero."""
        self.value = 0

    def get_value(self) -> int:
        """Return the current value."""
        return self.value

    @property
    def is_zero(self) -> bool:
        """Check if the counter is at zero."""
        return self.value == 0
