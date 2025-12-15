"""
Metrics collection for ConnectorMCP.

Provides application metrics using Prometheus format for
observability and monitoring dashboards.
"""

import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

from app.core.enums import DataSourceType, RoutingPath
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MetricValue:
    """A single metric value with labels."""

    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class Counter:
    """
    A monotonically increasing counter metric.

    Used for counting events like requests, errors, etc.
    """

    def __init__(self, name: str, description: str, label_names: List[str] = None):
        self.name = name
        self.description = description
        self.label_names = label_names or []
        self._values: Dict[tuple, float] = defaultdict(float)
        self._lock = Lock()

    def inc(self, value: float = 1, **labels) -> None:
        """Increment the counter."""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[label_key] += value

    def get(self, **labels) -> float:
        """Get current counter value."""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            return self._values.get(label_key, 0)

    def get_all(self) -> List[MetricValue]:
        """Get all counter values with labels."""
        with self._lock:
            return [
                MetricValue(
                    value=value,
                    labels=dict(label_key),
                )
                for label_key, value in self._values.items()
            ]


class Gauge:
    """
    A metric that can go up and down.

    Used for current values like active connections, cache size, etc.
    """

    def __init__(self, name: str, description: str, label_names: List[str] = None):
        self.name = name
        self.description = description
        self.label_names = label_names or []
        self._values: Dict[tuple, float] = defaultdict(float)
        self._lock = Lock()

    def set(self, value: float, **labels) -> None:
        """Set the gauge value."""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[label_key] = value

    def inc(self, value: float = 1, **labels) -> None:
        """Increment the gauge."""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[label_key] += value

    def dec(self, value: float = 1, **labels) -> None:
        """Decrement the gauge."""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[label_key] -= value

    def get(self, **labels) -> float:
        """Get current gauge value."""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            return self._values.get(label_key, 0)

    def get_all(self) -> List[MetricValue]:
        """Get all gauge values with labels."""
        with self._lock:
            return [
                MetricValue(
                    value=value,
                    labels=dict(label_key),
                )
                for label_key, value in self._values.items()
            ]


class Histogram:
    """
    A histogram metric for measuring distributions.

    Used for request latencies, response sizes, etc.
    """

    DEFAULT_BUCKETS = (
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        float("inf"),
    )

    def __init__(
        self,
        name: str,
        description: str,
        label_names: List[str] = None,
        buckets: tuple = None,
    ):
        self.name = name
        self.description = description
        self.label_names = label_names or []
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._observations: Dict[tuple, List[float]] = defaultdict(list)
        self._lock = Lock()

    def observe(self, value: float, **labels) -> None:
        """Record an observation."""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._observations[label_key].append(value)

    @contextmanager
    def time(self, **labels):
        """Context manager to time a block of code."""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            self.observe(duration, **labels)

    def get_stats(self, **labels) -> Dict[str, float]:
        """Get histogram statistics."""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            observations = self._observations.get(label_key, [])
            if not observations:
                return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0}

            return {
                "count": len(observations),
                "sum": sum(observations),
                "avg": sum(observations) / len(observations),
                "min": min(observations),
                "max": max(observations),
            }

    def get_bucket_counts(self, **labels) -> Dict[float, int]:
        """Get bucket counts for histogram (cumulative, Prometheus-style)."""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            observations = self._observations.get(label_key, [])
            bucket_counts = {b: 0 for b in self.buckets}

            for obs in observations:
                for bucket in self.buckets:
                    if obs <= bucket:
                        bucket_counts[bucket] += 1
                        # No break - cumulative buckets

            return bucket_counts


# ============ Application Metrics ============


