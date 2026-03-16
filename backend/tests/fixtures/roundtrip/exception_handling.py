def basic_try_except() -> int:
    """Basic try/except."""
    try:
        result = int("42")
    except ValueError:
        result = -1
    return result


def try_except_else_finally() -> str:
    """Full try/except/else/finally."""
    status = "unknown"
    try:
        value = 1 / 1
    except ZeroDivisionError:
        status = "error"
    else:
        status = "success"
    finally:
        pass
    return status


def multiple_except() -> int:
    """Multiple except clauses."""
    try:
        result = int("abc")
    except ValueError:
        result = -1
    except TypeError:
        result = -2
    except (KeyError, IndexError):
        result = -3
    return result


def except_with_as() -> str:
    """Except with as clause."""
    try:
        raise ValueError("test error")
    except ValueError as e:
        msg = str(e)
    return msg


def nested_try() -> str:
    """Nested try blocks."""
    try:
        try:
            result = int("abc")
        except ValueError:
            result = 0
        return str(result)
    except Exception:
        return "outer error"


def raise_from() -> None:
    """Raise with from clause."""
    try:
        raise ValueError("original")
    except ValueError as e:
        raise RuntimeError("wrapped") from e
