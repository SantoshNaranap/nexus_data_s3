"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.database import init_db, close_db
from app.api import chat, datasources, credentials, auth, agent
from app.services.mcp_service import mcp_service

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting ConnectorMCP backend...")

    # Initialize database on startup
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
                "⚠️ Database init failed but continuing in development mode. "
                "Some features requiring database will not work."
            )

    # Pre-warm MCP connections for faster first requests
    try:
        # Only pre-warm connectors that are configured (have credentials in .env)
        connectors_to_prewarm = ["s3", "jira"]  # MySQL might timeout if RDS is blocked
        logger.info(f"🔥 Pre-warming MCP connections for: {connectors_to_prewarm}")
        await mcp_service.prewarm_connections(connectors_to_prewarm)
    except Exception as e:
        logger.warning(f"Pre-warming failed (non-fatal): {e}")

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
    version="0.1.0",
    lifespan=lifespan,
)

# Add Session middleware (required for OAuth)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.jwt_secret_key,  # Use the same secret as JWT
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(datasources.router)
app.include_router(credentials.router)
app.include_router(agent.router)  # Multi-source agent orchestration


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "ConnectorMCP API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
