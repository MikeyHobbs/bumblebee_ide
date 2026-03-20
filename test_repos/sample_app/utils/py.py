def validate_email(email: str) -> bool:
    """Check whether an email address looks valid."""
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email))


def generate_id() -> str:
    """Generate a new UUID-4 string."""
    return str(uuid.uuid4())


def format_currency(amount: float) -> str:
    """Format a numeric amount as a USD currency string."""
    return f"${amount:,.2f}"


def paginate(items: list, page: int, size: int) -> list:
    """Return a slice of items for the given page number and page size."""
    start = (page - 1) * size
    return items[start : start + size]


def audit_log(entity_type: str, actor_id: str, action: str, target_id: str) -> dict:
    """Record an audit trail entry for any entity mutation.

    Generates a unique event ID and returns the full audit record.
    Called by every top-level handler chain to ensure traceability.
    """
    event_id = generate_id()
    return {
        "event_id": event_id,
        "entity_type": entity_type,
        "actor_id": actor_id,
        "action": action,
        "target_id": target_id,
    }
