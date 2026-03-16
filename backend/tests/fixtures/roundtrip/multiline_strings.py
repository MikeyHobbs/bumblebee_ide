def triple_quoted() -> str:
    """Function with triple-quoted strings."""
    text = """This is a
    multiline string
    with several lines."""
    return text


def raw_string() -> str:
    """Function with raw strings."""
    pattern = r"\d+\.\d+"
    return pattern


def byte_string() -> bytes:
    """Function with byte strings."""
    data = b"hello world"
    return data


def concatenated_strings() -> str:
    """Function with implicit string concatenation."""
    result = (
        "first part "
        "second part "
        "third part"
    )
    return result


def multiline_fstring(name: str, items: list) -> str:
    """Function with multiline f-string."""
    msg = (
        f"Hello {name}, "
        f"you have {len(items)} items"
    )
    return msg
