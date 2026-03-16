"""Module with various control flow structures for testing."""


def simple_statements(x: int) -> int:
    """Function with simple sequential statements."""
    a = x + 1
    b = a * 2
    c = b - 3
    return c


def if_else_flow(x: int) -> str:
    """Function with if/elif/else."""
    result = "unknown"
    if x > 10:
        result = "high"
    elif x > 5:
        result = "medium"
    else:
        result = "low"
    return result


def for_loop(items: list) -> int:
    """Function with a for loop."""
    total = 0
    for item in items:
        total += item
    return total


def while_loop(n: int) -> int:
    """Function with a while loop."""
    count = 0
    while n > 0:
        count += 1
        n -= 1
    return count


def try_except_flow(value: str) -> int:
    """Function with try/except/else/finally."""
    result = 0
    try:
        result = int(value)
    except ValueError:
        result = -1
    except TypeError:
        result = -2
    else:
        result = result * 2
    finally:
        print(result)
    return result


def nested_control_flow(data: list) -> list:
    """Function with nested control flow."""
    results = []
    for item in data:
        if item > 0:
            results.append(item * 2)
        else:
            results.append(0)
    return results


def with_statement(path: str) -> str:
    """Function with a with statement."""
    content = ""
    with open(path) as f:
        content = f.read()
    return content
