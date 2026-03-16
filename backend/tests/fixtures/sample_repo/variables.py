"""Module for testing variable and mutation extraction."""


class Account:
    """A bank account for testing self.x handling."""

    def __init__(self, owner: str, balance: float = 0.0) -> None:
        """Initialize account."""
        self.owner = owner
        self.balance = balance
        self.transactions: list = []

    def deposit(self, amount: float) -> float:
        """Deposit money."""
        self.balance += amount
        self.transactions.append(amount)
        return self.balance

    def withdraw(self, amount: float) -> float:
        """Withdraw money with validation."""
        if amount > self.balance:
            raise ValueError("Insufficient funds")
        self.balance -= amount
        self.transactions.append(-amount)
        return self.balance


def process_items(items: list, threshold: int = 10) -> dict:
    """Process items with various assignment patterns."""
    result = {}
    count = 0
    total = 0

    for item in items:
        if item > threshold:
            count += 1
            total += item
            result[item] = True
        else:
            result[item] = False

    average = total / count if count > 0 else 0
    return result


def unpacking_example() -> None:
    """Test tuple unpacking assignments."""
    a, b = 1, 2
    x, y, z = (10, 20, 30)
    first, *rest = [1, 2, 3, 4, 5]


def walrus_example(data: list) -> list:
    """Test walrus operator."""
    results = []
    results.append(data)
    return results


def mutation_patterns(items: list, data: dict, numbers: set) -> None:
    """Test various mutation patterns."""
    items.append(1)
    items.extend([2, 3])
    items.sort()

    data.update({"key": "value"})
    data.setdefault("default", 0)

    numbers.add(42)
    numbers.discard(0)

    items[0] = 99
