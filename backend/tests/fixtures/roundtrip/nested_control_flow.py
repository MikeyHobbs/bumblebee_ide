def deep_nesting(data: list) -> list:
    """Function with deeply nested control flow."""
    results = []
    for item in data:
        if isinstance(item, list):
            for sub_item in item:
                if sub_item > 0:
                    results.append(sub_item * 2)
                else:
                    results.append(0)
        elif isinstance(item, int):
            if item > 100:
                results.append(item)
            elif item > 50:
                results.append(item * 2)
            else:
                results.append(item * 3)
        else:
            results.append(-1)
    return results


def triple_nested_while(n: int) -> int:
    """Three levels of nested while loops."""
    total = 0
    i = 0
    while i < n:
        j = 0
        while j < n:
            k = 0
            while k < n:
                total += 1
                k += 1
            j += 1
        i += 1
    return total


def mixed_nesting(items: list, threshold: int) -> dict:
    """Mix of for, if, while, and try nesting."""
    result = {}
    for idx, item in enumerate(items):
        if item > threshold:
            try:
                value = 100 / item
                result[idx] = value
            except ZeroDivisionError:
                result[idx] = 0
        else:
            count = 0
            while count < item:
                count += 1
            result[idx] = count
    return result
