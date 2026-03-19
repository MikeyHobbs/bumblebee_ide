"""Event emission, message routing, and handler management."""

from __future__ import annotations

import hashlib
import time

from core.base_model import Event
from models.user_model import User
from models.post_model import Post, Comment


# ---------------------------------------------------------------------------
# Event attribute access patterns
# ---------------------------------------------------------------------------

def log_event(event: Event) -> None:
    """Log an event's name and data payload to stdout."""
    name = event.name
    data = event.data
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] EVENT {name}: {data}")


def log_event_verbose(event: Event) -> str:
    """Return a verbose log string including source and timestamp."""
    name = event.name
    data = event.data
    source = event.source
    timestamp = event.timestamp
    return f"[{timestamp}] {source} -> {name}: {data}"


def is_high_priority(event: Event) -> bool:
    """Return True if the event priority exceeds the critical threshold."""
    priority = event.priority
    name = event.name
    if priority >= 9:
        return True
    if priority >= 7 and name.startswith("system."):
        return True
    return False


def event_fingerprint(event: Event) -> str:
    """Produce a deterministic fingerprint from all event fields."""
    name = event.name
    data = str(event.data)
    source = event.source
    timestamp = str(event.timestamp)
    priority = str(event.priority)
    raw = f"{name}|{data}|{source}|{timestamp}|{priority}"
    return hashlib.sha256(raw.encode()).hexdigest()


def dispatch_event(event: Event, handlers: list) -> int:
    """Dispatch an event to all matching handlers. Returns count dispatched."""
    name = event.name
    data = event.data
    handled = event.handled
    if handled:
        return 0
    count = 0
    for handler in handlers:
        try:
            handler(name, data)
            count += 1
        except Exception:
            continue
    return count


# ---------------------------------------------------------------------------
# Domain event handlers (cross-module calls)
# ---------------------------------------------------------------------------

def handle_user_created(event: Event, user: User) -> None:
    """Process a user-created event and persist the new user."""
    event_type = event.type
    payload = event.payload
    if event_type != "user.created":
        return
    user.name = payload.get("name", user.name)
    user.save()


def handle_post_published(event: Event, post: Post) -> None:
    """Process a post-published event: publish then persist."""
    event_type = event.type
    payload = event.payload
    if event_type != "post.published":
        return
    post.title = payload.get("title", post.title)
    post.publish()
    post.save()


def handle_comment_flagged(event: Event, comment: Comment) -> None:
    """Process a comment-flagged event: flag and persist."""
    event_type = event.type
    payload = event.payload
    if event_type != "comment.flagged":
        return
    reason = payload.get("reason", "unspecified")
    comment.flag(reason)
    comment.save()


# ---------------------------------------------------------------------------
# Emitter method patterns
# ---------------------------------------------------------------------------

def setup_logging_emitter(emitter) -> None:
    """Attach persistent and one-shot logging listeners to the emitter."""
    def _on_event(name, data):
        print(f"[emitter] {name}: {data}")

    def _once_ready(name, data):
        print(f"[emitter:once] ready — {name}")

    emitter.on("*", _on_event)
    emitter.once("ready", _once_ready)


def teardown_emitter(emitter) -> None:
    """Remove all listeners from the emitter."""
    emitter.off("*")


def broadcast(emitter, event_name: str, data: dict) -> None:
    """Emit a named event with the supplied data dict."""
    emitter.emit(event_name, data)


# ---------------------------------------------------------------------------
# Message dict subscript patterns
# ---------------------------------------------------------------------------

def route_message(message: dict) -> str:
    """Route a message based on its topic, returning the destination queue."""
    topic = message["topic"]
    body = message["body"]
    if topic.startswith("urgent."):
        return f"priority_queue:{topic}"
    return f"default_queue:{topic}"


def route_with_headers(message: dict) -> str:
    """Route a message, taking headers into account for priority."""
    topic = message["topic"]
    body = message["body"]
    headers = message["headers"]
    priority = headers.get("X-Priority", "normal")
    if priority == "high":
        return f"priority_queue:{topic}"
    return f"standard_queue:{topic}"


def reply_to_message(message: dict) -> dict:
    """Create an acknowledgment reply for the given message."""
    topic = message["topic"]
    body = message["body"]
    reply_to = message["reply_to"]
    return {
        "topic": reply_to,
        "body": f"ACK: {body[:50]}",
        "reply_to": topic,
        "timestamp": time.time(),
    }


def full_message_summary(message: dict) -> str:
    """Summarize every field of a message into a single string."""
    topic = message["topic"]
    body = message["body"]
    headers = message["headers"]
    reply_to = message["reply_to"]
    header_count = len(headers) if isinstance(headers, dict) else 0
    return (
        f"topic={topic} reply_to={reply_to} "
        f"headers={header_count} body_len={len(body)}"
    )


# ---------------------------------------------------------------------------
# Handler registry collection patterns
# ---------------------------------------------------------------------------

def add_handler(registry: list, handler) -> None:
    """Append a handler to the registry list."""
    registry.append(handler)


def remove_handler(registry: list, handler) -> None:
    """Remove the first occurrence of *handler* from the registry."""
    registry.remove(handler)


def clear_handlers(registry: list) -> None:
    """Remove all handlers from the registry."""
    registry.clear()
