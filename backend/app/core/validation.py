"""
Input validation utilities for ConnectorMCP.

Provides validation for user inputs to prevent security issues
and ensure data integrity.
"""

import re
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.enums import DataSourceType, Limits
from app.core.exceptions import ValidationError, InvalidDatasourceError


# ============ Regex Patterns ============


class Patterns:
    """Compiled regex patterns for validation."""

    # Session ID: UUID format or alphanumeric with dashes
    SESSION_ID = re.compile(r"^[a-zA-Z0-9\-]{8,64}$")

    # Safe filename pattern (no path traversal)
    SAFE_FILENAME = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

    # SQL injection patterns to detect
    SQL_INJECTION = re.compile(
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|TRUNCATE)\b.*\b(FROM|INTO|TABLE|WHERE)\b)|"
        r"(--|;|\/\*|\*\/|@@|@)",
        re.IGNORECASE,
    )

    # XSS patterns to detect
    XSS_PATTERNS = re.compile(
        r"(<script|javascript:|on\w+\s*=|<iframe|<object|<embed)",
        re.IGNORECASE,
    )

    # Email pattern
    EMAIL = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


# ============ Validation Functions ============


def validate_session_id(session_id: str) -> bool:
    """
    Validate session ID format.

    Args:
        session_id: The session ID to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If invalid
    """
    if not session_id:
        return True  # None/empty is allowed (will be generated)

    if not Patterns.SESSION_ID.match(session_id):
        raise ValidationError(
            message="Invalid session ID format",
            details={"session_id": session_id[:20] + "..." if len(session_id) > 20 else session_id},
        )
    return True


def validate_datasource(datasource: str) -> bool:
    """
    Validate datasource is a known type.

    Args:
        datasource: The datasource identifier

    Returns:
        True if valid

    Raises:
        InvalidDatasourceError: If invalid
    """
    if not DataSourceType.is_valid(datasource):
        raise InvalidDatasourceError(
            datasource=datasource,
            details={"valid_datasources": list(DataSourceType.values())},
        )
    return True


def validate_message_length(message: str, max_length: int = Limits.MAX_MESSAGE_LENGTH) -> bool:
    """
    Validate message doesn't exceed maximum length.

    Args:
        message: The message to validate
        max_length: Maximum allowed length

    Returns:
        True if valid

    Raises:
        ValidationError: If too long
    """
    if len(message) > max_length:
        raise ValidationError(
            message=f"Message exceeds maximum length of {max_length} characters",
            details={"length": len(message), "max_length": max_length},
        )
    return True


def sanitize_for_logging(value: str, max_length: int = 100) -> str:
    """
    Sanitize a value for safe logging.

    Args:
        value: Value to sanitize
        max_length: Maximum length to include

    Returns:
        Sanitized string safe for logging
    """
    if not value:
        return ""

    # Truncate if needed
    if len(value) > max_length:
        value = value[:max_length] + "..."

    # Remove control characters
    value = "".join(c if c.isprintable() else "?" for c in value)

    return value


def check_sql_injection(value: str) -> bool:
    """
    Check if a value contains potential SQL injection patterns.

    Args:
        value: The value to check

    Returns:
        True if suspicious patterns detected
    """
    return bool(Patterns.SQL_INJECTION.search(value))


def check_xss(value: str) -> bool:
    """
    Check if a value contains potential XSS patterns.

    Args:
        value: The value to check

    Returns:
        True if suspicious patterns detected
    """
    return bool(Patterns.XSS_PATTERNS.search(value))


def sanitize_html(value: str) -> str:
    """
    Remove HTML tags from a string.

    Args:
        value: The string to sanitize

    Returns:
        String with HTML tags removed
    """
    return re.sub(r"<[^>]+>", "", value)


# ============ Pydantic Models with Validation ============


