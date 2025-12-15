"""
Custom exception hierarchy for ConnectorMCP.

Provides structured error handling with error codes, user-friendly messages,
and proper HTTP status code mapping.
"""

from typing import Any, Dict, Optional
from enum import Enum


class ErrorCode(str, Enum):
    """Error codes for categorizing exceptions."""

    # Authentication errors (401)
    AUTH_TOKEN_MISSING = "AUTH_TOKEN_MISSING"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    AUTH_USER_NOT_FOUND = "AUTH_USER_NOT_FOUND"

    # Authorization errors (403)
    PERMISSION_DENIED = "PERMISSION_DENIED"
    CREDENTIAL_ACCESS_DENIED = "CREDENTIAL_ACCESS_DENIED"

    # Validation errors (400)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_DATASOURCE = "INVALID_DATASOURCE"
    INVALID_SESSION = "INVALID_SESSION"
    INVALID_REQUEST = "INVALID_REQUEST"
    MISSING_CREDENTIALS = "MISSING_CREDENTIALS"

    # Resource errors (404)
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    CONNECTOR_NOT_FOUND = "CONNECTOR_NOT_FOUND"

    # External service errors (502)
    TOOL_EXECUTION_ERROR = "TOOL_EXECUTION_ERROR"
    MCP_CONNECTION_ERROR = "MCP_CONNECTION_ERROR"
    ANTHROPIC_API_ERROR = "ANTHROPIC_API_ERROR"
    SLACK_API_ERROR = "SLACK_API_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"

    # Rate limiting (429)
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    ANTHROPIC_RATE_LIMIT = "ANTHROPIC_RATE_LIMIT"

    # Server errors (500)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    ENCRYPTION_ERROR = "ENCRYPTION_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"

    # Timeout errors (504)
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    MCP_TIMEOUT = "MCP_TIMEOUT"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"


class AppError(Exception):
    """
    Base application error with structured error information.

    All application-specific exceptions should inherit from this class.

    Attributes:
        code: Error code from ErrorCode enum
        message: Human-readable error message
        details: Additional context (not exposed to users in production)
        http_status: HTTP status code for API responses
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        http_status: int = 500,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.http_status = http_status
        super().__init__(message)

    def to_dict(self, include_details: bool = False) -> Dict[str, Any]:
        """Convert exception to dictionary for API response."""
        result = {
            "error": {
                "code": self.code.value,
                "message": self.message,
            }
        }
        if include_details and self.details:
            result["error"]["details"] = self.details
        return result


# ============ Authentication Errors ============


class AuthenticationError(AppError):
    """Base class for authentication errors."""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.AUTH_TOKEN_INVALID,
        message: str = "Authentication failed",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(code=code, message=message, details=details, http_status=401)


class TokenMissingError(AuthenticationError):
    """Raised when no authentication token is provided."""

    def __init__(self, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.AUTH_TOKEN_MISSING,
            message="Authentication token is required",
            details=details,
        )


class TokenInvalidError(AuthenticationError):
    """Raised when the token is malformed or invalid."""

    def __init__(self, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.AUTH_TOKEN_INVALID,
            message="Invalid authentication token",
            details=details,
        )


class TokenExpiredError(AuthenticationError):
    """Raised when the token has expired."""

    def __init__(self, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.AUTH_TOKEN_EXPIRED,
            message="Authentication token has expired",
            details=details,
        )


class UserNotFoundError(AuthenticationError):
    """Raised when the user in the token doesn't exist."""

    def __init__(self, user_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.AUTH_USER_NOT_FOUND,
            message="User not found",
            details={**(details or {}), "user_id": user_id},
        )


# ============ Authorization Errors ============


class AuthorizationError(AppError):
    """Base class for authorization errors."""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.PERMISSION_DENIED,
        message: str = "Permission denied",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(code=code, message=message, details=details, http_status=403)


class CredentialAccessDeniedError(AuthorizationError):
    """Raised when user tries to access another user's credentials."""

    def __init__(self, datasource: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.CREDENTIAL_ACCESS_DENIED,
            message=f"Access denied to {datasource} credentials",
            details={**(details or {}), "datasource": datasource},
        )


# ============ Validation Errors ============


class ValidationError(AppError):
    """Base class for validation errors."""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.VALIDATION_ERROR,
        message: str = "Validation failed",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(code=code, message=message, details=details, http_status=400)


class InvalidDatasourceError(ValidationError):
    """Raised when an invalid datasource is specified."""

    def __init__(self, datasource: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.INVALID_DATASOURCE,
            message=f"Invalid datasource: {datasource}",
            details={**(details or {}), "datasource": datasource},
        )


