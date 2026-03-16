def match_basic(command: str) -> str:
    """Basic match/case statement."""
    match command:
        case "start":
            return "Starting..."
        case "stop":
            return "Stopping..."
        case "pause":
            return "Pausing..."
        case _:
            return "Unknown command"


def match_with_guard(point: tuple) -> str:
    """Match with guard clause."""
    match point:
        case (x, y) if x > 0 and y > 0:
            return "first quadrant"
        case (x, y) if x < 0 and y > 0:
            return "second quadrant"
        case (0, 0):
            return "origin"
        case _:
            return "other"


def match_class_pattern(obj) -> str:
    """Match with class patterns."""
    match obj:
        case {"action": "buy", "amount": amount}:
            return f"Buying {amount}"
        case {"action": "sell", "amount": amount}:
            return f"Selling {amount}"
        case [first, *rest]:
            return f"List starting with {first}"
        case _:
            return "no match"
