from typing import Optional, Union


def typed_params(
    name: str,
    age: int,
    scores: list[float],
    metadata: dict[str, int],
) -> tuple[str, int]:
    """Function with full type annotations."""
    result = (name, age)
    return result


def optional_params(
    value: Optional[int] = None,
    flag: bool = False,
) -> Union[int, str]:
    """Function with Optional and Union types."""
    if value is not None:
        return value * 2
    if flag:
        return "flagged"
    return 0


def complex_return(items: list[dict[str, list[int]]]) -> dict[str, int]:
    """Function with complex nested type hints."""
    result = {}
    for item in items:
        for key, values in item.items():
            result[key] = sum(values)
    return result
