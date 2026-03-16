def positional_only(a: int, b: int, /) -> int:
    """Function with positional-only parameters."""
    return a + b


def keyword_only(*, name: str, value: int) -> str:
    """Function with keyword-only parameters."""
    return f"{name}={value}"


def mixed_params(a: int, b: int, /, c: int = 0, *, d: int = 1) -> int:
    """Function with mixed parameter kinds."""
    return a + b + c + d


def args_kwargs(*args: int, **kwargs: str) -> tuple:
    """Function with *args and **kwargs."""
    total = sum(args)
    labels = list(kwargs.values())
    return (total, labels)


def all_param_kinds(a: int, /, b: int, *args: int, c: int = 0, **kwargs: str) -> dict:
    """Function with all parameter kinds."""
    result = {"a": a, "b": b, "args": args, "c": c, "kwargs": kwargs}
    return result
