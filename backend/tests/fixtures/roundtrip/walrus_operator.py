def walrus_in_if(data: list) -> list:
    """Walrus operator in if condition."""
    results = []
    if (n := len(data)) > 10:
        results.append(n)
    return results


def walrus_in_while() -> list:
    """Walrus operator in while loop."""
    values = [1, 2, 3, 0, 4, 5]
    results = []
    idx = 0
    while (val := values[idx]) != 0:
        results.append(val * 2)
        idx += 1
    return results


def walrus_in_comprehension(items: list) -> list:
    """Walrus operator in list comprehension."""
    results = [y for x in items if (y := x * 2) > 5]
    return results
