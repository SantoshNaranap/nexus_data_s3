"""
Rate limiting middleware for ConnectorMCP.

Provides request rate limiting using sliding window algorithm
to protect against abuse and ensure fair resource usage.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Dict, Optional, Tuple

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.exceptions import RateLimitError
from app.core.logging import get_logger, security_logger

logger = get_logger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10  # Allow burst of requests
    enabled: bool = True
    # Endpoints to exclude from rate limiting
    excluded_paths: list = field(default_factory=lambda: ["/health", "/api/health"])


class SlidingWindowCounter:
    """
    Sliding window rate limiter implementation.

    More accurate than fixed window counters and prevents
    burst attacks at window boundaries.
    """

    def __init__(self, window_size: int, max_requests: int):
        self.window_size = window_size  # in seconds
        self.max_requests = max_requests
        self.requests: Dict[str, list] = defaultdict(list)
        self.lock = Lock()

    def is_allowed(self, key: str) -> Tuple[bool, int, int]:
        """
        Check if request is allowed for the given key.

        Returns:
            Tuple of (is_allowed, remaining_requests, retry_after_seconds)
        """
        now = time.time()
        window_start = now - self.window_size

        with self.lock:
            # Remove expired timestamps
            self.requests[key] = [
                ts for ts in self.requests[key] if ts > window_start
            ]

            current_count = len(self.requests[key])

            if current_count >= self.max_requests:
                # Calculate retry-after
                oldest_in_window = min(self.requests[key]) if self.requests[key] else now
                retry_after = int(self.window_size - (now - oldest_in_window)) + 1
                return False, 0, retry_after

            # Allow request
            self.requests[key].append(now)
            remaining = self.max_requests - current_count - 1

            return True, remaining, 0

    def get_usage(self, key: str) -> Dict[str, int]:
        """Get current usage stats for a key."""
        now = time.time()
        window_start = now - self.window_size

        with self.lock:
            self.requests[key] = [
                ts for ts in self.requests[key] if ts > window_start
            ]
            return {
                "current": len(self.requests[key]),
                "limit": self.max_requests,
                "window_seconds": self.window_size,
            }

    def reset(self, key: str) -> None:
        """Reset rate limit for a key."""
        with self.lock:
            self.requests[key] = []


class RateLimiter:
    """
    Rate limiter with multiple time windows.

    Enforces both per-minute and per-hour limits to prevent
    sustained abuse while allowing burst traffic.
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self.minute_limiter = SlidingWindowCounter(60, self.config.requests_per_minute)
        self.hour_limiter = SlidingWindowCounter(3600, self.config.requests_per_hour)

    def check(self, key: str) -> Tuple[bool, Dict[str, any]]:
        """
        Check if request is allowed.

        Args:
            key: Unique identifier (user_id or IP address)

        Returns:
            Tuple of (is_allowed, rate_limit_info)
        """
        if not self.config.enabled:
            return True, {}

        # Check minute limit first (more restrictive)
        minute_allowed, minute_remaining, minute_retry = self.minute_limiter.is_allowed(
            f"{key}:minute"
        )

        if not minute_allowed:
            return False, {
                "limit": self.config.requests_per_minute,
                "window": "minute",
                "remaining": 0,
                "retry_after": minute_retry,
            }

        # Check hour limit
        hour_allowed, hour_remaining, hour_retry = self.hour_limiter.is_allowed(
            f"{key}:hour"
        )

        if not hour_allowed:
            return False, {
                "limit": self.config.requests_per_hour,
                "window": "hour",
                "remaining": 0,
                "retry_after": hour_retry,
            }

        return True, {
            "minute_remaining": minute_remaining,
            "hour_remaining": hour_remaining,
        }

    def get_key_from_request(self, request: Request) -> str:
        """
        Extract rate limit key from request.

        Uses user_id if authenticated, otherwise falls back to IP.
        """
        # Try to get user_id from request state (set by auth middleware)
        if hasattr(request.state, "user") and request.state.user:
            return f"user:{request.state.user.id}"

        # Fall back to IP address
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        return f"ip:{ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.

    Adds rate limit headers to all responses and returns 429
    when limits are exceeded.
    """

    def __init__(self, app, config: Optional[RateLimitConfig] = None):
        super().__init__(app)
        self.limiter = RateLimiter(config)
        self.config = config or RateLimitConfig()

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip rate limiting for excluded paths
        if request.url.path in self.config.excluded_paths:
            return await call_next(request)

        # Skip if disabled
        if not self.config.enabled:
            return await call_next(request)

        # Get rate limit key
        key = self.limiter.get_key_from_request(request)

        # Check rate limit
        allowed, info = self.limiter.check(key)

        if not allowed:
            # Log rate limit hit
            security_logger.log_rate_limit(
                user_id=key,
                endpoint=request.url.path,
            )

            # Return 429 response
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded. Try again in {info['retry_after']} seconds.",
                        "details": {
                            "limit": info["limit"],
                            "window": info["window"],
                            "retry_after": info["retry_after"],
                        },
                    }
                },
                headers={
                    "Retry-After": str(info["retry_after"]),
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + info["retry_after"]),
                },
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        if "minute_remaining" in info:
            response.headers["X-RateLimit-Limit-Minute"] = str(
                self.config.requests_per_minute
            )
            response.headers["X-RateLimit-Remaining-Minute"] = str(
                info["minute_remaining"]
            )

        return response


# ============ Endpoint-Specific Rate Limiting ============


def rate_limit(
    requests_per_minute: int = 30,
    requests_per_hour: int = 500,
    key_func: Optional[Callable[[Request], str]] = None,
):
    """
    Decorator for endpoint-specific rate limiting.

    Usage:
        @router.post("/expensive-operation")
        @rate_limit(requests_per_minute=10)
        async def expensive_operation():
            ...
    """
    limiter = RateLimiter(
        RateLimitConfig(
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour,
        )
    )

    def decorator(func: Callable):
        async def wrapper(request: Request, *args, **kwargs):
            # Get rate limit key
            if key_func:
                key = key_func(request)
            else:
                key = limiter.get_key_from_request(request)

            # Check rate limit
            allowed, info = limiter.check(key)

            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded. Try again in {info['retry_after']} seconds.",
                        "retry_after": info["retry_after"],
                    },
                    headers={"Retry-After": str(info["retry_after"])},
                )

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


# ============ Token Bucket (Alternative Algorithm) ============


class TokenBucket:
    """
    Token bucket rate limiter for burst-friendly rate limiting.

    Allows bursts up to bucket_size while maintaining
    average rate of refill_rate tokens per second.
    """

    def __init__(self, bucket_size: int, refill_rate: float):
        self.bucket_size = bucket_size
        self.refill_rate = refill_rate  # tokens per second
        self.buckets: Dict[str, Tuple[float, float]] = {}  # key -> (tokens, last_update)
        self.lock = Lock()

    def consume(self, key: str, tokens: int = 1) -> Tuple[bool, float]:
        """
        Try to consume tokens from the bucket.

        Returns:
            Tuple of (success, wait_time_if_failed)
        """
        now = time.time()

        with self.lock:
            if key not in self.buckets:
                self.buckets[key] = (self.bucket_size, now)

            current_tokens, last_update = self.buckets[key]

            # Refill tokens based on time elapsed
            elapsed = now - last_update
            refilled = current_tokens + (elapsed * self.refill_rate)
            current_tokens = min(refilled, self.bucket_size)

            if current_tokens >= tokens:
                # Consume tokens
                self.buckets[key] = (current_tokens - tokens, now)
                return True, 0

            # Not enough tokens - calculate wait time
            tokens_needed = tokens - current_tokens
            wait_time = tokens_needed / self.refill_rate

            # Update last_update even on failure
            self.buckets[key] = (current_tokens, now)

            return False, wait_time
