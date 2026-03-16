def lambda_assignment() -> None:
    """Lambda in assignment."""
    double = lambda x: x * 2
    triple = lambda x: x * 3
    result = double(5) + triple(3)
    return result


def lambda_as_argument(items: list) -> list:
    """Lambda as function argument."""
    sorted_items = sorted(items, key=lambda x: x[1])
    filtered = list(filter(lambda x: x > 0, items))
    mapped = list(map(lambda x: x * 2, items))
    return sorted_items


def lambda_in_dict() -> dict:
    """Lambda stored in a dictionary."""
    ops = {
        "add": lambda a, b: a + b,
        "sub": lambda a, b: a - b,
        "mul": lambda a, b: a * b,
    }
    result = ops["add"](1, 2)
    return ops


def lambda_with_default() -> None:
    """Lambda with default parameter."""
    greet = lambda name, greeting="Hello": f"{greeting}, {name}!"
    result = greet("World")
    return result
