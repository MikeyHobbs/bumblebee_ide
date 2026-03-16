class Base:
    """Base class."""

    def base_method(self) -> str:
        """Base method."""
        return "base"


class Mixin:
    """Mixin class."""

    def mixin_method(self) -> str:
        """Mixin method."""
        return "mixin"


class Child(Base, Mixin):
    """Class with multiple inheritance."""

    __slots__ = ("_name", "_value")

    class_var: int = 42
    _private_var: str = "private"

    def __init__(self, name: str, value: int = 0) -> None:
        """Initialize Child."""
        super().__init__()
        self._name = name
        self._value = value

    def __repr__(self) -> str:
        """Return string representation."""
        return f"Child(name={self._name!r}, value={self._value!r})"

    def __eq__(self, other: object) -> bool:
        """Check equality."""
        if not isinstance(other, Child):
            return NotImplemented
        return self._name == other._name and self._value == other._value

    @property
    def name(self) -> str:
        """Get name."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set name."""
        self._name = value

    @classmethod
    def create(cls, name: str) -> "Child":
        """Factory method."""
        return cls(name=name)

    @staticmethod
    def validate_name(name: str) -> bool:
        """Validate a name."""
        return len(name) > 0

    def combined(self) -> str:
        """Use methods from parent classes."""
        base_val = self.base_method()
        mixin_val = self.mixin_method()
        return f"{base_val}-{mixin_val}-{self._name}"