class InvalidSessionError(ValidationError):
    """Raised when session ID is invalid or malformed."""

    def __init__(self, session_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.INVALID_SESSION,
            message="Invalid session ID",
            details={**(details or {}), "session_id": session_id[:8] + "..."},
        )


class MissingCredentialsError(ValidationError):
    """Raised when required credentials are not configured."""

    def __init__(self, datasource: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.MISSING_CREDENTIALS,
            message=f"Credentials not configured for {datasource}",
            details={**(details or {}), "datasource": datasource},
        )


# ============ Resource Not Found Errors ============


class ResourceNotFoundError(AppError):
    """Base class for resource not found errors."""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.RESOURCE_NOT_FOUND,
        message: str = "Resource not found",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(code=code, message=message, details=details, http_status=404)


class SessionNotFoundError(ResourceNotFoundError):
    """Raised when a session cannot be found."""

    def __init__(self, session_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.SESSION_NOT_FOUND,
            message="Chat session not found",
            details={**(details or {}), "session_id": session_id[:8] + "..."},
        )


class ConnectorNotFoundError(ResourceNotFoundError):
    """Raised when a connector/datasource doesn't exist."""

    def __init__(self, connector_id: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.CONNECTOR_NOT_FOUND,
            message=f"Connector not found: {connector_id}",
            details={**(details or {}), "connector_id": connector_id},
        )


# ============ External Service Errors ============


class ExternalServiceError(AppError):
    """Base class for external service errors."""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.EXTERNAL_SERVICE_ERROR,
        message: str = "External service error",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(code=code, message=message, details=details, http_status=502)


class ToolExecutionError(ExternalServiceError):
    """Raised when an MCP tool execution fails."""

    def __init__(
        self,
        tool_name: str,
        original_error: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            code=ErrorCode.TOOL_EXECUTION_ERROR,
            message=f"Tool execution failed: {tool_name}",
            details={
                **(details or {}),
                "tool_name": tool_name,
                "original_error": original_error,
            },
        )


class MCPConnectionError(ExternalServiceError):
    """Raised when MCP server connection fails."""

    def __init__(self, datasource: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.MCP_CONNECTION_ERROR,
            message=f"Failed to connect to {datasource} server",
            details={**(details or {}), "datasource": datasource},
        )


class AnthropicAPIError(ExternalServiceError):
    """Raised when Anthropic API call fails."""

    def __init__(self, original_error: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.ANTHROPIC_API_ERROR,
            message="AI service temporarily unavailable",
            details={**(details or {}), "original_error": original_error},
        )


# ============ Rate Limiting Errors ============


class RateLimitError(AppError):
    """Base class for rate limiting errors."""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.RATE_LIMIT_EXCEEDED,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.retry_after = retry_after
        details = details or {}
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(code=code, message=message, details=details, http_status=429)


class AnthropicRateLimitError(RateLimitError):
    """Raised when Anthropic API rate limit is hit."""

    def __init__(self, retry_after: Optional[int] = None):
        super().__init__(
            code=ErrorCode.ANTHROPIC_RATE_LIMIT,
            message="AI service rate limit reached. Please try again shortly.",
            retry_after=retry_after,
        )


# ============ Timeout Errors ============


class TimeoutError(AppError):
    """Base class for timeout errors."""

    def __init__(
        self,
        code: ErrorCode = ErrorCode.TIMEOUT_ERROR,
        message: str = "Request timed out",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(code=code, message=message, details=details, http_status=504)


class MCPTimeoutError(TimeoutError):
    """Raised when MCP server connection times out."""

    def __init__(self, datasource: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.MCP_TIMEOUT,
            message=f"Connection to {datasource} timed out",
            details={**(details or {}), "datasource": datasource},
        )


class ToolTimeoutError(TimeoutError):
    """Raised when a tool execution times out."""

    def __init__(self, tool_name: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.TOOL_TIMEOUT,
            message=f"Tool execution timed out: {tool_name}",
            details={**(details or {}), "tool_name": tool_name},
        )


# ============ Internal Errors ============


class DatabaseError(AppError):
    """Raised when database operations fail."""

    def __init__(self, operation: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.DATABASE_ERROR,
            message="Database operation failed",
            details={**(details or {}), "operation": operation},
            http_status=500,
        )


class EncryptionError(AppError):
    """Raised when encryption/decryption fails."""

    def __init__(self, operation: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.ENCRYPTION_ERROR,
            message="Encryption operation failed",
            details={**(details or {}), "operation": operation},
            http_status=500,
        )


class ConfigurationError(AppError):
    """Raised when there's a configuration issue."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.CONFIGURATION_ERROR,
            message=message,
            details=details,
            http_status=500,
        )
