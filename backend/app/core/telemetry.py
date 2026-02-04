"""
OpenTelemetry integration for distributed tracing.

Provides automatic instrumentation for FastAPI, HTTPX, and SQLAlchemy,
with support for OTLP exporters (Jaeger, Datadog, etc.).
"""

import os
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def configure_telemetry(
    service_name: str = "connectormcp",
    otlp_endpoint: Optional[str] = None,
    enable_console_export: bool = False,
) -> bool:
    """
    Configure OpenTelemetry tracing for the application.

    Args:
        service_name: Name of the service for trace identification
        otlp_endpoint: OTLP exporter endpoint (e.g., "http://localhost:4317")
                       If not provided, uses OTEL_EXPORTER_OTLP_ENDPOINT env var
        enable_console_export: If True, also export traces to console (for debugging)

    Returns:
        True if telemetry was configured successfully, False otherwise
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME

        # Create resource with service name
        resource = Resource.create({
            SERVICE_NAME: service_name,
            "deployment.environment": settings.environment,
            "service.version": settings.version,
        })

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Get OTLP endpoint from parameter or environment
        endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

                otlp_exporter = OTLPSpanExporter(endpoint=endpoint)
                provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                logger.info(f"OpenTelemetry OTLP exporter configured: {endpoint}")
            except Exception as e:
                logger.warning(f"Failed to configure OTLP exporter: {e}")

        if enable_console_export:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.info("OpenTelemetry console exporter enabled")

        # Set the tracer provider
        trace.set_tracer_provider(provider)

        # Auto-instrument FastAPI
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor().instrument()
            logger.info("FastAPI auto-instrumentation enabled")
        except ImportError:
            logger.debug("FastAPI instrumentation not available")

        # Auto-instrument HTTPX (for outbound HTTP calls)
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
            HTTPXClientInstrumentor().instrument()
            logger.info("HTTPX auto-instrumentation enabled")
        except ImportError:
            logger.debug("HTTPX instrumentation not available")

        # Auto-instrument SQLAlchemy
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            SQLAlchemyInstrumentor().instrument()
            logger.info("SQLAlchemy auto-instrumentation enabled")
        except ImportError:
            logger.debug("SQLAlchemy instrumentation not available")

        logger.info(f"OpenTelemetry configured for service: {service_name}")
        return True

    except ImportError as e:
        logger.warning(f"OpenTelemetry not available: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to configure OpenTelemetry: {e}")
        return False


def get_tracer(name: str = __name__):
    """
    Get a tracer instance for creating spans.

    Args:
        name: Name for the tracer (usually __name__)

    Returns:
        Tracer instance (or no-op tracer if OpenTelemetry not configured)
    """
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        # Return a no-op tracer if OpenTelemetry is not installed
        class NoOpTracer:
            def start_as_current_span(self, name, **kwargs):
                from contextlib import contextmanager
                @contextmanager
                def noop_span():
                    yield None
                return noop_span()

        return NoOpTracer()


def get_current_span():
    """Get the current active span, if any."""
    try:
        from opentelemetry import trace
        return trace.get_current_span()
    except ImportError:
        return None


def add_span_attributes(attributes: dict) -> None:
    """
    Add attributes to the current span.

    Args:
        attributes: Dictionary of attribute key-value pairs
    """
    span = get_current_span()
    if span:
        for key, value in attributes.items():
            span.set_attribute(key, value)


def record_exception(exception: Exception, attributes: dict = None) -> None:
    """
    Record an exception on the current span.

    Args:
        exception: The exception to record
        attributes: Optional additional attributes
    """
    span = get_current_span()
    if span:
        span.record_exception(exception)
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)


class SpanContext:
    """
    Context manager for creating spans with automatic exception handling.

    Usage:
        with SpanContext("my_operation", {"key": "value"}) as span:
            # Your code here
            span.set_attribute("result", "success")
    """

    def __init__(self, name: str, attributes: dict = None):
        self.name = name
        self.attributes = attributes or {}
        self._tracer = get_tracer()
        self._span = None
        self._token = None

    def __enter__(self):
        try:
            from opentelemetry import trace
            self._span = self._tracer.start_span(self.name)
            for key, value in self.attributes.items():
                self._span.set_attribute(key, value)
            self._token = trace.use_span(self._span, end_on_exit=False)
            self._token.__enter__()
        except Exception:
            pass
        return self._span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._span:
            if exc_val:
                self._span.record_exception(exc_val)
                self._span.set_attribute("error", True)
            self._span.end()
        if self._token:
            try:
                self._token.__exit__(exc_type, exc_val, exc_tb)
            except Exception:
                pass
        return False
