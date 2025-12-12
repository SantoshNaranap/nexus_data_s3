"""FastAPI application entry point."""

import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
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

    # Initialize database on startup (quick, non-blocking)
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        # Don't crash the app even in production - database schema issues are non-fatal
        # The app can still serve API requests, just some features won't work
        logger.warning(
            "⚠️ Database init failed but continuing. "
            "Some features requiring database will not work. "
            "The app will still respond to health checks and API requests."
        )

    # Pre-warm MCP connections in background (don't block startup)
    async def prewarm_background():
        """Pre-warm connectors in background without blocking startup."""
        try:
            connectors_to_prewarm = ["s3"]  # Start with s3 only
            
            # Only add jira if credentials are fully configured
            jira_configured = (
                settings.jira_url 
                and settings.jira_email 
                and settings.jira_api_token
            )
            
            if jira_configured:
                try:
                    import jira
                    connectors_to_prewarm.append("jira")
                    logger.info("JIRA credentials configured, will pre-warm JIRA connector")
                except ImportError:
                    logger.warning("⚠️ JIRA connector dependencies not installed, skipping jira pre-warming")
            else:
                logger.info("⚠️ JIRA credentials not configured, skipping jira pre-warming")
            
            if connectors_to_prewarm:
                logger.info(f"🔥 Pre-warming MCP connections for: {connectors_to_prewarm}")
                await mcp_service.prewarm_connections(connectors_to_prewarm)
        except Exception as e:
            logger.warning(f"Pre-warming failed (non-fatal): {e}")
    
    # Start pre-warming in background (don't await - let it run in background)
    # This allows the app to start serving requests immediately
    asyncio.create_task(prewarm_background())

    yield  # App is now ready to serve requests (health checks will work immediately)

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
    """Health check endpoint for load balancer and container health checks."""
    try:
        # Basic health check - just verify the app is running
        # Don't check database or connectors here to avoid false negatives
        return {"status": "healthy", "service": "mosaic-backend"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
