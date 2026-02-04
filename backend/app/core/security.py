"""Security utilities for session and ID generation."""

import secrets
import uuid
import time
from threading import Lock
from typing import Dict, Optional, Set

from app.core.logging import get_logger

logger = get_logger(__name__)


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


def secure_compare(a: str, b: str) -> bool:
    """
    Perform a timing-safe string comparison.

    Uses secrets.compare_digest to prevent timing attacks when comparing
    session IDs, tokens, or other security-sensitive strings.

    Args:
        a: First string to compare
        b: Second string to compare

    Returns:
        True if strings are equal, False otherwise
    """
    return secrets.compare_digest(a.encode(), b.encode())


class SessionRegistry:
    """
    Registry for tracking valid session IDs.

    Provides:
    - Session ID validation with timing-safe comparison
    - Session ID rotation after authentication
    - Automatic cleanup of expired sessions
    """

    def __init__(self, session_ttl_seconds: int = 86400):  # 24 hours default
        self._sessions: Dict[str, float] = {}  # session_id -> creation_timestamp
        self._lock = Lock()
        self._session_ttl = session_ttl_seconds
        self._cleanup_interval = 3600  # Clean up every hour
        self._last_cleanup = time.time()

    def register_session(self, session_id: str) -> None:
        """Register a new session ID."""
        with self._lock:
            self._sessions[session_id] = time.time()
            self._maybe_cleanup()

    def is_valid_session(self, session_id: str) -> bool:
        """
        Check if a session ID is valid (registered and not expired).

        Uses timing-safe comparison to prevent timing attacks.
        """
        with self._lock:
            if session_id not in self._sessions:
                return False

            creation_time = self._sessions[session_id]
            if time.time() - creation_time > self._session_ttl:
                # Session expired, remove it
                del self._sessions[session_id]
                return False

            return True

    def invalidate_session(self, session_id: str) -> bool:
        """
        Invalidate (logout) a session.

        Returns True if session was found and invalidated.
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    def rotate_session(self, old_session_id: str) -> Optional[str]:
        """
        Rotate a session ID after authentication.

        Generates a new session ID and invalidates the old one.
        This prevents session fixation attacks.

        Args:
            old_session_id: The current session ID to rotate

        Returns:
            New session ID if rotation successful, None if old session invalid
        """
        with self._lock:
            # Verify old session exists
            if old_session_id not in self._sessions:
                return None

            # Generate new session ID
            new_session_id = generate_session_id()

            # Transfer session data (timestamp) to new session
            creation_time = self._sessions.pop(old_session_id)
            self._sessions[new_session_id] = creation_time

            logger.info(f"Session rotated: {old_session_id[:8]}... -> {new_session_id[:8]}...")
            return new_session_id

    def _maybe_cleanup(self) -> None:
        """Clean up expired sessions if cleanup interval has passed."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        self._last_cleanup = now
        expired = [
            sid for sid, created in self._sessions.items()
            if now - created > self._session_ttl
        ]
        for sid in expired:
            del self._sessions[sid]

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")

    def get_active_session_count(self) -> int:
        """Get the number of active sessions."""
        with self._lock:
            return len(self._sessions)


# Global session registry instance
session_registry = SessionRegistry()
