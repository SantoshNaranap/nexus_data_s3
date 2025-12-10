"""Check the actual structure of the chat_history table."""
import asyncio
from sqlalchemy import text
from app.core.database import get_db_context


async def check_table():
    """Check chat_history table structure."""
    async with get_db_context() as db:
        # Get table structure
        result = await db.execute(text("DESCRIBE chat_history"))
        rows = result.fetchall()

        print("\n📋 Current chat_history table structure:")
        print("-" * 60)
        for row in rows:
            print(f"{row[0]:<20} {row[1]:<20} {row[2]:<10}")
        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(check_table())
