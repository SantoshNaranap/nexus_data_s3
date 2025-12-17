"""
Unit tests for metrics collection.
"""

import pytest
import time

from app.core.metrics import (
    Counter,
    Gauge,
    Histogram,
    ApplicationMetrics,
    get_metrics,
)


class TestCounter:
    """Tests for Counter metric."""

    def test_counter_increment(self):
        """Test counter increment."""
        counter = Counter("test_counter", "Test counter")
        counter.inc()
        assert counter.get() == 1
        counter.inc()
        assert counter.get() == 2

    def test_counter_increment_by_value(self):
        """Test counter increment by specific value."""
        counter = Counter("test_counter", "Test counter")
        counter.inc(5)
        assert counter.get() == 5
        counter.inc(3)
        assert counter.get() == 8

    def test_counter_with_labels(self):
        """Test counter with labels."""
        counter = Counter("test_counter", "Test counter", ["method", "status"])
        counter.inc(method="GET", status="200")
        counter.inc(method="POST", status="200")
        counter.inc(method="GET", status="200")

        assert counter.get(method="GET", status="200") == 2
        assert counter.get(method="POST", status="200") == 1
        assert counter.get(method="DELETE", status="404") == 0

    def test_counter_get_all(self):
        """Test getting all counter values."""
        counter = Counter("test_counter", "Test counter", ["method"])
        counter.inc(method="GET")
        counter.inc(method="POST")
        counter.inc(method="GET")

        all_values = counter.get_all()
        assert len(all_values) == 2

        get_value = next(v for v in all_values if v.labels.get("method") == "GET")
        assert get_value.value == 2


class TestGauge:
    """Tests for Gauge metric."""

    def test_gauge_set(self):
        """Test gauge set."""
        gauge = Gauge("test_gauge", "Test gauge")
        gauge.set(42)
        assert gauge.get() == 42
        gauge.set(100)
        assert gauge.get() == 100

    def test_gauge_inc_dec(self):
        """Test gauge increment and decrement."""
        gauge = Gauge("test_gauge", "Test gauge")
        gauge.set(10)
        gauge.inc()
        assert gauge.get() == 11
        gauge.dec()
        assert gauge.get() == 10
        gauge.inc(5)
        assert gauge.get() == 15
        gauge.dec(3)
        assert gauge.get() == 12

    def test_gauge_with_labels(self):
        """Test gauge with labels."""
        gauge = Gauge("active_connections", "Active connections", ["datasource"])
        gauge.set(5, datasource="slack")
        gauge.set(3, datasource="jira")

        assert gauge.get(datasource="slack") == 5
        assert gauge.get(datasource="jira") == 3


class TestHistogram:
    """Tests for Histogram metric."""

    def test_histogram_observe(self):
        """Test histogram observe."""
        histogram = Histogram("test_histogram", "Test histogram")
        histogram.observe(0.5)
        histogram.observe(1.0)
        histogram.observe(2.0)

        stats = histogram.get_stats()
        assert stats["count"] == 3
        assert stats["sum"] == 3.5
        assert stats["avg"] == pytest.approx(1.167, rel=0.01)
        assert stats["min"] == 0.5
        assert stats["max"] == 2.0

    def test_histogram_time_context_manager(self):
        """Test histogram time context manager."""
        histogram = Histogram("test_histogram", "Test histogram")

        with histogram.time(operation="test"):
            time.sleep(0.1)

        stats = histogram.get_stats(operation="test")
        assert stats["count"] == 1
        assert stats["sum"] >= 0.1

    def test_histogram_buckets(self):
        """Test histogram bucket counts."""
        histogram = Histogram(
            "test_histogram",
            "Test histogram",
            buckets=(0.1, 0.5, 1.0, float("inf")),
        )

        histogram.observe(0.05)  # <= 0.1
        histogram.observe(0.3)  # <= 0.5
        histogram.observe(0.8)  # <= 1.0
        histogram.observe(2.0)  # <= inf

        buckets = histogram.get_bucket_counts()
        assert buckets[0.1] == 1
        assert buckets[0.5] == 2  # Cumulative
        assert buckets[1.0] == 3  # Cumulative
        assert buckets[float("inf")] == 4  # All

    def test_histogram_with_labels(self):
        """Test histogram with labels."""
        histogram = Histogram("response_time", "Response time", ["endpoint"])
        histogram.observe(0.5, endpoint="/api/chat")
        histogram.observe(0.3, endpoint="/api/chat")
        histogram.observe(1.0, endpoint="/api/auth")

        chat_stats = histogram.get_stats(endpoint="/api/chat")
        assert chat_stats["count"] == 2
        assert chat_stats["avg"] == 0.4

        auth_stats = histogram.get_stats(endpoint="/api/auth")
        assert auth_stats["count"] == 1


