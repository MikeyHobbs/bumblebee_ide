"""Module for testing cross-function PASSES_TO and intra-function FEEDS."""


def producer(seed: int) -> int:
    """Produce a value from a seed."""
    result = seed * 2
    return result


def transformer(data: int) -> int:
    """Transform data."""
    output = data + 10
    return output


def consumer(value: int) -> None:
    """Consume a value."""
    print(value)


def pipeline() -> None:
    """A -> B -> C pipeline for testing PASSES_TO chains."""
    x = producer(42)
    y = transformer(x)
    consumer(y)


def keyword_passing() -> None:
    """Test keyword argument passing."""
    val = 100
    result = transformer(data=val)
    print(result)


def feeds_example() -> int:
    """Test FEEDS: reads that feed into assignments."""
    a = 10
    b = 20
    c = a + b
    d = c * 2
    return d


def mutation_feeds(items: list) -> None:
    """Test FEEDS: reads that feed into mutations."""
    new_item = 42
    items.append(new_item)
