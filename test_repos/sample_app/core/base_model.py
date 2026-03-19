from __future__ import annotations

"""Base model and event types for the sample application."""

import time


class BaseModel:
    """Base class for all persistent models in the application.

    Provides common fields (id, created_at, updated_at) and lifecycle
    methods for saving, deleting, and refreshing model instances.
    """

    def __init__(self) -> None:
        self.id: str = ""
        self.created_at: str = ""
        self.updated_at: str = ""

    def save(self) -> bool:
        """Persist the current model instance.

        Returns:
            True if the save succeeded, False otherwise.
        """
        if not self.id:
            return False
        self.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return True

    def delete(self) -> bool:
        """Delete the current model instance.

        Returns:
            True if the deletion succeeded, False if the model has no id.
        """
        if not self.id:
            return False
        self.id = ""
        self.created_at = ""
        self.updated_at = ""
        return True

    def refresh(self) -> None:
        """Reload the model data from the backing store.

        Sets updated_at to the current time to reflect the refresh.
        """
        if not self.id:
            return
        self.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Event:
    """Represents a domain event emitted by the application."""

    def __init__(self, name: str, data: dict) -> None:
        self.name: str = name
        self.data: dict = data
        self.source: str = ""
        self.timestamp: str = ""
        self.priority: int = 0
        self.handled: bool = False
