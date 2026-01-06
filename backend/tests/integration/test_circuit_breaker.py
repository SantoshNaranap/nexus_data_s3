"""
Integration tests for circuit breaker functionality.

Tests the circuit breaker pattern for handling external service failures.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitState,
    CircuitOpenError,
    get_mcp_breaker,
    mcp_circuit_breakers,
)


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class TestCircuitBreakerStates:
    """Tests for circuit breaker state transitions."""

    @pytest.mark.anyio
    async def test_initial_state_is_closed(self):
        """Circuit breaker should start in CLOSED state."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_available()

    @pytest.mark.anyio
    async def test_opens_after_threshold_failures(self):
        """Circuit should open after reaching failure threshold."""
        config = CircuitBreakerConfig(failure_threshold=3, timeout=10.0)
        breaker = CircuitBreaker("test", config)

        # Record failures up to threshold
        for i in range(3):
            await breaker.record_failure(Exception(f"Error {i}"))

        assert breaker.state == CircuitState.OPEN
        assert not breaker.is_available()

    @pytest.mark.anyio
    async def test_rejects_requests_when_open(self):
        """Circuit should reject requests when OPEN."""
        config = CircuitBreakerConfig(failure_threshold=1, timeout=60.0)
        breaker = CircuitBreaker("test", config)

        await breaker.record_failure(Exception("Error"))

        with pytest.raises(CircuitOpenError):
            async with breaker:
                pass

    @pytest.mark.anyio
    async def test_transitions_to_half_open_after_timeout(self):
        """Circuit should transition to HALF_OPEN after timeout."""
        config = CircuitBreakerConfig(failure_threshold=1, timeout=0.1)  # Very short timeout
        breaker = CircuitBreaker("test", config)

        await breaker.record_failure(Exception("Error"))
        assert breaker.stats.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.15)

        # State property should return HALF_OPEN
        assert breaker.state == CircuitState.HALF_OPEN
        assert breaker.is_available()

    @pytest.mark.anyio
    async def test_closes_after_success_in_half_open(self):
        """Circuit should close after successes in HALF_OPEN state."""
        config = CircuitBreakerConfig(failure_threshold=1, success_threshold=2, timeout=0.1)
        breaker = CircuitBreaker("test", config)

        # Open the circuit
        await breaker.record_failure(Exception("Error"))
        await asyncio.sleep(0.15)  # Wait for half-open

        # Record successes
        await breaker.record_success()
        await breaker.record_success()

        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.anyio
    async def test_reopens_on_failure_in_half_open(self):
        """Circuit should reopen on failure in HALF_OPEN state."""
        config = CircuitBreakerConfig(failure_threshold=1, timeout=0.1)
        breaker = CircuitBreaker("test", config)

        # Open the circuit
        await breaker.record_failure(Exception("Error"))
        await asyncio.sleep(0.15)  # Wait for half-open

        # Fail again
        await breaker.record_failure(Exception("Error again"))

        assert breaker.state == CircuitState.OPEN


class TestCircuitBreakerDecorator:
    """Tests for circuit breaker as decorator."""

    @pytest.mark.anyio
    async def test_decorator_passes_on_success(self):
        """Decorated function should work normally when circuit is closed."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig())

        @breaker
        async def my_func():
            return "success"

        result = await my_func()
        assert result == "success"
        assert breaker.stats.total_successes == 1

    @pytest.mark.anyio
    async def test_decorator_records_failure(self):
        """Decorated function should record failures."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))

        @breaker
        async def my_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await my_func()

        assert breaker.stats.total_failures == 1
        assert breaker.stats.failure_count == 1


class TestCircuitBreakerRegistry:
    """Tests for circuit breaker registry."""

    def test_get_or_create_returns_same_instance(self):
        """Registry should return same instance for same name."""
        registry = CircuitBreakerRegistry()
        breaker1 = registry.get_or_create("test")
        breaker2 = registry.get_or_create("test")
        assert breaker1 is breaker2

    def test_different_names_get_different_instances(self):
        """Registry should return different instances for different names."""
        registry = CircuitBreakerRegistry()
        breaker1 = registry.get_or_create("test1")
        breaker2 = registry.get_or_create("test2")
        assert breaker1 is not breaker2

    @pytest.mark.anyio
    async def test_reset_clears_breaker_state(self):
        """Reset should clear breaker state."""
        registry = CircuitBreakerRegistry()
        breaker = registry.get_or_create("test", CircuitBreakerConfig(failure_threshold=1))

        await breaker.record_failure(Exception("Error"))
        assert breaker.state == CircuitState.OPEN

        registry.reset("test")
        assert breaker.state == CircuitState.CLOSED

    def test_get_all_stats(self):
        """get_all_stats should return stats for all breakers."""
        registry = CircuitBreakerRegistry()
        registry.get_or_create("breaker1")
        registry.get_or_create("breaker2")

        stats = registry.get_all_stats()
        assert "breaker1" in stats
        assert "breaker2" in stats
        assert stats["breaker1"]["state"] == "closed"


class TestMCPCircuitBreaker:
    """Tests for MCP-specific circuit breaker integration."""

    def test_get_mcp_breaker_returns_prefixed_breaker(self):
        """get_mcp_breaker should return breaker with mcp_ prefix."""
        breaker = get_mcp_breaker("jira")
        assert breaker.name == "mcp_jira"

    def test_mcp_breakers_share_registry(self):
        """MCP breakers should share the global registry."""
        breaker1 = get_mcp_breaker("jira")
        breaker2 = get_mcp_breaker("jira")
        assert breaker1 is breaker2

    def test_mcp_registry_default_config(self):
        """MCP registry should have sensible default config."""
        breaker = get_mcp_breaker("test_datasource")
        config = breaker.config
        assert config.failure_threshold == 3
        assert config.success_threshold == 2
        assert config.timeout == 60.0


class TestCircuitBreakerStats:
    """Tests for circuit breaker statistics."""

    @pytest.mark.anyio
    async def test_stats_track_totals(self):
        """Stats should track total successes and failures."""
        breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=10))

        await breaker.record_success()
        await breaker.record_success()
        await breaker.record_failure(Exception("Error"))

        stats = breaker.get_stats()
        assert stats["total_successes"] == 2
        assert stats["total_failures"] == 1
        assert stats["name"] == "test"

    @pytest.mark.anyio
    async def test_stats_track_rejected(self):
        """Stats should track rejected requests."""
        config = CircuitBreakerConfig(failure_threshold=1, timeout=60.0)
        breaker = CircuitBreaker("test", config)

        await breaker.record_failure(Exception("Error"))

        # Try to use when open
        try:
            async with breaker:
                pass
        except CircuitOpenError:
            pass

        stats = breaker.get_stats()
        assert stats["total_rejected"] == 1


class TestExcludedExceptions:
    """Tests for excluded exceptions feature."""

    @pytest.mark.anyio
    async def test_excluded_exceptions_not_counted(self):
        """Excluded exceptions should not count as failures."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            excluded_exceptions=(ValueError,)
        )
        breaker = CircuitBreaker("test", config)

        # This should NOT count as a failure
        await breaker.record_failure(ValueError("Not a real error"))

        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.failure_count == 0

    @pytest.mark.anyio
    async def test_non_excluded_exceptions_counted(self):
        """Non-excluded exceptions should count as failures."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            excluded_exceptions=(ValueError,)
        )
        breaker = CircuitBreaker("test", config)

        # This SHOULD count as a failure
        await breaker.record_failure(RuntimeError("Real error"))

        assert breaker.state == CircuitState.OPEN


# Run with: pytest tests/integration/test_circuit_breaker.py -v
