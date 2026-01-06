"""
Circuit Breaker implementation for external services.

Prevents cascading failures by stopping requests to failing services
and allowing them to recover.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import TypeVar, Callable, Any, Optional
from functools import wraps
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation, requests flow through
    OPEN = "open"          # Failing, requests are rejected
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""
    failure_threshold: int = 5        # Failures before opening
    success_threshold: int = 2        # Successes needed to close from half-open
    timeout: float = 30.0             # Seconds before attempting recovery
    excluded_exceptions: tuple = ()   # Exceptions that don't count as failures


@dataclass
class CircuitBreakerStats:
    """Statistics for a circuit breaker."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_state_change: float = field(default_factory=time.time)
    total_failures: int = 0
    total_successes: int = 0
    total_rejected: int = 0


class CircuitBreaker:
    """
    Circuit breaker for protecting external service calls.

    Usage:
        breaker = CircuitBreaker("jira", config)

        # As decorator
        @breaker
        async def call_jira_api():
            ...

        # Or manually
        async with breaker:
            await call_jira_api()
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current state, checking for timeout-based transitions."""
        if self.stats.state == CircuitState.OPEN:
            # Check if timeout has passed
            if time.time() - self.stats.last_state_change >= self.config.timeout:
                return CircuitState.HALF_OPEN
        return self.stats.state

    def is_available(self) -> bool:
        """Check if circuit allows requests."""
        return self.state != CircuitState.OPEN

    async def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self.stats.state
        self.stats.state = new_state
        self.stats.last_state_change = time.time()

        if new_state == CircuitState.CLOSED:
            self.stats.failure_count = 0
            self.stats.success_count = 0

        logger.info(f"Circuit breaker [{self.name}]: {old_state.value} -> {new_state.value}")

    async def record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            self.stats.total_successes += 1
            self.stats.success_count += 1

            if self.state == CircuitState.HALF_OPEN:
                if self.stats.success_count >= self.config.success_threshold:
                    await self._transition_to(CircuitState.CLOSED)

    async def record_failure(self, exception: Exception) -> None:
        """Record a failed call."""
        # Don't count excluded exceptions
        if isinstance(exception, self.config.excluded_exceptions):
            return

        async with self._lock:
            self.stats.total_failures += 1
            self.stats.failure_count += 1
            self.stats.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                # Immediately open on failure in half-open state
                await self._transition_to(CircuitState.OPEN)
            elif self.state == CircuitState.CLOSED:
                if self.stats.failure_count >= self.config.failure_threshold:
                    await self._transition_to(CircuitState.OPEN)

    async def __aenter__(self):
        """Context manager entry - check if available."""
        if not self.is_available():
            self.stats.total_rejected += 1
            raise CircuitOpenError(
                f"Circuit breaker [{self.name}] is OPEN. "
                f"Service unavailable, will retry in {self.config.timeout - (time.time() - self.stats.last_state_change):.1f}s"
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - record result."""
        if exc_val is None:
            await self.record_success()
        else:
            await self.record_failure(exc_val)
        return False  # Don't suppress exceptions

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator to wrap async functions with circuit breaker."""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with self:
                return await func(*args, **kwargs)
        return wrapper

    def get_stats(self) -> dict:
        """Get current statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.stats.failure_count,
            "success_count": self.stats.success_count,
            "total_failures": self.stats.total_failures,
            "total_successes": self.stats.total_successes,
            "total_rejected": self.stats.total_rejected,
            "last_failure": self.stats.last_failure_time,
            "seconds_until_retry": max(0, self.config.timeout - (time.time() - self.stats.last_state_change)) if self.stats.state == CircuitState.OPEN else 0,
        }


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open and rejecting requests."""
    pass


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers.

    Usage:
        registry = CircuitBreakerRegistry()
        breaker = registry.get_or_create("jira")

        async with breaker:
            await call_jira()
    """

    def __init__(self, default_config: Optional[CircuitBreakerConfig] = None):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._default_config = default_config or CircuitBreakerConfig()
        self._lock = asyncio.Lock()

    def get_or_create(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """Get existing breaker or create new one."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name,
                config or self._default_config
            )
        return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get breaker by name if it exists."""
        return self._breakers.get(name)

    def get_all_stats(self) -> dict[str, dict]:
        """Get stats for all breakers."""
        return {name: breaker.get_stats() for name, breaker in self._breakers.items()}

    def reset(self, name: str) -> bool:
        """Manually reset a circuit breaker to closed state."""
        breaker = self._breakers.get(name)
        if breaker:
            breaker.stats = CircuitBreakerStats()
            logger.info(f"Circuit breaker [{name}] manually reset")
            return True
        return False

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for name in self._breakers:
            self.reset(name)


# Global registry for MCP service connections
mcp_circuit_breakers = CircuitBreakerRegistry(
    default_config=CircuitBreakerConfig(
        failure_threshold=3,       # Open after 3 failures
        success_threshold=2,       # Close after 2 successes
        timeout=60.0,              # Wait 60s before retrying
    )
)


def get_mcp_breaker(datasource: str) -> CircuitBreaker:
    """Get circuit breaker for an MCP datasource."""
    return mcp_circuit_breakers.get_or_create(f"mcp_{datasource}")
