"""
Migration script to add session_id column to chat_history table.

This fixes the database schema mismatch where the ChatHistory model has session_id
but the actual MySQL table is missing this column.
"""
import asyncio
import sys
from sqlalchemy import text
from app.core.database import get_db_context
from app.core.config import settings


async def add_session_id_column():
    """Add session_id column to chat_history table if it doesn't exist."""

    print("🔧 Starting migration: Adding session_id column to chat_history table...")

    async with get_db_context() as db:
        try:
            # Check if column exists
            check_query = text("""
                SELECT COUNT(*) as count
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = :database_name
                AND TABLE_NAME = 'chat_history'
                AND COLUMN_NAME = 'session_id'
            """)

            result = await db.execute(
                check_query,
                {"database_name": settings.mysql_database}
            )
            row = result.fetchone()

            if row and row[0] > 0:
                print("✅ Column 'session_id' already exists in chat_history table. No migration needed.")
                return

            print("📋 Column 'session_id' not found. Adding it now...")

            # Add the column
            alter_query = text("""
                ALTER TABLE chat_history
                ADD COLUMN session_id VARCHAR(255) NOT NULL DEFAULT 'legacy-session',
                ADD INDEX idx_user_session (user_id, session_id)
            """)

            await db.execute(alter_query)
            await db.commit()

            print("✅ Successfully added session_id column to chat_history table!")
            print("✅ Added composite index on (user_id, session_id)")

            # Update legacy rows to have unique session IDs per user+datasource
            update_query = text("""
                UPDATE chat_history
                SET session_id = CONCAT('legacy-', user_id, '-', datasource)
                WHERE session_id = 'legacy-session'
            """)

            result = await db.execute(update_query)
            await db.commit()

            rows_updated = result.rowcount
            print(f"✅ Updated {rows_updated} existing rows with unique session IDs")

        except Exception as e:
            print(f"❌ Migration failed: {e}")
            await db.rollback()
            raise

    print("\n🎉 Migration completed successfully!")
    print("💡 You can now restart your backend server.")


if __name__ == "__main__":
    try:
        asyncio.run(add_session_id_column())
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Migration failed with error: {e}")
        sys.exit(1)
