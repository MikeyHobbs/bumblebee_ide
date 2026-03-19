from __future__ import annotations

"""HTTP request routing and response building."""

import json
import time

from core.types import Request, Response, make_error_response
from core.config import build_base_url
from services.auth_service import is_authenticated, extract_bearer_token


# ---------------------------------------------------------------------------
# Request routing
# ---------------------------------------------------------------------------

def route_request(request: Request) -> str:
    """Dispatch an incoming request to a handler name based on method and path.

    Args:
        request: The incoming HTTP request.

    Returns:
        The name of the handler that should process this request.
    """
    method = request.method
    path = request.path
    body = request.body
    query_params = request.query_params

    if method == "GET" and path == "/":
        return "index"
    if method == "GET" and path.startswith("/api/"):
        resource = path.split("/api/")[1].split("/")[0] if "/api/" in path else ""
        return f"get_{resource}" if resource else "api_root"
    if method == "POST" and body:
        return f"create_{path.strip('/').replace('/', '_')}"
    if method == "DELETE":
        return f"delete_{path.strip('/').replace('/', '_')}"
    if query_params.get("action"):
        return f"action_{query_params['action']}"
    return "not_found"


def parse_accept_header(request: Request) -> list:
    """Parse the Accept header into a sorted list of media types.

    Args:
        request: The incoming HTTP request.

    Returns:
        A list of accepted media type strings, ordered by quality factor.
    """
    accept_value = request.headers.get("Accept", "*/*")
    parts = []
    for entry in accept_value.split(","):
        entry = entry.strip()
        if ";q=" in entry:
            media, q = entry.split(";q=", 1)
            parts.append((media.strip(), float(q)))
        else:
            parts.append((entry, 1.0))
    parts.sort(key=lambda p: p[1], reverse=True)
    return [media for media, _ in parts]


def extract_content_type(request: Request) -> str:
    """Return the Content-Type header value, defaulting to octet-stream.

    Args:
        request: The incoming HTTP request.

    Returns:
        The content type string.
    """
    return request.headers.get("Content-Type", "application/octet-stream")


def log_request(request: Request, logger: object) -> None:
    """Log a summary of the request using the provided logger.

    Args:
        request: The incoming HTTP request.
        logger: An object with an ``info`` method.
    """
    method = request.method
    path = request.path
    logger.info(f"{method} {path}")  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Response building
# ---------------------------------------------------------------------------

def build_json_response(response: Response, data: dict) -> None:
    """Populate *response* with a JSON-serialised body.

    Args:
        response: The outgoing response to populate.
        data: The payload to serialise.
    """
    response.status_code = 200
    response.body = json.dumps(data, default=str)
    response.headers["Content-Type"] = "application/json"


def build_error_response(response: Response, status: int, message: str) -> None:
    """Populate *response* with an error payload.

    Args:
        response: The outgoing response to populate.
        status: The HTTP status code.
        message: A human-readable error description.
    """
    response.status_code = status
    response.body = json.dumps({"error": message})
    response.headers["Content-Type"] = "application/json"


def build_redirect_response(response: Response, location: str) -> None:
    """Populate *response* with a 302 redirect.

    Args:
        response: The outgoing response to populate.
        location: The target URL.
    """
    response.status_code = 302
    response.body = ""
    response.headers["Location"] = location


# ---------------------------------------------------------------------------
# Cross-module orchestration
# ---------------------------------------------------------------------------

def handle_api_call(request: Request, config: dict, session: dict) -> dict:
    """Handle a full API call: authenticate, resolve URL, and build result.

    Args:
        request: The incoming HTTP request.
        config: Application configuration dict with key ``debug``.
        session: Current session dict with key ``user_id``.

    Returns:
        A dict describing the outcome of the API call.
    """
    method = request.method
    path = request.path
    headers = request.headers
    body = request.body
    debug = config["debug"]
    user_id = session["user_id"]

    if not is_authenticated(session):
        return {"ok": False, "reason": "unauthenticated"}

    token = extract_bearer_token(request)
    if not token:
        return {"ok": False, "reason": "missing bearer token"}

    base_url = build_base_url(config)
    full_url = f"{base_url}{path}"

    result: dict = {
        "ok": True,
        "method": method,
        "url": full_url,
        "user_id": user_id,
        "has_body": bool(body),
    }
    if debug:
        result["debug_headers"] = dict(headers)
    return result


def build_request_context(request: Request, session: dict, config: dict) -> dict:
    """Build a context dict summarising the current request and session.

    Args:
        request: The incoming HTTP request.
        session: Current session dict.
        config: Application configuration dict.

    Returns:
        A context dict suitable for passing into middleware.
    """
    method = request.method
    path = request.path
    query_params = request.query_params
    user_id = session["user_id"]
    debug = config["debug"]

    return {
        "method": method,
        "path": path,
        "query": dict(query_params),
        "user_id": user_id,
        "debug": debug,
    }


# ---------------------------------------------------------------------------
# Logger helpers
# ---------------------------------------------------------------------------

def log_slow_request(request: Request, logger: object, threshold_ms: float) -> None:
    """Log a warning when a request is slower than the threshold.

    This is typically called after a request completes with the elapsed time
    already measured by the caller.

    Args:
        request: The completed request.
        logger: A logger with ``warning`` and ``debug`` methods.
        threshold_ms: Threshold in milliseconds above which a warning fires.
    """
    method = request.method
    path = request.path
    logger.debug(f"Checking slow-request threshold for {method} {path}")  # type: ignore[attr-defined]
    if threshold_ms > 1000:
        logger.warning(f"Slow request: {method} {path} took {threshold_ms:.1f}ms")  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Header utilities
# ---------------------------------------------------------------------------

def get_header_safe(headers: dict, name: str) -> str:
    """Return the value of *name* from *headers*, or empty string if absent.

    Args:
        headers: A dict of header name/value pairs.
        name: The header name to look up (case-sensitive).

    Returns:
        The header value or ``""``.
    """
    return headers.get(name, "")


def merge_headers(base: dict, extra: dict) -> dict:
    """Merge *extra* headers into *base* in-place and return the result.

    Args:
        base: The base header dict that will be mutated.
        extra: Additional headers to merge in.

    Returns:
        The updated *base* dict.
    """
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Middleware chain helpers
# ---------------------------------------------------------------------------

def register_middleware(chain: list, middleware: object) -> None:
    """Append a middleware callable to the end of the chain.

    Args:
        chain: The ordered list of middleware callables.
        middleware: The middleware to add.
    """
    chain.append(middleware)


def prepend_middleware(chain: list, middleware: object) -> None:
    """Insert a middleware callable at the front of the chain.

    Args:
        chain: The ordered list of middleware callables.
        middleware: The middleware to insert.
    """
    chain.insert(0, middleware)
