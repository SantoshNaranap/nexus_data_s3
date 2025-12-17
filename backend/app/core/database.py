"""Database connection and session management."""

import logging
from contextlib import asynccontextmanager
from urllib.parse import quote_plus
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create async engine for MySQL (App internal database)
# URL-encode the password to handle special characters
encoded_password = quote_plus(settings.local_mysql_password)
DATABASE_URL = (
    f"mysql+aiomysql://{settings.local_mysql_user}:{encoded_password}"
    f"@{settings.local_mysql_host}:{settings.local_mysql_port}/{settings.local_mysql_database}"
)

# Create async engine with connection timeout
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # Enable connection health checks
    pool_size=5,
    max_overflow=10,
    pool_timeout=10,  # Wait max 10 seconds for connection
    connect_args={
        "connect_timeout": 10,  # MySQL connection timeout
    },
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database sessions.

    Usage:
        @router.get("/endpoint")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            # Use db session
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {str(e)}")
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    from app.models.database import Base

    try:
        async with engine.begin() as conn:
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {str(e)}")
        logger.info("Continuing without database initialization (app will still work for anonymous users)")
        # Don't raise - allow app to continue for development


async def close_db():
    """Close database connections."""
    await engine.dispose()
    logger.info("Database connections closed")


@asynccontextmanager
async def get_db_context():
    """
    Context manager for database session.

    Usage:
        async with get_db_context() as db:
            # Use db session here
            pass
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database context error: {e}")
            raise
        finally:
            await session.close()