class ValidatedChatRequest(BaseModel):
    """Validated chat request model."""

    message: str = Field(..., min_length=1, max_length=Limits.MAX_MESSAGE_LENGTH)
    datasource: str = Field(..., min_length=1, max_length=50)
    session_id: Optional[str] = Field(None, min_length=8, max_length=64)

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate and sanitize message."""
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")

        # Check for potential injection attacks (log but don't block)
        if check_sql_injection(v):
            # Log suspicious input but allow it through
            # The actual SQL execution is parameterized
            pass

        return v

    @field_validator("datasource")
    @classmethod
    def validate_datasource(cls, v: str) -> str:
        """Validate datasource is known."""
        v = v.strip().lower()
        if not DataSourceType.is_valid(v):
            raise ValueError(f"Invalid datasource: {v}")
        return v

    @field_validator("session_id")
    @classmethod
    def validate_session(cls, v: Optional[str]) -> Optional[str]:
        """Validate session ID format."""
        if v is None:
            return None
        v = v.strip()
        if not Patterns.SESSION_ID.match(v):
            raise ValueError("Invalid session ID format")
        return v


class ValidatedCredentials(BaseModel):
    """Validated credentials model."""

    datasource: str = Field(..., min_length=1, max_length=50)
    credentials: Dict[str, str]

    @field_validator("datasource")
    @classmethod
    def validate_datasource(cls, v: str) -> str:
        """Validate datasource is known."""
        v = v.strip().lower()
        if not DataSourceType.is_valid(v):
            raise ValueError(f"Invalid datasource: {v}")
        return v

    @field_validator("credentials")
    @classmethod
    def validate_credentials(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Validate credential fields."""
        if not v:
            raise ValueError("Credentials cannot be empty")

        # Validate each credential value
        for key, value in v.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError("Credential keys and values must be strings")
            if len(key) > 100:
                raise ValueError(f"Credential key too long: {key[:20]}...")
            if len(value) > 10000:
                raise ValueError(f"Credential value too long for: {key}")

        return v


class ValidatedToolCall(BaseModel):
    """Validated tool call model."""

    tool: str = Field(..., min_length=1, max_length=100)
    args: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("tool")
    @classmethod
    def validate_tool_name(cls, v: str) -> str:
        """Validate tool name format."""
        v = v.strip()
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", v):
            raise ValueError(f"Invalid tool name: {v}")
        return v


# ============ Request Validation Middleware ============


class InputValidator:
    """
    Central input validation service.

    Validates and sanitizes all user inputs before processing.
    """

    def __init__(self):
        self.blocked_patterns: Set[str] = set()

    def validate_chat_request(
        self,
        message: str,
        datasource: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate a chat request.

        Args:
            message: The chat message
            datasource: The datasource identifier
            session_id: Optional session ID

        Returns:
            Dict with validated values

        Raises:
            ValidationError: If validation fails
        """
        try:
            validated = ValidatedChatRequest(
                message=message,
                datasource=datasource,
                session_id=session_id,
            )
            return validated.model_dump()
        except Exception as e:
            raise ValidationError(
                message=f"Invalid request: {str(e)}",
                details={"field": "chat_request"},
            )

    def validate_credentials(
        self,
        datasource: str,
        credentials: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Validate credentials submission.

        Args:
            datasource: The datasource identifier
            credentials: The credentials dict

        Returns:
            Dict with validated values

        Raises:
            ValidationError: If validation fails
        """
        try:
            validated = ValidatedCredentials(
                datasource=datasource,
                credentials=credentials,
            )
            return validated.model_dump()
        except Exception as e:
            raise ValidationError(
                message=f"Invalid credentials: {str(e)}",
                details={"field": "credentials"},
            )

    def sanitize_log_message(self, message: str) -> str:
        """Sanitize message for safe logging."""
        return sanitize_for_logging(message)


# Global validator instance
validator = InputValidator()


def get_validator() -> InputValidator:
    """Get the global validator instance."""
    return validator
