"""
Structured logging configuration for ConnectorMCP.

Provides JSON-formatted logs with context propagation for
distributed tracing and observability.
"""

import logging
import json
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional, Callable

# Context variables for request tracing
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
datasource_var: ContextVar[str] = ContextVar("datasource", default="")


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return str(uuid.uuid4())[:8]


def set_request_context(
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    datasource: Optional[str] = None,
) -> str:
    """Set request context variables for logging."""
    req_id = request_id or generate_request_id()
    request_id_var.set(req_id)
    if user_id:
        user_id_var.set(user_id[:8] + "..." if len(user_id) > 8 else user_id)
    if datasource:
        datasource_var.set(datasource)
    return req_id


def clear_request_context() -> None:
    """Clear request context after request completes."""
    request_id_var.set("")
    user_id_var.set("")
    datasource_var.set("")


class StructuredLogFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Outputs logs in JSON format suitable for log aggregation systems
    like ELK, Splunk, or CloudWatch.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add context from context variables
        if request_id := request_id_var.get():
            log_data["request_id"] = request_id
        if user_id := user_id_var.get():
            log_data["user_id"] = user_id
        if datasource := datasource_var.get():
            log_data["datasource"] = datasource

        # Add extra fields from record
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class DevelopmentFormatter(logging.Formatter):
    """
    Human-readable formatter for development.

    Provides colorized, readable output for local development.
    """

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]

        # Build context string
        context_parts = []
        if request_id := request_id_var.get():
            context_parts.append(f"req={request_id}")
        if user_id := user_id_var.get():
            context_parts.append(f"user={user_id}")
        if datasource := datasource_var.get():
            context_parts.append(f"ds={datasource}")

        context_str = f" [{', '.join(context_parts)}]" if context_parts else ""

        # Format timestamp
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # Build log line
        log_line = (
            f"{color}{timestamp} {record.levelname:8}{reset}"
            f"{context_str} "
            f"{record.name}: {record.getMessage()}"
        )

        # Add extra fields if present
        if hasattr(record, "extra_fields") and record.extra_fields:
            extras = " | ".join(f"{k}={v}" for k, v in record.extra_fields.items())
            log_line += f" | {extras}"

        # Add exception info if present
        if record.exc_info:
            log_line += f"\n{self.formatException(record.exc_info)}"

        return log_line


class ContextLogger(logging.LoggerAdapter):
    """
    Logger adapter that automatically includes context in log messages.

    Usage:
        logger = get_logger(__name__)
        logger.info("Processing request", extra={"tool": "list_channels", "duration_ms": 150})
    """

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        # Extract extra fields and store them properly
        extra = kwargs.get("extra", {})
        if extra:
            # Store extra fields in a way the formatter can access
            kwargs["extra"] = {"extra_fields": extra}
        return msg, kwargs


def get_logger(name: str) -> ContextLogger:
    """
    Get a configured logger with context support.

    Args:
        name: Logger name (typically __name__)

    Returns:
        ContextLogger instance
    """
    logger = logging.getLogger(name)
    return ContextLogger(logger, {})


def configure_logging(
    log_level: str = "INFO",
    json_format: bool = False,
    include_timestamp: bool = True,
) -> None:
    """
    Configure application logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON format for production, readable format for development
        include_timestamp: Include timestamps in log output
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, log_level.upper()))

    # Set formatter based on environment
    if json_format:
        formatter = StructuredLogFormatter()
    else:
        formatter = DevelopmentFormatter()

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def log_execution_time(
    logger: Optional[ContextLogger] = None,
    operation: str = "operation",
) -> Callable:
    """
    Decorator to log function execution time.

    Args:
        logger: Logger instance (uses function's module logger if not provided)
        operation: Name of the operation for logging

    Usage:
        @log_execution_time(operation="process_message")
        async def process_message(...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        func_logger = logger or get_logger(func.__module__)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000
                func_logger.info(
                    f"{operation} completed",
                    extra={"duration_ms": round(duration_ms, 2), "status": "success"},
                )
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start) * 1000
                func_logger.error(
                    f"{operation} failed",
                    extra={
                        "duration_ms": round(duration_ms, 2),
                        "status": "error",
                        "error_type": type(e).__name__,
                    },
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000
                func_logger.info(
                    f"{operation} completed",
                    extra={"duration_ms": round(duration_ms, 2), "status": "success"},
                )
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start) * 1000
                func_logger.error(
                    f"{operation} failed",
                    extra={
                        "duration_ms": round(duration_ms, 2),
                        "status": "error",
                        "error_type": type(e).__name__,
                    },
                )
                raise

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ============ Specialized Loggers ============


class PerformanceLogger:
    """Logger specialized for performance metrics."""

    def __init__(self, name: str = "performance"):
        self.logger = get_logger(name)

    def log_routing(
        self,
        path: str,
        datasource: str,
        tools: list,
        duration_ms: float,
    ) -> None:
        """Log routing decision metrics."""
        self.logger.info(
            f"Routing decision: {path}",
            extra={
                "routing_path": path,
                "datasource": datasource,
                "tools_selected": tools,
                "duration_ms": round(duration_ms, 2),
            },
        )

    def log_tool_execution(
        self,
        tool_name: str,
        datasource: str,
        duration_ms: float,
        cached: bool = False,
        success: bool = True,
    ) -> None:
        """Log tool execution metrics."""
        self.logger.info(
            f"Tool execution: {tool_name}",
            extra={
                "tool_name": tool_name,
                "datasource": datasource,
                "duration_ms": round(duration_ms, 2),
                "cached": cached,
                "success": success,
            },
        )

    def log_llm_call(
        self,
        model: str,
        purpose: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: float,
    ) -> None:
        """Log LLM call metrics."""
        self.logger.info(
            f"LLM call: {purpose}",
            extra={
                "model": model,
                "purpose": purpose,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "duration_ms": round(duration_ms, 2),
            },
        )


class SecurityLogger:
    """Logger specialized for security events."""

    def __init__(self, name: str = "security"):
        self.logger = get_logger(name)

    def log_auth_success(self, user_email: str, method: str) -> None:
        """Log successful authentication."""
        self.logger.info(
            "Authentication successful",
            extra={"user_email": user_email, "auth_method": method},
        )

    def log_auth_failure(self, reason: str, details: Dict[str, Any] = None) -> None:
        """Log failed authentication attempt."""
        self.logger.warning(
            "Authentication failed",
            extra={"reason": reason, **(details or {})},
        )

    def log_credential_access(
        self, user_id: str, datasource: str, action: str
    ) -> None:
        """Log credential access."""
        self.logger.info(
            f"Credential {action}",
            extra={
                "user_id": user_id[:8] + "...",
                "datasource": datasource,
                "action": action,
            },
        )

    def log_rate_limit(self, user_id: str, endpoint: str) -> None:
        """Log rate limit hit."""
        self.logger.warning(
            "Rate limit exceeded",
            extra={"user_id": user_id[:8] + "...", "endpoint": endpoint},
        )


# Global logger instances
perf_logger = PerformanceLogger()
security_logger = SecurityLogger()
