"""FalkorDB singleton client management."""

from __future__ import annotations

from falkordb import FalkorDB

from app.config import settings

_client: FalkorDB | None = None


def get_client() -> FalkorDB:
    """Get the singleton FalkorDB client instance."""
    global _client  # pylint: disable=global-statement  # Singleton pattern
    if _client is None:
        _client = FalkorDB(host=settings.falkor_host, port=settings.falkor_port)
    return _client


def get_graph():  # type: ignore[no-untyped-def]
    """Get the default graph instance."""
    return get_client().select_graph(settings.falkor_graph_name)


def init_client() -> None:
    """Initialize the FalkorDB client (called during app startup)."""
    get_client()


def close_client() -> None:
    """Close the FalkorDB client connection (called during app shutdown)."""
    global _client  # pylint: disable=global-statement  # Singleton pattern
    if _client is not None:
        _client.close()
        _client = None
