"""Module testing type inference for obj.method() resolution."""

from calculator import Calculator


def direct_instance_call() -> int:
    """Create an instance and call a method."""
    calc = Calculator(10)
    calc.add(5)
    return calc.subtract(3)


def transitive_assignment() -> None:
    """Transitive alias: x = y, y = Calculator."""
    original = Calculator(0)
    alias = original
    alias.add(42)


def annotated_param(calc: Calculator) -> int:
    """Parameter with type annotation."""
    return calc.add(1)
