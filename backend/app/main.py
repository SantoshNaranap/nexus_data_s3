"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.logging import configure_logging, get_logger, set_request_context, clear_request_context
from app.core.cache import init_cache_service, get_cache_service
from app.core.metrics import get_metrics, MetricsMiddleware
from app.core.exceptions import AppError
from app.middleware.rate_limit import RateLimitMiddleware, RateLimitConfig
from app.api import chat, datasources, credentials, auth, agent, health
from app.services.mcp_service import mcp_service

# Configure structured logging
configure_logging(
    log_level=settings.log_level,
    json_format=settings.log_format == "json",
)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting ConnectorMCP backend...", extra={"version": settings.version, "environment": settings.environment})

    # Initialize cache service
    try:
        cache = init_cache_service(use_redis=False)  # Use Redis in production: use_redis=settings.is_production
        logger.info("Cache service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize cache: {e}")

    # Initialize database on startup (quick, non-blocking)
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        if settings.is_production:
            # In production, database is required - fail fast
            raise RuntimeError(f"Database initialization failed in production: {e}")
        else:
            # In development, warn but allow app to start for API testing
            logger.warning(
                "Database init failed but continuing in development mode. "
                "Some features requiring database will not work."
            )

    # MCP connections will be established on first use
    logger.info("MCP connections will be established on first use")

    yield

    # Close persistent MCP connections on shutdown
    try:
        await mcp_service.close_all_persistent_sessions()
        logger.info("MCP persistent connections closed")
    except Exception as e:
        logger.error(f"Error closing MCP connections: {e}")

    # Close database connections on shutdown
    try:
        await close_db()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")

    logger.info("Shutting down ConnectorMCP backend...")


# Create FastAPI app
app = FastAPI(
    title="ConnectorMCP API",
    description="Backend API for ConnectorMCP - Multi-source data connector with MCP",
    version=settings.version,
    lifespan=lifespan,
)


# ============ Exception Handlers ============


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle application errors with structured response."""
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_dict(include_details=not settings.is_production),
    )


# ============ Middleware ============


# Add metrics middleware (outermost to capture all requests)
app.add_middleware(MetricsMiddleware)

# Add rate limiting middleware
if settings.rate_limit_enabled:
    app.add_middleware(
        RateLimitMiddleware,
        config=RateLimitConfig(
            requests_per_minute=settings.rate_limit_requests_per_minute,
            requests_per_hour=settings.rate_limit_requests_per_hour,
            enabled=settings.rate_limit_enabled,
        ),
    )

# Add Session middleware (required for OAuth)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.jwt_secret_key,
)

# Add CORS middleware - allow render.com and trycloudflare.com for demos
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"https://.*\.(onrender\.com|trycloudflare\.com)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Request Context Middleware ============


@app.middleware("http")
async def request_context_middleware(request: Request, call_next: Callable):
    """Add request context for logging."""
    # Set request context for structured logging
    request_id = set_request_context()
    request.state.request_id = request_id

    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        clear_request_context()


# ============ Include Routers ============

app.include_router(health.router)  # Health check endpoints
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(datasources.router)
app.include_router(credentials.router)
app.include_router(agent.router)  # Multi-source agent orchestration


# ============ Root Endpoint ============


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "ConnectorMCP API",
        "version": settings.version,
        "status": "running",
        "environment": settings.environment,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
