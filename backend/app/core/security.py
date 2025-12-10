"""Security utilities for session and ID generation."""

import secrets
import uuid
from typing import Optional


def generate_session_id(prefix: Optional[str] = None) -> str:
    """
    Generate a cryptographically secure session ID.

    Uses secrets.token_urlsafe which is recommended for security-sensitive tokens.
    This is more secure than uuid.uuid4() as it uses the OS's cryptographic random generator.

    Args:
        prefix: Optional prefix for the session ID (e.g., "agent_jira_")

    Returns:
        A URL-safe base64-encoded 32-byte random string (43 chars without prefix)
    """
    token = secrets.token_urlsafe(32)
    if prefix:
        return f"{prefix}{token[:16]}"  # Shorten when prefixed
    return token


def generate_db_id() -> str:
    """
    Generate a UUID for database primary keys.

    Uses uuid.uuid4() which is standard for database IDs.
    This is appropriate for IDs that don't need to be unpredictable.

    Returns:
        A string representation of a UUID4
    """
    return str(uuid.uuid4())
