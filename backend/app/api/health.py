"""
Health check endpoints for ConnectorMCP.

Provides liveness and readiness probes for Kubernetes/container
orchestration, plus detailed system status for monitoring.
"""

import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.cache import get_cache_service
from app.core.metrics import get_metrics
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["Health"])


# ============ Backward Compatible Endpoint ============


@router.get("/api/health")
async def api_health_check():
    """
    Backward compatible health check endpoint.

    Kept for compatibility with existing clients expecting /api/health.
    """
    return {"status": "healthy"}

# Track application start time
_start_time = time.time()


@router.get("/health")
async def health_check():
    """
    Basic health check endpoint (liveness probe).

    Returns 200 if the application is running.
    Used by load balancers and orchestrators to check if the service is alive.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


@router.get("/health/live")
async def liveness_probe():
    """
    Kubernetes liveness probe.

    Returns 200 if the application is alive.
    A failure triggers container restart.
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_probe(db: AsyncSession = Depends(get_db)):
    """
    Kubernetes readiness probe.

    Checks if the application is ready to receive traffic.
    Verifies database connectivity and other critical dependencies.
    """
    checks = {
        "database": False,
        "cache": False,
    }
    errors = []

    # Check database connection
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as e:
        errors.append(f"Database: {str(e)}")
        logger.error(f"Readiness check failed - database: {e}")

    # Check cache service
    try:
        cache = get_cache_service()
        # Simple set/get test
        cache._backend.set("health_check", "ok", ttl=10)
        if cache._backend.get("health_check") == "ok":
            checks["cache"] = True
        cache._backend.delete("health_check")
    except Exception as e:
        errors.append(f"Cache: {str(e)}")
        logger.error(f"Readiness check failed - cache: {e}")

    # Determine overall status
    all_healthy = all(checks.values())

    if not all_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not ready",
                "checks": checks,
                "errors": errors,
            },
        )

    return {
        "status": "ready",
        "checks": checks,
    }


@router.get("/health/detailed")
async def detailed_health_check(db: AsyncSession = Depends(get_db)):
    """
    Detailed health check with system information.

    Provides comprehensive status for monitoring dashboards.
    """
    import platform
    import sys

    # Calculate uptime
    uptime_seconds = time.time() - _start_time

    # Get metrics summary
    metrics = get_metrics()
    metrics_summary = metrics.get_summary()

    # Get cache stats
    cache = get_cache_service()
    cache_stats = cache.get_stats() if hasattr(cache, "get_stats") else {}

    # Check database
    db_status = "healthy"
    try:
        result = await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "version": getattr(settings, "version", "1.0.0"),
        "environment": settings.environment,
        "uptime": {
            "seconds": int(uptime_seconds),
            "formatted": _format_uptime(uptime_seconds),
        },
        "system": {
            "python_version": sys.version.split()[0],
            "platform": platform.system(),
            "platform_version": platform.version(),
        },
        "components": {
            "database": db_status,
            "cache": "healthy" if cache_stats else "no stats available",
        },
        "cache": cache_stats,
        "metrics": metrics_summary,
    }


@router.get("/health/metrics")
async def metrics_endpoint():
    """
    Prometheus-compatible metrics endpoint.

    Returns metrics in Prometheus text format for scraping.
    """
    metrics = get_metrics()
    prometheus_output = metrics.export_prometheus()

    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        content=prometheus_output,
        media_type="text/plain; version=0.0.4",
    )


@router.get("/health/config")
async def config_check():
    """
    Configuration health check.

    Verifies required configuration is present without exposing secrets.
    """
    config_status = {
        "anthropic_api_key": bool(settings.anthropic_api_key),
        "jwt_secret_key": bool(settings.jwt_secret_key),
        "encryption_key": bool(settings.encryption_key),
        "database_configured": bool(settings.local_mysql_host),
        "google_oauth_configured": bool(settings.google_oauth_client_id),
    }

    # Check connector configurations
    connector_status = {
        "s3": bool(settings.aws_access_key_id),
        "slack": bool(settings.slack_bot_token),
        "jira": bool(settings.jira_url and settings.jira_api_token),
        "mysql": bool(settings.mysql_host),
        "google_workspace": bool(settings.google_oauth_client_id),
        "github": bool(settings.github_token),
        "shopify": bool(settings.shopify_access_token),
    }

    missing_required = [k for k, v in config_status.items() if not v and k in ["anthropic_api_key", "jwt_secret_key"]]

    if missing_required:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "misconfigured",
                "missing_required": missing_required,
            },
        )

    return {
        "status": "configured",
        "core": config_status,
        "connectors": connector_status,
    }


def _format_uptime(seconds: float) -> str:
    """Format uptime in human-readable form."""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")

    return " ".join(parts)
