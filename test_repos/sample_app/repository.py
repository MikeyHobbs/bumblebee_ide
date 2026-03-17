"""Data access layer — in-memory repositories for the sample app."""

from __future__ import annotations

from models import BaseRepository, Order, User


class UserRepository(BaseRepository):
    """Stores and retrieves User objects."""

    def __init__(self) -> None:
        self._store: dict[str, User] = {}

    def get_by_id(self, user_id: str) -> User | None:
        """Fetch a user by their ID."""
        self._validate_id(user_id)
        return self._store.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        """Fetch a user by email address."""
        for user in self._store.values():
            if user.email == email:
                return user
        return None

    def save(self, user: User) -> User:
        """Persist a user (insert or update)."""
        self._validate_id(user.id)
        self._store[user.id] = user
        return user

    def delete(self, user_id: str) -> bool:
        """Remove a user by ID. Returns True if deleted."""
        self._validate_id(user_id)
        return self._store.pop(user_id, None) is not None

    def list_all(self) -> list[User]:
        """Return all stored users."""
        return list(self._store.values())


class OrderRepository(BaseRepository):
    """Stores and retrieves Order objects."""

    def __init__(self) -> None:
        self._store: dict[str, Order] = {}

    def get_by_id(self, order_id: str) -> Order | None:
        """Fetch an order by its ID."""
        self._validate_id(order_id)
        return self._store.get(order_id)

    def save(self, order: Order) -> Order:
        """Persist an order."""
        self._validate_id(order.id)
        self._store[order.id] = order
        return order

    def find_by_user(self, user_id: str) -> list[Order]:
        """Return all orders belonging to a user."""
        return [o for o in self._store.values() if o.user_id == user_id]
