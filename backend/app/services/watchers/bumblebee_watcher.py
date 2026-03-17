"""Bumblebee watcher service: monitors .bumblebee/ for external changes and syncs to FalkorDB (TICKET-823)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from app.graph import logic_queries as lq
from app.graph.client import get_graph
from app.services.persistence.deserializer import (
    DeserializationReport,
    _chunked_query,
    _collect_flow_edges,
    _prepare_flow_item,
    _prepare_node_item,
    _prepare_variable_item,
)

logger = logging.getLogger(__name__)

# Debounce interval in seconds
DEBOUNCE_INTERVAL = 0.3

# File checksums for change detection
_file_checksums: dict[str, str] = {}

# Background event loop reference for broadcasting
_event_loop: asyncio.AbstractEventLoop | None = None


class BumblebeeWatcher:
    """Watches a `.bumblebee/` directory for JSON file changes and syncs to FalkorDB.

    Monitors the nodes/, variables/, edges/, and flows/ subdirectories for
    external modifications (e.g. git pull) and applies them to the graph.
    The vfs/ subdirectory is ignored as it is output-only.

    Attributes:
        bumblebee_dir: Absolute path to the watched `.bumblebee/` directory.
    """

    def __init__(self, bumblebee_dir: str) -> None:
        self.bumblebee_dir = os.path.abspath(bumblebee_dir)
        self._observer: Any = None
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._running = False

    def start(self) -> None:
        """Start watching the .bumblebee/ directory for changes."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            watcher = self

            class Handler(FileSystemEventHandler):
                """Handle file system events for .bumblebee/ JSON files."""

                def on_modified(self, event: Any) -> None:
                    if not event.is_directory and event.src_path.endswith(".json"):
                        if watcher._should_watch(event.src_path):
                            watcher._debounce_sync(event.src_path)

                def on_created(self, event: Any) -> None:
                    if not event.is_directory and event.src_path.endswith(".json"):
                        if watcher._should_watch(event.src_path):
                            watcher._debounce_sync(event.src_path)

            self._observer = Observer()
            self._observer.schedule(Handler(), self.bumblebee_dir, recursive=True)
            self._observer.start()
            self._running = True
            logger.info("Bumblebee watcher started for: %s", self.bumblebee_dir)
        except ImportError:
            logger.warning("watchdog not installed - bumblebee watching disabled")
        except Exception:
            logger.exception("Failed to start bumblebee watcher")

    def stop(self) -> None:
        """Stop the bumblebee watcher."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._running = False
            logger.info("Bumblebee watcher stopped")

        # Cancel pending timers
        for timer in self._debounce_timers.values():
            timer.cancel()
        self._debounce_timers.clear()

    @property
    def is_running(self) -> bool:
        """Whether the watcher is currently active."""
        return self._running

    def _should_watch(self, file_path: str) -> bool:
        """Check whether a file path falls within a watched subdirectory.

        Ignores the vfs/ subdirectory which is output-only.

        Args:
            file_path: Absolute path to the changed file.

        Returns:
            True if the file should trigger a sync.
        """
        rel_path = os.path.relpath(file_path, self.bumblebee_dir)
        parts = Path(rel_path).parts

        if not parts:
            return False

        # Only watch nodes/, variables/, edges/, flows/
        watched_dirs = {"nodes", "variables", "edges", "flows"}
        return parts[0] in watched_dirs

    def _debounce_sync(self, file_path: str) -> None:
        """Debounce file change events before triggering sync.

        Args:
            file_path: Absolute path to the changed file.
        """
        if file_path in self._debounce_timers:
            self._debounce_timers[file_path].cancel()

        timer = threading.Timer(DEBOUNCE_INTERVAL, self._handle_change, args=[file_path])
        self._debounce_timers[file_path] = timer
        timer.start()

    def _handle_change(self, file_path: str) -> None:
        """Handle a file change after debouncing.

        Reads the changed JSON file, determines its type based on the
        subdirectory, and syncs the data to FalkorDB.

        Args:
            file_path: Absolute path to the changed file.
        """
        self._debounce_timers.pop(file_path, None)

        # Checksum comparison to avoid unnecessary re-syncs
        try:
            content = Path(file_path).read_text(encoding="utf-8")
            new_checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
            old_checksum = _file_checksums.get(file_path)

            if old_checksum == new_checksum:
                return

            _file_checksums[file_path] = new_checksum
        except OSError:
            return

        # Parse JSON
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Invalid JSON in %s: %s", file_path, exc)
            return

        # Determine subdirectory and dispatch
        rel_path = os.path.relpath(file_path, self.bumblebee_dir)
        parts = Path(rel_path).parts

        if not parts:
            return

        subdir = parts[0]

        try:
            graph = get_graph()
            report = DeserializationReport()

            if subdir == "nodes":
                self._sync_node(graph, data, report)
            elif subdir == "variables":
                self._sync_variables(graph, data, report)
            elif subdir == "edges":
                self._sync_edges(graph, data, report)
            elif subdir == "flows":
                self._sync_flow(graph, data, report)
            else:
                return

            logger.info(
                "Bumblebee sync (%s): %d nodes, %d vars, %d edges, %d flows, %d errors",
                rel_path,
                report.nodes_loaded,
                report.variables_loaded,
                report.edges_loaded,
                report.flows_loaded,
                len(report.errors),
            )

            if report.errors:
                for err in report.errors:
                    logger.warning("Sync error: %s", err)

            # Broadcast graph:updated event
            _broadcast_event("graph:updated", {"affected_modules": [rel_path]})

        except Exception:
            logger.exception("Failed to sync bumblebee file: %s", file_path)

    def _sync_node(self, graph: Any, data: dict[str, Any], report: DeserializationReport) -> None:
        """Sync a single LogicNode JSON file to the graph.

        Args:
            graph: FalkorDB graph instance.
            data: Parsed JSON data from a nodes/*.json file.
            report: Report to accumulate counts and errors.
        """
        item = _prepare_node_item(data)
        if item:
            _chunked_query(graph, lq.BATCH_MERGE_LOGIC_NODES, [item])
            report.nodes_loaded += 1

    def _sync_variables(self, graph: Any, data: dict[str, Any], report: DeserializationReport) -> None:
        """Sync a variables file to the graph using batch query.

        Args:
            graph: FalkorDB graph instance.
            data: Parsed JSON data from a variables/var_*.json file.
            report: Report to accumulate counts and errors.
        """
        items = []
        for var_data in data.get("variables", []):
            item = _prepare_variable_item(var_data)
            if item:
                items.append(item)
                report.variables_loaded += 1
        if items:
            _chunked_query(graph, lq.BATCH_MERGE_VARIABLES, items)

    def _sync_edges(self, graph: Any, data: dict[str, Any], report: DeserializationReport) -> None:
        """Sync an edges manifest file to the graph using batch queries.

        Args:
            graph: FalkorDB graph instance.
            data: Parsed JSON data from edges/manifest.json.
            report: Report to accumulate counts and errors.
        """
        edge_buckets: dict[str, list[dict[str, Any]]] = {}
        for edge_data in data.get("edges", []):
            edge_type = edge_data.get("type", "")
            source = edge_data.get("source", "")
            target = edge_data.get("target", "")
            if not edge_type or not source or not target:
                continue
            if edge_type not in lq.BATCH_EDGE_MERGE_QUERIES:
                continue
            props = edge_data.get("properties", {})
            item: dict[str, Any] = {"source_id": source, "target_id": target}
            item.update(props)
            edge_buckets.setdefault(edge_type, []).append(item)
            report.edges_loaded += 1
        for etype, items in edge_buckets.items():
            _chunked_query(graph, lq.BATCH_EDGE_MERGE_QUERIES[etype], items)

    def _sync_flow(self, graph: Any, data: dict[str, Any], report: DeserializationReport) -> None:
        """Sync a single Flow JSON file to the graph using batch queries.

        Args:
            graph: FalkorDB graph instance.
            data: Parsed JSON data from a flows/flow_*.json file.
            report: Report to accumulate counts and errors.
        """
        flow_item = _prepare_flow_item(data)
        if flow_item:
            _chunked_query(graph, lq.BATCH_MERGE_FLOWS, [flow_item])
            report.flows_loaded += 1
            step_of_items: list[dict[str, Any]] = []
            contains_flow_items: list[dict[str, Any]] = []
            _collect_flow_edges(data, step_of_items, contains_flow_items)
            if step_of_items:
                _chunked_query(graph, lq.BATCH_EDGE_MERGE_QUERIES["STEP_OF"], step_of_items)
            if contains_flow_items:
                _chunked_query(graph, lq.BATCH_EDGE_MERGE_QUERIES["CONTAINS_FLOW"], contains_flow_items)


def _broadcast_event(event: str, data: dict[str, Any]) -> None:
    """Broadcast a WebSocket event from the bumblebee watcher thread.

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
_watcher: BumblebeeWatcher | None = None


def start_bumblebee_watcher(
    bumblebee_dir: str,
    loop: asyncio.AbstractEventLoop | None = None,
) -> BumblebeeWatcher:
    """Start the global bumblebee watcher.

    Args:
        bumblebee_dir: Path to the `.bumblebee/` directory to watch.
        loop: Event loop for broadcasting WebSocket events.

    Returns:
        The BumblebeeWatcher instance.
    """
    global _watcher, _event_loop  # pylint: disable=global-statement  # Module-level singleton
    if loop is not None:
        _event_loop = loop

    if _watcher is not None:
        _watcher.stop()

    _watcher = BumblebeeWatcher(bumblebee_dir)
    _watcher.start()
    return _watcher


def stop_bumblebee_watcher() -> None:
    """Stop the global bumblebee watcher."""
    global _watcher  # pylint: disable=global-statement  # Module-level singleton
    if _watcher is not None:
        _watcher.stop()
        _watcher = None
