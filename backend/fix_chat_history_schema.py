"""
Recreate chat_history table with the correct schema to match the ChatHistory model.

The current table has an old schema with a 'messages' JSON column.
The model expects 'role' and 'content' columns for individual message rows.
"""
import asyncio
import sys
from sqlalchemy import text
from app.core.database import get_db_context


async def recreate_table():
    """Drop and recreate chat_history table with correct schema."""

    print("🔧 Fixing chat_history table schema...")

    async with get_db_context() as db:
        try:
            # Drop the old table
            print("📋 Dropping old chat_history table...")
            await db.execute(text("DROP TABLE IF EXISTS chat_history"))
            await db.commit()
            print("✅ Old table dropped")

            # Create new table with correct schema
            print("📋 Creating new chat_history table with correct schema...")
            create_query = text("""
                CREATE TABLE chat_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    session_id VARCHAR(255) NOT NULL,
                    datasource VARCHAR(50) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_user_datasource_created (user_id, datasource, created_at),
                    INDEX idx_user_session (user_id, session_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            await db.execute(create_query)
            await db.commit()

            print("✅ Successfully created chat_history table with correct schema!")
            print("\n📋 New table structure:")
            print("-" * 60)
            print("id               INT (AUTO_INCREMENT)")
            print("user_id          VARCHAR(255)")
            print("session_id       VARCHAR(255)")
            print("datasource       VARCHAR(50)")
            print("role             VARCHAR(20)")
            print("content          TEXT")
            print("created_at       DATETIME")
            print("-" * 60)

        except Exception as e:
            print(f"❌ Migration failed: {e}")
            await db.rollback()
            raise

    print("\n🎉 Migration completed successfully!")
    print("💡 You can now restart your backend server.")


if __name__ == "__main__":
    try:
        asyncio.run(recreate_table())
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Migration failed with error: {e}")
        sys.exit(1)
