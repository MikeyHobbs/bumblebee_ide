"""File watcher service: monitors repo for changes and triggers re-indexing (TICKET-601)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time
from typing import Any

from app.config import settings
from app.graph.indexer import index_file
from app.models.exceptions import IndexingError

logger = logging.getLogger(__name__)

# Debounce interval in seconds
DEBOUNCE_INTERVAL = 0.3

# File checksums for change detection
_file_checksums: dict[str, str] = {}

# Background event loop reference for broadcasting
_event_loop: asyncio.AbstractEventLoop | None = None


class FileWatcher:
    """Watches a directory for Python file changes and triggers re-indexing.

    Uses watchdog for filesystem monitoring with debouncing and checksum
    comparison to avoid spurious re-indexes.

    Attributes:
        repo_path: Absolute path to the watched repository.
        observer: watchdog observer instance.
    """

    def __init__(self, repo_path: str) -> None:
        self.repo_path = os.path.abspath(repo_path)
        self._observer: Any = None
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._running = False

    def start(self) -> None:
        """Start watching the repository for changes."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent

            watcher = self

            class Handler(FileSystemEventHandler):
                """Handle file system events for Python files."""

                def on_modified(self, event: Any) -> None:
                    if not event.is_directory and event.src_path.endswith(".py"):
                        watcher._debounce_reindex(event.src_path)

                def on_created(self, event: Any) -> None:
                    if not event.is_directory and event.src_path.endswith(".py"):
                        watcher._debounce_reindex(event.src_path)

            self._observer = Observer()
            self._observer.schedule(Handler(), self.repo_path, recursive=True)
            self._observer.start()
            self._running = True
            logger.info("File watcher started for: %s", self.repo_path)
        except ImportError:
            logger.warning("watchdog not installed - file watching disabled")
        except Exception:
            logger.exception("Failed to start file watcher")

    def stop(self) -> None:
        """Stop the file watcher."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._running = False
            logger.info("File watcher stopped")

        # Cancel pending timers
        for timer in self._debounce_timers.values():
            timer.cancel()
        self._debounce_timers.clear()

    @property
    def is_running(self) -> bool:
        """Whether the watcher is currently active."""
        return self._running

    def _debounce_reindex(self, file_path: str) -> None:
        """Debounce file change events before triggering re-index.

        Args:
            file_path: Absolute path to the changed file.
        """
        # Cancel existing timer for this file
        if file_path in self._debounce_timers:
            self._debounce_timers[file_path].cancel()

        timer = threading.Timer(DEBOUNCE_INTERVAL, self._handle_change, args=[file_path])
        self._debounce_timers[file_path] = timer
        timer.start()

    def _handle_change(self, file_path: str) -> None:
        """Handle a file change after debouncing.

        Args:
            file_path: Absolute path to the changed file.
        """
        self._debounce_timers.pop(file_path, None)

        # Skip non-source directories
        rel_path = os.path.relpath(file_path, self.repo_path)
        skip_dirs = {"__pycache__", "node_modules", ".venv", "venv"}
        if any(part.startswith(".") or part in skip_dirs for part in rel_path.split(os.sep)):
            return

        # Checksum comparison
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
            new_checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
            old_checksum = _file_checksums.get(file_path)

            if old_checksum == new_checksum:
                return

            _file_checksums[file_path] = new_checksum
        except OSError:
            return

        # Re-index the file
        try:
            logger.info("Re-indexing changed file: %s", rel_path)
            index_file(file_path, repo_root=self.repo_path)

            # Broadcast graph:updated event
            module_name = rel_path.replace("/", ".").replace("\\", ".").removesuffix(".py")
            _broadcast_event("graph:updated", {"affected_modules": [module_name]})

            # Broadcast node:pulse for the module
            _broadcast_event("node:pulse", {"node_id": module_name})

        except IndexingError:
            logger.exception("Failed to re-index: %s", file_path)


def _broadcast_event(event: str, data: dict[str, Any]) -> None:
    """Broadcast a WebSocket event from the file watcher thread.

    Args:
        event: Event name.
        data: Event payload.
    """
    try:
        from app.routers.websocket import broadcast

        if _event_loop is not None and _event_loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast(event, data), _event_loop)
    except Exception:
        logger.debug("Could not broadcast event: %s", event)


# Global watcher instance
_watcher: FileWatcher | None = None


def start_watcher(repo_path: str, loop: asyncio.AbstractEventLoop | None = None) -> FileWatcher:
    """Start the global file watcher.

    Args:
        repo_path: Path to watch.
        loop: Event loop for broadcasting WebSocket events.

    Returns:
        The FileWatcher instance.
    """
    global _watcher, _event_loop  # pylint: disable=global-statement  # Module-level singleton
    if loop is not None:
        _event_loop = loop

    if _watcher is not None:
        _watcher.stop()

    _watcher = FileWatcher(repo_path)
    _watcher.start()
    return _watcher


def stop_watcher() -> None:
    """Stop the global file watcher."""
    global _watcher  # pylint: disable=global-statement  # Module-level singleton
    if _watcher is not None:
        _watcher.stop()
        _watcher = None
