"""Module with nested definitions for testing."""


class Outer:
    """Outer class."""

    class Inner:
        """Inner class."""

        def inner_method(self) -> str:
            """Inner class method."""
            return "inner"

    def outer_method(self) -> str:
        """Outer class method."""
        return "outer"

    @staticmethod
    def static_method() -> str:
        """A static method."""
        return "static"


def top_level_func() -> None:
    """A top-level function."""

    def nested_func() -> str:
        """A nested function."""
        return "nested"

    nested_func()
