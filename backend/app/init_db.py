"""Database initialization script.

This script can be run standalone to create database tables or called during app startup.
"""

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def initialize_database():
    """Initialize the database by creating all tables."""
    try:
        from app.core.database import init_db, engine
        from app.models.database import Base

        logger.info("Starting database initialization...")

        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database tables created successfully!")
        logger.info("Tables created: users, chat_history")

        return True
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        return False


async def drop_all_tables():
    """Drop all tables - USE WITH CAUTION!"""
    try:
        from app.core.database import engine
        from app.models.database import Base

        logger.warning("Dropping all database tables...")

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        logger.info("All tables dropped successfully")
        return True
    except Exception as e:
        logger.error(f"Error dropping tables: {e}")
        return False


async def reset_database():
    """Reset database by dropping and recreating all tables - USE WITH CAUTION!"""
    logger.warning("Resetting database - this will delete all data!")
    if await drop_all_tables():
        return await initialize_database()
    return False


if __name__ == "__main__":
    """Run this script directly to initialize the database."""
    import argparse

    parser = argparse.ArgumentParser(description="Database initialization script")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset database (drop and recreate all tables)",
    )
    args = parser.parse_args()

    if args.reset:
        confirmation = input(
            "Are you sure you want to reset the database? This will delete all data! (yes/no): "
        )
        if confirmation.lower() == "yes":
            success = asyncio.run(reset_database())
        else:
            logger.info("Database reset cancelled")
            sys.exit(0)
    else:
        success = asyncio.run(initialize_database())

    sys.exit(0 if success else 1)
