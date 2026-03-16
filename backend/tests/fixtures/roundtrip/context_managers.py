def single_context_manager(path: str) -> str:
    """Single context manager."""
    with open(path) as f:
        content = f.read()
    return content


def multiple_context_managers(path1: str, path2: str) -> tuple:
    """Multiple context managers."""
    with open(path1) as f1, open(path2) as f2:
        data1 = f1.read()
        data2 = f2.read()
    return (data1, data2)


def nested_context_managers(path: str) -> str:
    """Nested context managers."""
    with open(path) as f:
        with open(path) as g:
            content = f.read() + g.read()
    return content


def context_manager_with_try(path: str) -> str:
    """Context manager combined with try/except."""
    try:
        with open(path) as f:
            content = f.read()
    except FileNotFoundError:
        content = ""
    return content
