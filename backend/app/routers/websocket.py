"""WebSocket router for real-time graph events."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# Global set of connected WebSocket clients
_clients: set[WebSocket] = set()


async def broadcast(event: str, data: dict[str, str | int | list[str] | None]) -> None:
    """Broadcast an event to all connected WebSocket clients.

    Args:
        event: Event name (e.g., "graph:updated", "node:pulse", "index:progress").
        data: Event payload.
    """
    message = json.dumps({"event": event, "data": data})
    disconnected: list[WebSocket] = []
    for client in _clients:
        try:
            await client.send_text(message)
        except Exception:  # pylint: disable=broad-except  # WebSocket may be closed
            disconnected.append(client)
    for client in disconnected:
        _clients.discard(client)


@router.websocket("/ws/graph")
async def graph_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for graph events.

    Events sent to clients:
        - graph:updated: { affected_modules: string[] }
        - node:pulse: { node_id: string }
        - index:progress: { file: string, total: int, done: int }
    """
    await websocket.accept()
    _clients.add(websocket)
    logger.info("WebSocket client connected. Total clients: %d", len(_clients))
    try:
        while True:
            # Keep connection alive, handle any client messages
            data = await websocket.receive_text()
            # Client can send ping messages
            if data == "ping":
                await websocket.send_text(json.dumps({"event": "pong", "data": {}}))
    except WebSocketDisconnect:
        _clients.discard(websocket)
        logger.info("WebSocket client disconnected. Total clients: %d", len(_clients))
    except Exception:  # pylint: disable=broad-except  # Ensure cleanup
        _clients.discard(websocket)
