"""Module using import aliases for testing alias prefix expansion."""

import calculator as calc_mod
from utils import validate_positive as vp


def use_alias() -> int:
    """Call functions via import aliases."""
    c = calc_mod.Calculator(10)
    if vp(5):
        c.add(5)
    return c.value


def use_dotted_alias() -> None:
    """Call a dotted alias."""
    result = calc_mod.Calculator(0)
    result.reset()
