"""Module testing decorator extraction."""

from functools import lru_cache


def my_decorator(func):
    """A custom decorator."""
    return func


@lru_cache(maxsize=128)
def cached_compute(n: int) -> int:
    """A cached computation."""
    return n * n


@my_decorator
def decorated_func() -> str:
    """A decorated function."""
    return "decorated"


class MyClass:
    """Class with decorated methods."""

    @staticmethod
    def static_method() -> None:
        """Static method."""
        pass

    @classmethod
    def class_method(cls) -> None:
        """Class method."""
        pass

    @property
    def my_property(self) -> str:
        """A property."""
        return "value"
