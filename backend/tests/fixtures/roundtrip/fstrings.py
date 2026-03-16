def simple_fstring(name: str) -> str:
    """Simple f-string."""
    result = f"Hello, {name}!"
    return result


def expression_fstring(x: int, y: int) -> str:
    """F-string with expressions."""
    result = f"Sum: {x + y}, Product: {x * y}"
    return result


def format_spec_fstring(value: float) -> str:
    """F-string with format specifiers."""
    result = f"Value: {value:.2f}, Percent: {value:.1%}"
    return result


def nested_fstring(items: list) -> str:
    """F-string with nested expressions."""
    result = f"Count: {len(items)}, First: {items[0] if items else 'none'}"
    return result


def dict_access_fstring(data: dict) -> str:
    """F-string with dictionary access."""
    result = f"Name: {data['name']}, Age: {data['age']}"
    return result


def multiline_fstring_expr(values: list) -> str:
    """F-string with complex expression."""
    result = f"Total: {sum(v for v in values if v > 0)}"
    return result
