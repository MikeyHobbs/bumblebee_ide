from __future__ import annotations

"""Shared request/response types used across api and services."""


class Request:
    """Represents an incoming HTTP request."""

    def __init__(self) -> None:
        self.method: str = ""
        self.path: str = ""
        self.headers: dict = {}
        self.body: str = ""
        self.query_params: dict = {}


class Response:
    """Represents an outgoing HTTP response."""

    def __init__(self) -> None:
        self.status_code: int = 200
        self.body: str = ""
        self.headers: dict = {}


def make_error_response(status: int, message: str) -> Response:
    """Create a standardised error response.

    Args:
        status: The HTTP status code.
        message: A human-readable error message.

    Returns:
        A Response populated with error details.
    """
    resp = Response()
    resp.status_code = status
    resp.body = message
    resp.headers = {"Content-Type": "application/json"}
    return resp
