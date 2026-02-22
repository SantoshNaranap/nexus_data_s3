"""
Unit tests for input validation.
"""

import pytest

from app.core.validation import (
    Patterns,
    validate_session_id,
    validate_datasource,
    validate_message_length,
    sanitize_for_logging,
    check_sql_injection,
    check_xss,
    sanitize_html,
    ValidatedChatRequest,
    ValidatedCredentials,
    InputValidator,
)
from app.core.exceptions import ValidationError, InvalidDatasourceError


class TestPatterns:
    """Tests for regex patterns."""

    def test_session_id_pattern_valid(self):
        """Test valid session ID patterns."""
        valid_ids = [
            "abc12345",
            "a1b2c3d4-e5f6",
            "session-123-abc-456",
            "ABCD1234",
        ]
        for session_id in valid_ids:
            assert Patterns.SESSION_ID.match(session_id), f"Should match: {session_id}"

    def test_session_id_pattern_invalid(self):
        """Test invalid session ID patterns."""
        invalid_ids = [
            "short",  # Too short
            "has spaces here",
            "special@chars!",
            "../path/traversal",
        ]
        for session_id in invalid_ids:
            assert not Patterns.SESSION_ID.match(session_id), f"Should not match: {session_id}"

    def test_email_pattern(self):
        """Test email pattern matching."""
        valid_emails = [
            "test@example.com",
            "user.name@domain.org",
            "user+tag@example.co.uk",
        ]
        for email in valid_emails:
            assert Patterns.EMAIL.match(email), f"Should match: {email}"

        invalid_emails = [
            "not-an-email",
            "@missing-local.com",
            "missing-domain@",
            "spaces in@email.com",
        ]
        for email in invalid_emails:
            assert not Patterns.EMAIL.match(email), f"Should not match: {email}"


class TestValidationFunctions:
    """Tests for validation functions."""

    def test_validate_session_id_valid(self):
        """Test valid session ID validation."""
        assert validate_session_id("abc12345") is True
        assert validate_session_id("session-123-abc") is True
        assert validate_session_id(None) is True  # None is allowed
        assert validate_session_id("") is True  # Empty is allowed

    def test_validate_session_id_invalid(self):
        """Test invalid session ID validation."""
        with pytest.raises(ValidationError):
            validate_session_id("../../../etc/passwd")

        with pytest.raises(ValidationError):
            validate_session_id("has spaces")

    def test_validate_datasource_valid(self):
        """Test valid datasource validation."""
        assert validate_datasource("slack") is True
        assert validate_datasource("s3") is True
        assert validate_datasource("mysql") is True
        assert validate_datasource("jira") is True

    def test_validate_datasource_invalid(self):
        """Test invalid datasource validation."""
        with pytest.raises(InvalidDatasourceError) as exc_info:
            validate_datasource("unknown_source")
        assert "unknown_source" in str(exc_info.value.message)

    def test_validate_message_length_valid(self):
        """Test valid message length."""
        assert validate_message_length("Hello, world!") is True
        assert validate_message_length("A" * 1000) is True

    def test_validate_message_length_invalid(self):
        """Test invalid message length."""
        with pytest.raises(ValidationError):
            validate_message_length("A" * 100001)  # Default max is 100000

        with pytest.raises(ValidationError):
            validate_message_length("Too long", max_length=5)

    def test_sanitize_for_logging(self):
        """Test log message sanitization."""
        # Normal string
        assert sanitize_for_logging("Hello") == "Hello"

        # Long string truncation
        result = sanitize_for_logging("A" * 200, max_length=50)
        assert len(result) == 53  # 50 chars + "..."
        assert result.endswith("...")

        # Control characters removed
        result = sanitize_for_logging("Hello\x00World\x1f!")
        assert "\x00" not in result
        assert "\x1f" not in result

    def test_check_sql_injection(self):
        """Test SQL injection detection."""
        # Malicious patterns
        assert check_sql_injection("SELECT * FROM users") is True
        assert check_sql_injection("'; DROP TABLE users;--") is True
        assert check_sql_injection("1 OR 1=1") is False  # Simple OR not detected
        assert check_sql_injection("UNION SELECT password FROM users") is True

        # Safe patterns
        assert check_sql_injection("Hello, how are you?") is False
        assert check_sql_injection("Show me the users list") is False

    def test_check_xss(self):
        """Test XSS detection."""
        # Malicious patterns
        assert check_xss("<script>alert('xss')</script>") is True
        assert check_xss("javascript:void(0)") is True
        assert check_xss("<img onerror=alert(1)>") is True
        assert check_xss("<iframe src='evil.com'>") is True

        # Safe patterns
        assert check_xss("Hello, <b>world</b>!") is False  # Bold is ok
        assert check_xss("This is safe text") is False

    def test_sanitize_html(self):
        """Test HTML sanitization."""
        assert sanitize_html("<p>Hello</p>") == "Hello"
        assert sanitize_html("<script>evil()</script>") == "evil()"
        assert sanitize_html("No tags here") == "No tags here"
        assert sanitize_html("<a href='test'>Link</a>") == "Link"


