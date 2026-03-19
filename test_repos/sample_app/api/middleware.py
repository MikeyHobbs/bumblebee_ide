from __future__ import annotations

"""Request middleware: CORS, authentication, session handling."""

import time

from core.types import Request, Response
from core.config import validate_cors_origin, apply_cors_settings
from services.auth_service import authenticate_request, get_session_user


# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------

def cors_middleware(request: Request, response: Response, settings: dict) -> bool:
    """Apply CORS headers to the response if the origin is allowed.

    Args:
        request: The incoming HTTP request.
        response: The outgoing response that will receive CORS headers.
        settings: CORS settings dict with key ``allowed_origins``.

    Returns:
        True if the origin was allowed and headers were applied.
    """
    origin = request.headers.get("Origin", "")
    method = request.method

    if not origin:
        return False

    if not validate_cors_origin(origin, settings):
        response.headers["X-CORS-Rejected"] = "true"
        return False

    apply_cors_settings(settings, response)
    response.headers["Vary"] = "Origin"

    if method == "OPTIONS":
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"

    return True


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

def auth_middleware(request: Request, session: dict, secret_key: str) -> dict:
    """Authenticate the request and return an auth result dict.

    Args:
        request: The incoming HTTP request.
        session: Current session with keys ``user_id`` and ``token``.
        secret_key: The server-side signing secret.

    Returns:
        A dict with ``ok`` and either ``user_id`` or ``reason``.
    """
    auth_header = request.headers.get("Authorization", "")
    body = request.body
    user_id = session["user_id"]
    token = session["token"]

    if not auth_header:
        return {"ok": False, "reason": "missing authorization header"}

    result = authenticate_request(request, session, secret_key)
    return result


# ---------------------------------------------------------------------------
# Logging middleware
# ---------------------------------------------------------------------------

def logging_middleware(request: Request, response: Response, logger: object) -> None:
    """Log the request method, path, and response status code.

    Args:
        request: The incoming HTTP request.
        response: The outgoing response.
        logger: An object with an ``info`` method.
    """
    method = request.method
    path = request.path
    status_code = response.status_code
    logger.info(f"{method} {path} -> {status_code}")  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def get_current_user(session: dict) -> str:
    """Return the current user id if the session is still valid.

    Args:
        session: Session dict with keys ``user_id``, ``token``, ``expires_at``.

    Returns:
        The user id, or empty string if the session has expired.
    """
    user_id = session["user_id"]
    token = session["token"]
    expires_at = session["expires_at"]

    if not token:
        return ""
    if expires_at < time.time():
        return ""
    return user_id


def refresh_session(session: dict, new_token: str) -> dict:
    """Create a refreshed copy of the session with a new token and expiry.

    Args:
        session: The current session dict.
        new_token: The replacement token value.

    Returns:
        A new session dict with updated token and extended expiry.
    """
    expires_at = session["expires_at"]
    user_id = session["user_id"]

    return {
        "user_id": user_id,
        "token": new_token,
        "expires_at": expires_at + 3600,
        "refreshed_at": time.time(),
    }


def session_is_valid(session: dict) -> bool:
    """Return True if the session has not expired.

    Args:
        session: Session dict with key ``expires_at``.

    Returns:
        True when the expiry timestamp is in the future.
    """
    expires_at = session["expires_at"]
    return expires_at > time.time()


# ---------------------------------------------------------------------------
# CORS settings helpers
# ---------------------------------------------------------------------------

def configure_cors(settings: dict) -> dict:
    """Build a normalised CORS configuration from raw settings.

    Args:
        settings: Dict with keys ``allowed_origins``, ``max_age``,
            ``allow_credentials``.

    Returns:
        A normalised CORS config dict.
    """
    allowed_origins = settings["allowed_origins"]
    max_age = settings["max_age"]
    allow_credentials = settings["allow_credentials"]

    return {
        "origins": list(allowed_origins),
        "max_age": max(int(max_age), 0),
        "credentials": bool(allow_credentials),
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    }


def is_origin_allowed(settings: dict, origin: str) -> bool:
    """Check whether *origin* appears in the allowed origins list.

    Args:
        settings: Dict with key ``allowed_origins``.
        origin: The origin string to check.

    Returns:
        True if the origin is allowed.
    """
    allowed_origins = settings["allowed_origins"]
    return origin in allowed_origins


# ---------------------------------------------------------------------------
# Response header helpers
# ---------------------------------------------------------------------------

def set_security_headers(response: Response) -> None:
    """Apply standard security headers to the response.

    Args:
        response: The outgoing response.
    """
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


def set_cache_headers(response: Response, max_age: int) -> None:
    """Set caching headers based on the response status and requested max age.

    Args:
        response: The outgoing response.
        max_age: Cache duration in seconds.
    """
    status_code = response.status_code
    if status_code >= 400:
        response.headers["Cache-Control"] = "no-store"
    else:
        response.headers["Cache-Control"] = f"public, max-age={max_age}"
        response.headers["Vary"] = "Accept-Encoding"


# ---------------------------------------------------------------------------
# Middleware chain runner
# ---------------------------------------------------------------------------

def run_middleware_chain(chain: list, request: Request, response: Response, context: dict) -> bool:
    """Execute each middleware in the chain sequentially.

    If any middleware returns False, the chain is halted and this function
    returns False.

    Args:
        chain: An ordered list of middleware callables.
        request: The incoming HTTP request.
        response: The outgoing response.
        context: A dict with keys ``session`` and ``config``.

    Returns:
        True if all middleware completed successfully.
    """
    method = request.method
    session = context["session"]
    config = context["config"]

    for mw in chain:
        try:
            result = mw(request, response, context)
            if result is False:
                response.status_code = 403
                return False
        except Exception:
            response.status_code = 500
            return False

    return True
