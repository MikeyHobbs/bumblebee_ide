"""Internal module with a class re-exported by pkg/__init__.py."""


class InternalClass:
    """A class re-exported at the package level."""

    def do_work(self) -> str:
        """Perform some work."""
        return "done"
