"""Custom exception classes for Bumblebee IDE."""

from __future__ import annotations


class BumblebeeError(Exception):
    """Base exception for all Bumblebee domain errors."""


class NodeNotFoundError(BumblebeeError):
    """Raised when a graph node cannot be found."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        super().__init__(f"Node not found: {node_id}")


class IndexingError(BumblebeeError):
    """Raised when file indexing fails."""


class GraphQueryError(BumblebeeError):
    """Raised when a graph query fails."""


class ParseError(BumblebeeError):
    """Raised when AST parsing fails."""


class ModelAdapterError(BumblebeeError):
    """Raised when an LLM model adapter fails."""


class ToolExecutionError(BumblebeeError):
    """Raised when a tool execution fails."""
