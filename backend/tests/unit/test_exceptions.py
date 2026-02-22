"""
Unit tests for custom exceptions.
"""

import pytest

from app.core.exceptions import (
    AppError,
    ErrorCode,
    AuthenticationError,
    TokenMissingError,
    TokenInvalidError,
    TokenExpiredError,
    UserNotFoundError,
    ValidationError,
    InvalidDatasourceError,
    MissingCredentialsError,
    ToolExecutionError,
    MCPConnectionError,
    RateLimitError,
    AnthropicRateLimitError,
    DatabaseError,
)


class TestAppError:
    """Tests for base AppError class."""

    def test_app_error_creation(self):
        """Test basic AppError creation."""
        error = AppError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Test error",
            details={"key": "value"},
            http_status=500,
        )

        assert error.code == ErrorCode.INTERNAL_ERROR
        assert error.message == "Test error"
        assert error.details == {"key": "value"}
        assert error.http_status == 500
        assert str(error) == "Test error"

    def test_app_error_to_dict(self):
        """Test AppError to_dict conversion."""
        error = AppError(
            code=ErrorCode.VALIDATION_ERROR,
            message="Invalid input",
            details={"field": "email"},
        )

        result = error.to_dict(include_details=False)
        assert result == {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid input",
            }
        }

        result_with_details = error.to_dict(include_details=True)
        assert result_with_details["error"]["details"] == {"field": "email"}


class TestAuthenticationErrors:
    """Tests for authentication errors."""

    def test_token_missing_error(self):
        """Test TokenMissingError."""
        error = TokenMissingError()
        assert error.code == ErrorCode.AUTH_TOKEN_MISSING
        assert error.http_status == 401
        assert "required" in error.message.lower()

    def test_token_invalid_error(self):
        """Test TokenInvalidError."""
        error = TokenInvalidError(details={"reason": "malformed"})
        assert error.code == ErrorCode.AUTH_TOKEN_INVALID
        assert error.http_status == 401
        assert error.details["reason"] == "malformed"

    def test_token_expired_error(self):
        """Test TokenExpiredError."""
        error = TokenExpiredError()
        assert error.code == ErrorCode.AUTH_TOKEN_EXPIRED
        assert error.http_status == 401
        assert "expired" in error.message.lower()

    def test_user_not_found_error(self):
        """Test UserNotFoundError."""
        error = UserNotFoundError(user_id="user-123")
        assert error.code == ErrorCode.AUTH_USER_NOT_FOUND
        assert error.http_status == 401
        assert error.details["user_id"] == "user-123"


class TestValidationErrors:
    """Tests for validation errors."""

    def test_validation_error(self):
        """Test basic ValidationError."""
        error = ValidationError(
            message="Invalid format",
            details={"field": "email", "reason": "not an email"},
        )
        assert error.code == ErrorCode.VALIDATION_ERROR
        assert error.http_status == 400

    def test_invalid_datasource_error(self):
        """Test InvalidDatasourceError."""
        error = InvalidDatasourceError(datasource="unknown")
        assert error.code == ErrorCode.INVALID_DATASOURCE
        assert error.http_status == 400
        assert "unknown" in error.message
        assert error.details["datasource"] == "unknown"

    def test_missing_credentials_error(self):
        """Test MissingCredentialsError."""
        error = MissingCredentialsError(datasource="slack")
        assert error.code == ErrorCode.MISSING_CREDENTIALS
        assert error.http_status == 400
        assert "slack" in error.message


class TestExternalServiceErrors:
    """Tests for external service errors."""

    def test_tool_execution_error(self):
        """Test ToolExecutionError."""
        error = ToolExecutionError(
            tool_name="list_channels",
            original_error="Connection refused",
        )
        assert error.code == ErrorCode.TOOL_EXECUTION_ERROR
        assert error.http_status == 502
        assert "list_channels" in error.message
        assert error.details["tool_name"] == "list_channels"
        assert error.details["original_error"] == "Connection refused"

    def test_mcp_connection_error(self):
        """Test MCPConnectionError."""
        error = MCPConnectionError(datasource="slack")
        assert error.code == ErrorCode.MCP_CONNECTION_ERROR
        assert error.http_status == 502
        assert "slack" in error.message


class TestRateLimitErrors:
    """Tests for rate limit errors."""

    def test_rate_limit_error(self):
        """Test basic RateLimitError."""
        error = RateLimitError(
            message="Too many requests",
            retry_after=60,
        )
        assert error.code == ErrorCode.RATE_LIMIT_EXCEEDED
        assert error.http_status == 429
        assert error.retry_after == 60
        assert error.details["retry_after_seconds"] == 60

    def test_anthropic_rate_limit_error(self):
        """Test AnthropicRateLimitError."""
        error = AnthropicRateLimitError(retry_after=30)
        assert error.code == ErrorCode.ANTHROPIC_RATE_LIMIT
        assert error.http_status == 429
        assert error.retry_after == 30


class TestDatabaseErrors:
    """Tests for database errors."""

    def test_database_error(self):
        """Test DatabaseError."""
        error = DatabaseError(
            operation="INSERT",
            details={"table": "users"},
        )
        assert error.code == ErrorCode.DATABASE_ERROR
        assert error.http_status == 500
        assert error.details["operation"] == "INSERT"
