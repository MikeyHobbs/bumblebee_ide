def register_user(first_name: str, last_name: str, email: str, password: str) -> User:
    """Register a new user account.

    Validates the email, hashes the password, and stores the user.
    """
    if not validate_email(email):
        raise ValueError(f"Invalid email: {email}")

    existing = user_repo.get_by_email(email)
    if existing is not None:
        raise ValueError("Email already registered")

    user = User(
        id=generate_id(),
        first_name=first_name,
        last_name=last_name,
        email=email,
        hashed_password=hash_password(password),
    )
    return user_repo.save(user)


def authenticate(email: str, password: str) -> str | None:
    """Authenticate a user and return a session token, or None on failure."""
    user = user_repo.get_by_email(email)
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return create_token(user)


def place_order(user_id: str, items: list[tuple[Product, int]]) -> Order:
    """Create a new order for a user with the given product/quantity pairs."""
    user = user_repo.get_by_id(user_id)
    if user is None:
        raise ValueError(f"User not found: {user_id}")
    if not user.is_active():
        raise ValueError("Inactive users cannot place orders")

    order = Order(id=generate_id(), user_id=user_id)
    for product, qty in items:
        order.add_item(product, qty)

    return order_repo.save(order)


def get_user_orders(user_id: str) -> list[Order]:
    """Retrieve all orders for a user."""
    return order_repo.find_by_user(user_id)
