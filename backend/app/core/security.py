"""Security utilities for session and ID generation."""

import re
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


def sanitize_for_llm(text: str, max_length: int = 10000) -> str:
    """
    Sanitize user input before including in LLM prompts.

    This helps prevent prompt injection attacks by:
    1. Removing control characters
    2. Escaping potential prompt delimiters
    3. Truncating to max length
    4. Normalizing whitespace

    Args:
        text: The user input to sanitize
        max_length: Maximum length of sanitized output

    Returns:
        Sanitized text safe for LLM prompt inclusion
    """
    if not text:
        return ""

    # Remove null bytes and most control characters (keep newlines, tabs)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # Escape sequences that could be interpreted as prompt delimiters
    # These patterns are commonly used in prompt injection attempts
    injection_patterns = [
        (r'```', '` ` `'),  # Code block delimiters
        (r'---+', '- - -'),  # Horizontal rules (often used as section breaks)
        (r'===+', '= = ='),  # Another common delimiter
        (r'\[INST\]', '[_INST_]'),  # Llama-style instruction tokens
        (r'\[/INST\]', '[/_INST_]'),
        (r'<<SYS>>', '<<_SYS_>>'),  # System prompt markers
        (r'<</SYS>>', '<</_SYS_>>'),
        (r'Human:', 'Human :'),  # Anthropic-style turn markers
        (r'Assistant:', 'Assistant :'),
        (r'System:', 'System :'),
        (r'USER:', 'USER :'),
        (r'ASSISTANT:', 'ASSISTANT :'),
    ]

    for pattern, replacement in injection_patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Normalize excessive whitespace (but preserve paragraph structure)
    text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces/tabs to single space
    text = re.sub(r'\n{4,}', '\n\n\n', text)  # Limit consecutive newlines

    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length] + "... [truncated]"

    return text.strip()


def escape_for_json_in_prompt(text: str) -> str:
    """
    Escape text that will be embedded in JSON within a prompt.

    Args:
        text: Text to escape

    Returns:
        JSON-safe escaped text
    """
    if not text:
        return ""

    # Escape backslashes first, then quotes
    text = text.replace('\\', '\\\\')
    text = text.replace('"', '\\"')
    text = text.replace('\n', '\\n')
    text = text.replace('\r', '\\r')
    text = text.replace('\t', '\\t')

    return text
