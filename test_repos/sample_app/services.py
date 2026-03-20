"""Business logic — orchestrates auth, repositories, and models."""

from __future__ import annotations

from auth import create_token, hash_password, verify_password
from models import Order, Product, User
from repository import LedgerRepository, OrderRepository, UserRepository
from services.auth_service import resolve_user_context
from services.event_bus import broadcast, dispatch_event, handle_comment_flagged
from services.ingestion_flow import enrich, parse_input, store_record
from services.data_pipeline import validate_row
from utils import audit_log, format_currency, generate_id, validate_email
from utils.text import count_words, format_notification, slugify

# Module-level singletons (simple DI for the sample)
user_repo = UserRepository()
order_repo = OrderRepository()


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


# Module-level ledger repository
ledger_repo = LedgerRepository()


# ---------------------------------------------------------------------------
# Chain 1: Notification Pipeline
# ---------------------------------------------------------------------------

def send_notification(session: dict, template: str, recipient: str, context: dict) -> dict:
    """Send a notification after resolving the user and formatting the message.

    Resolves the caller's identity, formats the notification body, dispatches
    the event, and records an audit trail.
    """
    user_ctx = resolve_user_context(session)
    message = format_notification(template, recipient, context)
    event_data = {"type": "notification", "message": message, "recipient": recipient}
    dispatch_event(event_data, [])
    audit_log("notification", user_ctx["user_id"], "send", recipient)
    return {"message": message, "status": "sent"}


# ---------------------------------------------------------------------------
# Chain 2: Payment Processing
# ---------------------------------------------------------------------------

def calculate_order_total(order: Order) -> float:
    """Calculate the total for an order, traversing items → products.

    Calls Order.total() which internally calls OrderItem.subtotal() which
    calls Product.discounted_price().
    """
    return order.total()


def process_payment(session: dict, order: Order) -> dict:
    """Process a payment for an order.

    Resolves user context, calculates the order total through the model chain,
    records a ledger entry, audits the transaction, and formats the amount.
    """
    user_ctx = resolve_user_context(session)
    total = calculate_order_total(order)
    ledger_repo.record_entry(user_ctx["user_id"], order.id, total)
    audit_log("payment", user_ctx["user_id"], "process", order.id)
    formatted = format_currency(total)
    return {"order_id": order.id, "total": formatted, "status": "processed"}


# ---------------------------------------------------------------------------
# Chain 3: User Onboarding
# ---------------------------------------------------------------------------

def send_welcome(user: User, emitter: object) -> dict:
    """Send a welcome notification and broadcast the onboarding event.

    Formats a welcome message using the notification formatter and
    broadcasts a user_onboarded event through the event bus.
    """
    message = format_notification(
        "Welcome {name}! {body}",
        user.full_name(),
        {"subject": "Welcome", "body": "Thanks for joining."},
    )
    broadcast(emitter, "user_onboarded", {"user_id": user.id, "message": message})
    return {"message": message, "broadcast": True}


# ---------------------------------------------------------------------------
# Chain 4: Content Moderation
# ---------------------------------------------------------------------------

def evaluate_content(text: str) -> dict:
    """Evaluate content for moderation by analysing word count and slug.

    Uses text utilities to measure the content and produce a normalised slug
    for indexing.
    """
    word_count = count_words(text)
    slug = slugify(text)
    flagged = word_count < 3 or word_count > 10000
    return {"slug": slug, "word_count": word_count, "flagged": flagged}


def flag_content(session: dict, content_text: str, content_id: str) -> dict:
    """Flag content for moderation review.

    Resolves the reporter's identity, evaluates the content, triggers
    the comment-flagged event handler, sends a notification, and audits.
    """
    user_ctx = resolve_user_context(session)
    evaluation = evaluate_content(content_text)
    handle_comment_flagged(None, None)
    notification = format_notification(
        "Content flagged by {name}: {subject}",
        user_ctx["user_id"],
        {"subject": content_id, "body": "Under review"},
    )
    audit_log("content", user_ctx["user_id"], "flag", content_id)
    return {"evaluation": evaluation, "notification": notification, "status": "flagged"}


# ---------------------------------------------------------------------------
# Chain 5: Report Generation
# ---------------------------------------------------------------------------

def generate_user_report(user: User, posts: list, comments: list) -> dict:
    """Generate a summary report for a user's activity.

    Summarises the user's posts and comments, formats currency totals,
    and records an audit entry.
    """
    from models.post_model import summarize_user_activity

    summary = summarize_user_activity(user, posts, comments)
    total_str = format_currency(summary.get("total_engagement", 0))
    audit_log("report", user.id, "generate", user.id)
    return {"summary": summary, "formatted_total": total_str}


# ---------------------------------------------------------------------------
# Chain 7: Bulk Data Import
# ---------------------------------------------------------------------------

def run_bulk_import(raw_data: str, db: object) -> dict:
    """Run a bulk data import pipeline.

    Parses the raw input, validates each row, enriches with metadata,
    and stores each record.
    """
    parsed = parse_input(raw_data)
    errors: list = []
    validate_row(parsed, errors)
    enriched = enrich(parsed)
    record_id = store_record(enriched, db)
    return {"record_id": record_id, "errors": errors}
