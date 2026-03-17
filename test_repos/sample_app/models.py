"""Domain models for the sample application."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Product:
    """A product in the catalog."""

    id: str
    name: str
    price: float
    discount_pct: float = 0.0

    def discounted_price(self) -> float:
        """Calculate the price after discount."""
        return self.price * (1 - self.discount_pct)


@dataclass
class OrderItem:
    """A single item within an order."""

    product: Product
    quantity: int

    def subtotal(self) -> float:
        """Calculate subtotal for this line item."""
        return self.product.discounted_price() * self.quantity


@dataclass
class Order:
    """A customer order containing line items."""

    id: str
    user_id: str
    items: list[OrderItem] = field(default_factory=list)
    status: str = "pending"

    def add_item(self, product: Product, quantity: int = 1) -> None:
        """Add a product to the order."""
        self.items.append(OrderItem(product=product, quantity=quantity))

    def total(self) -> float:
        """Calculate the total price of all items."""
        return sum(item.subtotal() for item in self.items)


@dataclass
class User:
    """A registered user."""

    id: str
    first_name: str
    last_name: str
    email: str
    hashed_password: str = ""
    active: bool = True

    def full_name(self) -> str:
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}"

    def is_active(self) -> bool:
        """Check if the user account is active."""
        return self.active


class BaseRepository:
    """Abstract base for all repositories."""

    def _validate_id(self, entity_id: str) -> None:
        """Ensure the ID is non-empty."""
        if not entity_id:
            raise ValueError("ID must not be empty")
