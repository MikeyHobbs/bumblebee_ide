def list_comprehension(items: list) -> list:
    """List comprehension examples."""
    doubled = [x * 2 for x in items]
    filtered = [x for x in items if x > 0]
    nested = [x + y for x in items for y in items]
    return doubled + filtered + nested


def dict_comprehension(keys: list, values: list) -> dict:
    """Dict comprehension example."""
    result = {k: v for k, v in zip(keys, values)}
    inverted = {v: k for k, v in result.items()}
    return inverted


def set_comprehension(items: list) -> set:
    """Set comprehension example."""
    unique_abs = {abs(x) for x in items}
    return unique_abs


def generator_expression(items: list) -> int:
    """Generator expression example."""
    total = sum(x * x for x in items if x > 0)
    return total


def nested_comprehension(matrix: list) -> list:
    """Nested comprehension."""
    flat = [val for row in matrix for val in row]
    return flat