class ApplicationMetrics:
    """
    Central metrics registry for the application.

    Provides pre-defined metrics for common operations.
    """

    def __init__(self):
        # Request metrics
        self.requests_total = Counter(
            "mosaic_requests_total",
            "Total number of requests",
            ["method", "endpoint", "status"],
        )

        self.request_duration = Histogram(
            "mosaic_request_duration_seconds",
            "Request duration in seconds",
            ["method", "endpoint"],
        )

        # Chat metrics
        self.chat_messages_total = Counter(
            "mosaic_chat_messages_total",
            "Total chat messages processed",
            ["datasource", "routing_path"],
        )

        self.chat_response_time = Histogram(
            "mosaic_chat_response_seconds",
            "Chat response time in seconds",
            ["datasource", "routing_path"],
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, float("inf")),
        )

        # Tool metrics
        self.tool_calls_total = Counter(
            "mosaic_tool_calls_total",
            "Total tool calls",
            ["datasource", "tool_name", "status"],
        )

        self.tool_duration = Histogram(
            "mosaic_tool_duration_seconds",
            "Tool execution duration in seconds",
            ["datasource", "tool_name"],
        )

        # Cache metrics
        self.cache_hits = Counter(
            "mosaic_cache_hits_total",
            "Cache hit count",
            ["cache_type", "datasource"],
        )

        self.cache_misses = Counter(
            "mosaic_cache_misses_total",
            "Cache miss count",
            ["cache_type", "datasource"],
        )

        self.cache_size = Gauge(
            "mosaic_cache_size",
            "Current cache size",
            ["cache_type"],
        )

        # LLM metrics
        self.llm_calls_total = Counter(
            "mosaic_llm_calls_total",
            "Total LLM API calls",
            ["model", "purpose"],
        )

        self.llm_tokens = Counter(
            "mosaic_llm_tokens_total",
            "Total LLM tokens used",
            ["model", "direction"],  # direction: input or output
        )

        self.llm_duration = Histogram(
            "mosaic_llm_duration_seconds",
            "LLM call duration in seconds",
            ["model", "purpose"],
        )

        # Authentication metrics
        self.auth_attempts = Counter(
            "mosaic_auth_attempts_total",
            "Authentication attempts",
            ["method", "status"],
        )

        # Active connections
        self.active_connections = Gauge(
            "mosaic_active_connections",
            "Number of active connections",
            ["datasource"],
        )

        self.active_streams = Gauge(
            "mosaic_active_streams",
            "Number of active SSE streams",
        )

        # Error metrics
        self.errors_total = Counter(
            "mosaic_errors_total",
            "Total errors",
            ["error_type", "datasource"],
        )

    # ============ Convenience Methods ============

    def record_request(
        self,
        method: str,
        endpoint: str,
        status: int,
        duration: float,
    ) -> None:
        """Record an HTTP request."""
        self.requests_total.inc(method=method, endpoint=endpoint, status=str(status))
        self.request_duration.observe(duration, method=method, endpoint=endpoint)

    def record_chat_message(
        self,
        datasource: str,
        routing_path: str,
        duration: float,
    ) -> None:
        """Record a chat message processing."""
        self.chat_messages_total.inc(datasource=datasource, routing_path=routing_path)
        self.chat_response_time.observe(
            duration, datasource=datasource, routing_path=routing_path
        )

    def record_tool_call(
        self,
        datasource: str,
        tool_name: str,
        success: bool,
        duration: float,
    ) -> None:
        """Record a tool call."""
        status = "success" if success else "error"
        self.tool_calls_total.inc(
            datasource=datasource, tool_name=tool_name, status=status
        )
        self.tool_duration.observe(duration, datasource=datasource, tool_name=tool_name)

    def record_cache_access(
        self,
        cache_type: str,
        datasource: str,
        hit: bool,
    ) -> None:
        """Record a cache access."""
        if hit:
            self.cache_hits.inc(cache_type=cache_type, datasource=datasource)
        else:
            self.cache_misses.inc(cache_type=cache_type, datasource=datasource)

    def record_llm_call(
        self,
        model: str,
        purpose: str,
        input_tokens: int,
        output_tokens: int,
        duration: float,
    ) -> None:
        """Record an LLM API call."""
        self.llm_calls_total.inc(model=model, purpose=purpose)
        self.llm_tokens.inc(input_tokens, model=model, direction="input")
        self.llm_tokens.inc(output_tokens, model=model, direction="output")
        self.llm_duration.observe(duration, model=model, purpose=purpose)

    def record_error(self, error_type: str, datasource: str = "unknown") -> None:
        """Record an error."""
        self.errors_total.inc(error_type=error_type, datasource=datasource)

    def record_auth_attempt(self, method: str, success: bool) -> None:
        """Record an authentication attempt."""
        status = "success" if success else "failure"
        self.auth_attempts.inc(method=method, status=status)

    # ============ Export Methods ============

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []

        def format_metric(metric, metric_type: str):
            lines.append(f"# HELP {metric.name} {metric.description}")
            lines.append(f"# TYPE {metric.name} {metric_type}")

            for mv in metric.get_all():
                label_str = (
                    ",".join(f'{k}="{v}"' for k, v in mv.labels.items())
                    if mv.labels
                    else ""
                )
                label_part = f"{{{label_str}}}" if label_str else ""
                lines.append(f"{metric.name}{label_part} {mv.value}")

        # Export counters
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if isinstance(attr, Counter):
                format_metric(attr, "counter")
            elif isinstance(attr, Gauge):
                format_metric(attr, "gauge")

        return "\n".join(lines)

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all metrics."""
        return {
            "requests": {
                "total": sum(mv.value for mv in self.requests_total.get_all()),
            },
            "chat": {
                "messages": sum(
                    mv.value for mv in self.chat_messages_total.get_all()
                ),
                "avg_response_time": self.chat_response_time.get_stats().get("avg", 0),
            },
            "tools": {
                "total_calls": sum(mv.value for mv in self.tool_calls_total.get_all()),
            },
            "cache": {
                "hits": sum(mv.value for mv in self.cache_hits.get_all()),
                "misses": sum(mv.value for mv in self.cache_misses.get_all()),
            },
            "llm": {
                "total_calls": sum(mv.value for mv in self.llm_calls_total.get_all()),
                "total_tokens": sum(mv.value for mv in self.llm_tokens.get_all()),
            },
            "errors": {
                "total": sum(mv.value for mv in self.errors_total.get_all()),
            },
        }


# Global metrics instance
metrics = ApplicationMetrics()


def get_metrics() -> ApplicationMetrics:
    """Get the global metrics instance."""
    return metrics


# ============ Middleware for Request Metrics ============


class MetricsMiddleware:
    """Middleware to automatically record request metrics."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500  # Default if something goes wrong

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            method = scope.get("method", "UNKNOWN")
            path = scope.get("path", "/")

            metrics.record_request(
                method=method,
                endpoint=path,
                status=status_code,
                duration=duration,
            )
