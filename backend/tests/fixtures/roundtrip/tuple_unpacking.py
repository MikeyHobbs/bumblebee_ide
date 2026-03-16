def simple_unpacking() -> tuple:
    """Simple tuple unpacking."""
    a, b = 1, 2
    x, y, z = (10, 20, 30)
    return (a, b, x, y, z)


def star_unpacking() -> list:
    """Star unpacking."""
    first, *rest = [1, 2, 3, 4, 5]
    *init, last = [10, 20, 30, 40]
    a, *middle, z = [100, 200, 300, 400, 500]
    return rest + init + middle


def nested_unpacking() -> tuple:
    """Nested tuple unpacking."""
    (a, b), (c, d) = (1, 2), (3, 4)
    return (a, b, c, d)


def swap_variables() -> tuple:
    """Variable swapping via unpacking."""
    x = 10
    y = 20
    x, y = y, x
    return (x, y)


def multiple_assignment() -> tuple:
    """Multiple assignment targets."""
    a = b = c = 0
    x = y = []
    return (a, b, c, x, y)
