class MyClass:
    """Class with various decorators."""

    @property
    def name(self) -> str:
        """Get the name."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set the name."""
        self._name = value

    @staticmethod
    def create() -> "MyClass":
        """Create a new instance."""
        return MyClass()

    @classmethod
    def from_dict(cls, data: dict) -> "MyClass":
        """Create from a dictionary."""
        obj = cls()
        return obj


def my_decorator(func):
    """A simple decorator."""
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        return result
    return wrapper