class TestValidatedChatRequest:
    """Tests for ValidatedChatRequest model."""

    def test_valid_request(self):
        """Test valid chat request."""
        request = ValidatedChatRequest(
            message="Show me the channels",
            datasource="slack",
            session_id="abc12345678",
        )
        assert request.message == "Show me the channels"
        assert request.datasource == "slack"
        assert request.session_id == "abc12345678"

    def test_message_strip(self):
        """Test message whitespace stripping."""
        request = ValidatedChatRequest(
            message="  Hello world  ",
            datasource="slack",
        )
        assert request.message == "Hello world"

    def test_datasource_lowercase(self):
        """Test datasource is lowercased."""
        request = ValidatedChatRequest(
            message="Hello",
            datasource="SLACK",
        )
        assert request.datasource == "slack"

    def test_empty_message_rejected(self):
        """Test empty message is rejected."""
        with pytest.raises(ValueError):
            ValidatedChatRequest(message="", datasource="slack")

        with pytest.raises(ValueError):
            ValidatedChatRequest(message="   ", datasource="slack")

    def test_invalid_datasource_rejected(self):
        """Test invalid datasource is rejected."""
        with pytest.raises(ValueError):
            ValidatedChatRequest(message="Hello", datasource="invalid")

    def test_invalid_session_id_rejected(self):
        """Test invalid session ID is rejected."""
        with pytest.raises(ValueError):
            ValidatedChatRequest(
                message="Hello",
                datasource="slack",
                session_id="bad id",
            )

    def test_none_session_id_allowed(self):
        """Test None session ID is allowed."""
        request = ValidatedChatRequest(
            message="Hello",
            datasource="slack",
            session_id=None,
        )
        assert request.session_id is None


class TestValidatedCredentials:
    """Tests for ValidatedCredentials model."""

    def test_valid_credentials(self):
        """Test valid credentials."""
        creds = ValidatedCredentials(
            datasource="slack",
            credentials={
                "slack_bot_token": "xoxb-test",
                "slack_user_token": "xoxp-test",
            },
        )
        assert creds.datasource == "slack"
        assert len(creds.credentials) == 2

    def test_empty_credentials_rejected(self):
        """Test empty credentials dict is rejected."""
        with pytest.raises(ValueError):
            ValidatedCredentials(datasource="slack", credentials={})

    def test_invalid_datasource_rejected(self):
        """Test invalid datasource is rejected."""
        with pytest.raises(ValueError):
            ValidatedCredentials(
                datasource="invalid",
                credentials={"key": "value"},
            )


class TestInputValidator:
    """Tests for InputValidator service."""

    def test_validate_chat_request(self):
        """Test chat request validation."""
        validator = InputValidator()

        result = validator.validate_chat_request(
            message="Hello world",
            datasource="slack",
            session_id="abc12345678",
        )

        assert result["message"] == "Hello world"
        assert result["datasource"] == "slack"
        assert result["session_id"] == "abc12345678"

    def test_validate_chat_request_invalid(self):
        """Test invalid chat request raises ValidationError."""
        validator = InputValidator()

        with pytest.raises(ValidationError):
            validator.validate_chat_request(
                message="",
                datasource="slack",
            )

    def test_validate_credentials(self):
        """Test credentials validation."""
        validator = InputValidator()

        result = validator.validate_credentials(
            datasource="slack",
            credentials={"token": "test-token"},
        )

        assert result["datasource"] == "slack"
        assert result["credentials"]["token"] == "test-token"

    def test_sanitize_log_message(self):
        """Test log message sanitization through validator."""
        validator = InputValidator()

        result = validator.sanitize_log_message("A" * 200)
        assert len(result) <= 103  # 100 + "..."
