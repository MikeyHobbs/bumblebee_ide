def simple_generator(n: int):
    """Simple generator with yield."""
    for i in range(n):
        yield i


def generator_with_return(items: list):
    """Generator that yields and returns."""
    for item in items:
        if item < 0:
            return
        yield item * 2


def yield_from_example(iterables: list):
    """Generator using yield from."""
    for iterable in iterables:
        yield from iterable


def fibonacci():
    """Infinite fibonacci generator."""
    a = 0
    b = 1
    while True:
        yield a
        a, b = b, a + b


def generator_expression_user(items: list) -> int:
    """Function using a generator expression."""
    total = sum(x * x for x in items)
    return total


def send_generator():
    """Generator that accepts sent values."""
    value = yield "started"
    while True:
        value = yield value * 2
