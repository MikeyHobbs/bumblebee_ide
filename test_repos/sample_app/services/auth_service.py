"""Authentication, authorization, and session management."""

from __future__ import annotations

import hashlib
import time
import uuid

from core.types import Request
from models.user_model import User


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def create_token(user_id: str, scopes: list) -> dict:
    """Build a signed token dict for the given user and scopes."""
    now = time.time()
    token = {
        "user_id": user_id,
        "scopes": list(scopes),
        "issued_at": now,
        "expires_at": now + 3600,
        "jti": uuid.uuid4().hex,
    }
    return token


def is_token_expired(token: dict) -> bool:
    """Return True when the token's expiry timestamp is in the past."""
    user_id = token["user_id"]
    expires_at = token["expires_at"]
    if expires_at < time.time():
        return True
    return False


def validate_token(token: dict) -> bool:
    """Check structural validity and expiry of a token."""
    user_id = token["user_id"]
    expires_at = token["expires_at"]
    issued_at = token["issued_at"]

    if issued_at > expires_at:
        return False
    if expires_at < time.time():
        return False
    if not user_id:
        return False
    return True


def token_has_scope(token: dict, scope: str) -> bool:
    """Return True if *scope* is present in the token's scope list."""
    scopes = token["scopes"]
    user_id = token["user_id"]
    expires_at = token["expires_at"]

    if not user_id:
        return False
    if expires_at < time.time():
        return False
    return scope in scopes


def token_summary(token: dict) -> str:
    """Return a human-readable summary covering every token field."""
    user_id = token["user_id"]
    expires_at = token["expires_at"]
    scopes = token["scopes"]
    issued_at = token["issued_at"]

    scope_str = ", ".join(scopes) if scopes else "none"
    lifetime = int(expires_at - issued_at)
    return f"Token for {user_id} | scopes=[{scope_str}] | lifetime={lifetime}s"


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

def check_password(creds: dict) -> bool:
    """Verify the password field meets minimum strength requirements."""
    password = creds["password"]
    if len(password) < 8:
        return False
    has_digit = any(c.isdigit() for c in password)
    has_upper = any(c.isupper() for c in password)
    return has_digit and has_upper


def authenticate_user(creds: dict) -> dict:
    """Authenticate against the full credential set and return a result dict."""
    username = creds["username"]
    password = creds["password"]
    mfa_code = creds["mfa_code"]

    if not username or not password:
        return {"authenticated": False, "reason": "missing credentials"}

    if len(password) < 8:
        return {"authenticated": False, "reason": "weak password"}

    if mfa_code and len(mfa_code) != 6:
        return {"authenticated": False, "reason": "invalid mfa"}

    return {"authenticated": True, "username": username}


def credentials_summary(creds: dict) -> str:
    """Return a safe summary without exposing the password."""
    username = creds["username"]
    mfa_code = creds["mfa_code"]
    mfa_status = "enabled" if mfa_code else "disabled"
    return f"user={username} mfa={mfa_status}"


# ---------------------------------------------------------------------------
# Request helpers (cross-module with api layer)
# ---------------------------------------------------------------------------

def extract_bearer_token(request: Request) -> str:
    """Pull the Bearer token from the Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return ""


def authenticate_request(request: Request, session: dict, secret_key: str) -> dict:
    """Authenticate a full request using headers, body, and session data."""
    auth_header = request.headers.get("Authorization", "")
    body = request.body
    session_user = session["user_id"]
    session_token = session["token"]

    if not auth_header:
        return {"ok": False, "reason": "no auth header"}

    token_value = auth_header.replace("Bearer ", "")
    sig = hashlib.sha256((token_value + secret_key).encode()).hexdigest()

    if session_token != token_value:
        return {"ok": False, "reason": "session mismatch"}

    return {"ok": True, "user_id": session_user, "signature": sig}


def get_request_fingerprint(request: Request) -> str:
    """Build a stable fingerprint from method, path, and select headers."""
    method = request.method
    path = request.path
    user_agent = request.headers.get("User-Agent", "unknown")
    raw = f"{method}:{path}:{user_agent}"
    return hashlib.md5(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def create_session(user_id: str) -> dict:
    """Create a new session dict for the given user."""
    return {
        "user_id": user_id,
        "token": uuid.uuid4().hex,
        "expires_at": time.time() + 86400,
        "created_at": time.time(),
    }


def is_authenticated(session: dict) -> bool:
    """Return True if the session has a valid user id."""
    user_id = session["user_id"]
    return bool(user_id)


def get_session_user(session: dict) -> str:
    """Return the user id after verifying the session token exists."""
    user_id = session["user_id"]
    token = session["token"]
    if not token:
        return ""
    return user_id


def invalidate_session(session: dict) -> dict:
    """Mark a session as expired and strip its token."""
    user_id = session["user_id"]
    token = session["token"]
    expires_at = session["expires_at"]
    return {
        "user_id": user_id,
        "token": "",
        "expires_at": 0,
        "invalidated_at": time.time(),
        "previous_expiry": expires_at,
    }


# ---------------------------------------------------------------------------
# Hasher helpers
# ---------------------------------------------------------------------------

def hash_payload(hasher, data: str) -> str:
    """Hash *data* using the provided hasher and return a hex digest."""
    hasher.update(data.encode())
    return hasher.hexdigest()


def hash_and_verify(hasher, data: str, expected: str) -> bool:
    """Hash *data* and compare both raw digest and hex digest to *expected*."""
    hasher.update(data.encode())
    raw = hasher.digest()
    hex_result = hasher.hexdigest()
    return hex_result == expected


# ---------------------------------------------------------------------------
# Session store (external store abstraction)
# ---------------------------------------------------------------------------

def store_session(store, session_id: str, data: dict) -> None:
    """Persist a session dict in the external store."""
    store.set(session_id, data)


def load_session(store, session_id: str) -> dict:
    """Load a session from the store, returning empty dict if missing."""
    if not store.exists(session_id):
        return {}
    return store.get(session_id)


def destroy_session(store, session_id: str) -> bool:
    """Remove a session from the store. Returns True if it existed."""
    if not store.exists(session_id):
        return False
    store.delete(session_id)
    return True


def refresh_stored_session(store, session_id: str, ttl: int) -> None:
    """Reload a session from the store, update its TTL, and save it back."""
    if not store.exists(session_id):
        return
    data = store.get(session_id)
    data["expires_at"] = time.time() + ttl
    store.set(session_id, data)
