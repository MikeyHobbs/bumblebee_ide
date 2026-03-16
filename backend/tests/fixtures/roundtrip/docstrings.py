def google_style(name: str, value: int) -> bool:
    """Check if the value is valid for the given name.

    Args:
        name: The identifier name.
        value: The numeric value to check.

    Returns:
        True if the value is valid, False otherwise.

    Raises:
        ValueError: If the name is empty.
    """
    if not name:
        raise ValueError("Name cannot be empty")
    return value > 0


class DocumentedClass:
    """A well-documented class.

    This class demonstrates Google-style docstrings on all public members.

    Attributes:
        data: The internal data store.
    """

    def __init__(self, data: list) -> None:
        """Initialize with data.

        Args:
            data: Initial data list.
        """
        self.data = data

    def process(self) -> list:
        """Process and return the data.

        Returns:
            The processed data list.
        """
        result = [x * 2 for x in self.data]
        return result