class TestApplicationMetrics:
    """Tests for ApplicationMetrics."""

    def test_record_request(self):
        """Test recording HTTP request."""
        metrics = ApplicationMetrics()
        metrics.record_request(
            method="GET",
            endpoint="/api/chat",
            status=200,
            duration=0.5,
        )

        assert metrics.requests_total.get(method="GET", endpoint="/api/chat", status="200") == 1

    def test_record_chat_message(self):
        """Test recording chat message."""
        metrics = ApplicationMetrics()
        metrics.record_chat_message(
            datasource="slack",
            routing_path="haiku",
            duration=1.5,
        )

        assert metrics.chat_messages_total.get(datasource="slack", routing_path="haiku") == 1

    def test_record_tool_call(self):
        """Test recording tool call."""
        metrics = ApplicationMetrics()
        metrics.record_tool_call(
            datasource="slack",
            tool_name="list_channels",
            success=True,
            duration=0.3,
        )

        assert metrics.tool_calls_total.get(
            datasource="slack", tool_name="list_channels", status="success"
        ) == 1

    def test_record_cache_access(self):
        """Test recording cache access."""
        metrics = ApplicationMetrics()

        # Record hit
        metrics.record_cache_access(cache_type="tools", datasource="slack", hit=True)
        assert metrics.cache_hits.get(cache_type="tools", datasource="slack") == 1

        # Record miss
        metrics.record_cache_access(cache_type="tools", datasource="slack", hit=False)
        assert metrics.cache_misses.get(cache_type="tools", datasource="slack") == 1

    def test_record_llm_call(self):
        """Test recording LLM call."""
        metrics = ApplicationMetrics()
        metrics.record_llm_call(
            model="claude-3-haiku",
            purpose="routing",
            input_tokens=100,
            output_tokens=50,
            duration=0.5,
        )

        assert metrics.llm_calls_total.get(model="claude-3-haiku", purpose="routing") == 1
        assert metrics.llm_tokens.get(model="claude-3-haiku", direction="input") == 100
        assert metrics.llm_tokens.get(model="claude-3-haiku", direction="output") == 50

    def test_record_error(self):
        """Test recording error."""
        metrics = ApplicationMetrics()
        metrics.record_error(error_type="ToolExecutionError", datasource="slack")

        assert metrics.errors_total.get(error_type="ToolExecutionError", datasource="slack") == 1

    def test_record_auth_attempt(self):
        """Test recording auth attempt."""
        metrics = ApplicationMetrics()

        metrics.record_auth_attempt(method="google", success=True)
        assert metrics.auth_attempts.get(method="google", status="success") == 1

        metrics.record_auth_attempt(method="google", success=False)
        assert metrics.auth_attempts.get(method="google", status="failure") == 1

    def test_get_summary(self):
        """Test getting metrics summary."""
        metrics = ApplicationMetrics()
        metrics.record_request("GET", "/api/chat", 200, 0.5)
        metrics.record_chat_message("slack", "haiku", 1.0)
        metrics.record_error("TestError", "slack")

        summary = metrics.get_summary()

        assert "requests" in summary
        assert "chat" in summary
        assert "errors" in summary
        assert summary["requests"]["total"] == 1
        assert summary["chat"]["messages"] == 1
        assert summary["errors"]["total"] == 1

    def test_export_prometheus(self):
        """Test Prometheus export format."""
        metrics = ApplicationMetrics()
        metrics.record_request("GET", "/api/chat", 200, 0.5)

        output = metrics.export_prometheus()

        assert "# HELP" in output
        assert "# TYPE" in output
        assert "mosaic_requests_total" in output


class TestGlobalMetrics:
    """Tests for global metrics instance."""

    def test_get_metrics_returns_instance(self):
        """Test get_metrics returns the global instance."""
        metrics1 = get_metrics()
        metrics2 = get_metrics()
        assert metrics1 is metrics2

    def test_global_metrics_is_application_metrics(self):
        """Test global metrics is ApplicationMetrics instance."""
        metrics = get_metrics()
        assert isinstance(metrics, ApplicationMetrics)
