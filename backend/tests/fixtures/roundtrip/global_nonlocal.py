_counter = 0


def increment_global() -> int:
    """Function using global statement."""
    global _counter
    _counter += 1
    return _counter


def reset_global() -> None:
    """Reset the global counter."""
    global _counter
    _counter = 0


def make_counter() -> callable:
    """Function using nonlocal statement."""
    count = 0

    def increment() -> int:
        """Inner function with nonlocal."""
        nonlocal count
        count += 1
        return count

    return increment


def nested_nonlocal() -> callable:
    """Multiple levels of nonlocal."""
    value = 0

    def middle() -> callable:
        """Middle function."""
        def inner() -> int:
            """Inner function."""
            nonlocal value
            value += 10
            return value

        return inner

    return middle
