from __future__ import annotations

"""Application configuration and settings."""


def build_base_url(config: dict) -> str:
    """Build the base URL from host, port, and TLS settings.

    Args:
        config: Dict with keys "host", "port", "tls_enabled".

    Returns:
        A fully qualified base URL string.
    """
    scheme = "https" if config["tls_enabled"] else "http"
    host = config["host"]
    port = config["port"]
    return f"{scheme}://{host}:{port}"


def create_server_socket(config: dict) -> dict:
    """Create a server socket descriptor from the config.

    Args:
        config: Dict with keys "host", "port".

    Returns:
        A dict describing the socket binding.
    """
    return {
        "address": config["host"],
        "port": config["port"],
        "backlog": 128,
    }


def should_auto_reload(config: dict) -> bool:
    """Determine whether the server should auto-reload on file changes.

    Args:
        config: Dict with key "debug".

    Returns:
        True when debug mode is enabled.
    """
    return bool(config["debug"])


def get_full_config_summary(config: dict) -> str:
    """Return a human-readable summary of the full configuration.

    Args:
        config: Dict with keys "host", "port", "debug", "tls_enabled".

    Returns:
        A multi-line summary string.
    """
    lines = [
        f"Host: {config['host']}",
        f"Port: {config['port']}",
        f"Debug: {config['debug']}",
        f"TLS: {config['tls_enabled']}",
    ]
    return "\n".join(lines)


def apply_cors_settings(settings: dict, response: object) -> None:
    """Apply CORS headers to the given response object.

    Args:
        settings: Dict with keys "allowed_origins", "max_age".
        response: An object with a ``headers`` dict attribute.
    """
    origins = settings["allowed_origins"]
    max_age = settings["max_age"]
    response.headers["Access-Control-Allow-Origin"] = ", ".join(origins)  # type: ignore[attr-defined]
    response.headers["Access-Control-Max-Age"] = str(max_age)  # type: ignore[attr-defined]


def validate_cors_origin(origin: str, settings: dict) -> bool:
    """Check whether a given origin is in the allowed list.

    Args:
        origin: The origin to validate.
        settings: Dict with key "allowed_origins".

    Returns:
        True if the origin is allowed.
    """
    return origin in settings["allowed_origins"]


def get_database_url(db_config: dict) -> str:
    """Build a database connection URL.

    Args:
        db_config: Dict with keys "host", "port", "name".

    Returns:
        A connection URL string.
    """
    return f"postgresql://{db_config['host']}:{db_config['port']}/{db_config['name']}"


def get_cache_config(cache: dict) -> dict:
    """Normalise and return cache configuration.

    Args:
        cache: Dict with keys "ttl", "max_size".

    Returns:
        A dict with validated cache parameters.
    """
    ttl = int(cache["ttl"])
    max_size = int(cache["max_size"])
    return {
        "ttl": max(ttl, 0),
        "max_size": max(max_size, 1),
        "enabled": ttl > 0,
    }
