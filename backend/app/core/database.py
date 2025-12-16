"""Database connection and session management."""

import logging
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from typing import AsyncGenerator

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create async engine for MySQL (App internal database - local)
DATABASE_URL = (
    f"mysql+aiomysql://{settings.local_mysql_user}:{settings.local_mysql_password}"
    f"@{settings.local_mysql_host}:{settings.local_mysql_port}/{settings.local_mysql_database}"
)

# Create async engine with configurable pool settings
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # Enable connection health checks
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
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


async def check_migrations_current() -> bool:
    """
    Check if database migrations are up to date.
    Returns True if migrations are current, False otherwise.
    """
    try:
        async with engine.connect() as conn:
            # Check if alembic_version table exists
            result = await conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            version = result.scalar()
            if version:
                logger.info(f"Database migration version: {version}")
                return True
            return False
    except Exception:
        # Table doesn't exist or other error
        return False


async def init_db():
    """
    Initialize database connection and verify migrations.

    NOTE: This no longer creates tables automatically.
    Use 'alembic upgrade head' to run migrations.
    """
    from app.models.database import Base

    try:
        # Test database connection
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection established successfully")

        # Check if migrations are current
        if not await check_migrations_current():
            if settings.is_production:
                logger.error(
                    "Database migrations not applied! "
                    "Run 'alembic upgrade head' before starting in production."
                )
                raise RuntimeError("Database migrations required in production")
            else:
                logger.warning(
                    "Database migrations not detected. "
                    "Run 'alembic upgrade head' to apply migrations. "
                    "Falling back to create_all for development..."
                )
                # In development, fall back to create_all for convenience
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                logger.info("Development tables created via create_all")
        else:
            logger.info("Database migrations are current")

    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")
        if settings.is_production:
            raise RuntimeError(f"Database initialization failed in production: {e}")
        else:
            logger.warning(
                "Database init failed but continuing in development mode. "
                "Some features requiring database will not work."
            )


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
