"""Helper functions re-exported by pkg/__init__.py."""


def greet(name: str) -> str:
    """Return a greeting string."""
    return f"Hello, {name}!"


def compute_total(values: list) -> int:
    """Sum a list of values."""
    return sum(values)


def _private_helper() -> None:
    """Not re-exported."""
    pass
