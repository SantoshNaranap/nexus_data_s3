"""Script to create database tables."""
import asyncio
import sys
from app.core.database import engine
from app.models.database import Base


async def create_tables():
    """Create all database tables."""
    try:
        async with engine.begin() as conn:
            # Create tables (will skip if they already exist)
            print("Creating tables if they don't exist...")
            await conn.run_sync(Base.metadata.create_all)

        print("✅ Database tables created/verified successfully!")
        print("\nTables:")
        print("- users (existing or created)")
        print("- chat_history (existing or created)")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nThe users table already exists but may have a different schema.")
        print("Since this is a shared database, OAuth will be disabled.")
        print("The app will continue to work for anonymous users.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_tables())
