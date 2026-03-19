from __future__ import annotations

"""User model and user-related operations."""

from core.base_model import BaseModel


class User(BaseModel):
    """A user account with role-based access and activation state.

    Attributes:
        email: The user's email address.
        name: The user's display name.
        role: The user's current role (default "member").
        is_active: Whether the account is active.
        last_login: ISO-formatted timestamp of the last login, or empty string.
    """

    def __init__(self, email: str, name: str) -> None:
        """Initialize a new User.

        Args:
            email: The user's email address.
            name: The user's display name.
        """
        super().__init__()
        self.email: str = email
        self.name: str = name
        self.role: str = "member"
        self.is_active: bool = True
        self.last_login: str = ""

    def promote(self, new_role: str) -> None:
        """Promote the user to a new role.

        Args:
            new_role: The role to assign (e.g. "admin", "moderator").
        """
        self.role = new_role
        self.save()

    def deactivate(self) -> None:
        """Deactivate the user account, preventing future logins."""
        self.is_active = False
        self.save()


def get_active_users(users: list) -> list:
    """Return a list of emails for all active users.

    Args:
        users: A list of User instances to filter.

    Returns:
        A list of email strings for users where is_active is True.
    """
    result: list = []
    for user in users:
        if user.is_active:
            result.append(user.email)
    return result


def get_user_posts(user: object, posts: list) -> list:
    """Collect all posts authored by a given user.

    Args:
        user: A User instance whose id is matched against post author_id.
        posts: A list of Post-like objects with an author_id attribute.

    Returns:
        A list of posts belonging to the user.
    """
    matched: list = []
    for post in posts:
        if post.author_id == user.id:
            matched.append(post)
    return matched


def format_user_display(row: dict) -> str:
    """Format a user row for compact display.

    Args:
        row: A dict with at least "id" and "name" keys.

    Returns:
        A formatted string like "User #abc123: Alice".
    """
    user_id = row["id"]
    name = row["name"]
    if not name.strip():
        return f"User #{user_id}: (unnamed)"
    return f"User #{user_id}: {name}"


def format_user_email(row: dict) -> str:
    """Format a user row including their email address.

    Args:
        row: A dict with "id", "name", and "email" keys.

    Returns:
        A formatted string like "Alice <alice@example.com> (id: abc123)".
    """
    user_id = row["id"]
    name = row["name"]
    email = row["email"]
    if "@" not in email:
        return f"{name} <invalid-email> (id: {user_id})"
    return f"{name} <{email}> (id: {user_id})"


def build_user_profile(row: dict) -> dict:
    """Build a full user profile dictionary from a data row.

    Args:
        row: A dict with "id", "name", "email", and "age" keys.

    Returns:
        A profile dict with display_name, contact, and metadata fields.
    """
    user_id = row["id"]
    name = row["name"]
    email = row["email"]
    age = row["age"]

    display_name = name if name.strip() else "Anonymous"
    age_group = "minor" if age < 18 else "adult" if age < 65 else "senior"

    return {
        "id": user_id,
        "display_name": display_name,
        "contact": email,
        "age": age,
        "age_group": age_group,
    }


def serialize_user(data: dict) -> dict:
    """Serialize a user data dict into a transport-ready format.

    Args:
        data: A dict with "email", "name", and "role" keys.

    Returns:
        A dict with normalized fields suitable for JSON serialization.
    """
    email = data["email"]
    name = data["name"]
    role = data["role"]

    return {
        "email": email.lower().strip(),
        "name": name.strip(),
        "role": role if role in ("member", "admin", "moderator") else "member",
    }


def validate_user(data: dict) -> list:
    """Validate user data and return a list of error messages.

    Args:
        data: A dict with "email" and "name" keys, and an optional "role" key.

    Returns:
        A list of error message strings. Empty if the data is valid.
    """
    errors: list = []
    email = data["email"]
    name = data["name"]
    role = data.get("role", "member")

    if not email or "@" not in email:
        errors.append("Invalid email address")

    if not name or len(name.strip()) < 2:
        errors.append("Name must be at least 2 characters")

    allowed_roles = ("member", "admin", "moderator")
    if role not in allowed_roles:
        errors.append(f"Role must be one of {allowed_roles}")

    return errors
