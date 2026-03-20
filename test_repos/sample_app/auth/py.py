def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with a random salt."""
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{digest}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a stored hash."""
    parts = hashed.split(":")
    if len(parts) != 2:
        return False
    salt, expected_digest = parts
    actual_digest = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return hmac.compare_digest(actual_digest, expected_digest)


def create_token(user: User) -> str:
    """Create a simple session token for a user."""
    payload = f"{user.id}:{user.email}:{secrets.token_hex(8)}"
    signature = hashlib.sha256(f"{SECRET_KEY}{payload}".encode()).hexdigest()
    return f"{payload}:{signature}"


def validate_token(token: str) -> User | None:
    """Validate a token and return the associated user stub, or None."""
    parts = token.split(":")
    if len(parts) < 4:
        return None
    user_id, email = parts[0], parts[1]
    # In a real app this would look up the user from a database
    return User(id=user_id, first_name="", last_name="", email=email)
