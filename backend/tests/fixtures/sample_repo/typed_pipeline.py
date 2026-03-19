"""Functions with diverse variable types for TypeShape testing."""


# --- Dict with string keys (subscript access) ---


def extract_user_emails(users: list, user: dict) -> list:
    """Extract emails from user dicts."""
    emails = []
    name = user["name"]
    email = user["email"]
    emails.append(email)
    return emails


def send_notification(user: dict, message: str) -> bool:
    """Send notification — same subscript shape as extract_user_emails."""
    addr = user["email"]
    name = user["name"]
    return True


def enrich_user(user: dict) -> dict:
    """Superset — accesses name, email, AND phone."""
    display = user["name"]
    contact = user["email"]
    phone = user["phone"]
    return {"display": display, "contact": contact, "phone": phone}


# --- Custom object (attribute access) ---


def format_response(response) -> str:
    """Access attrs on an HTTP-like response object."""
    code = response.status_code
    body = response.text
    return f"{code}: {body}"


def log_response(response) -> None:
    """Same attrs as format_response — should share TypeShape."""
    print(response.status_code)
    print(response.text)


# --- Collection (method calls) ---


def batch_process(items: list, results: list) -> None:
    """Uses append and extend on a list."""
    results.append(items[0])
    results.extend(items[1:])


# --- Typed primitives ---


def double(value: int) -> int:
    """Hint-based shape: int → int."""
    return value * 2


def increment(n: int) -> int:
    """Same hint-based shape as double."""
    return n + 1


# --- DB-like object (method calls as shape) ---


def run_query(conn, sql: str) -> list:
    """DB connection — shape from method calls."""
    cursor = conn.cursor()
    cursor.execute(sql)
    return cursor.fetchall()


def run_insert(conn, sql: str) -> None:
    """Same conn shape — cursor() + execute()."""
    cursor = conn.cursor()
    cursor.execute(sql)
    conn.commit()


# --- No evidence (opaque) ---


def identity(x):
    """No type hint, no attribute/subscript/method access. No TypeShape created."""
    return x
