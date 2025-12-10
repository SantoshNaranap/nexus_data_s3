"""Setup script to create ConnectorMCP database and tables."""
import asyncio
import aiomysql
from app.core.config import settings


async def setup_database():
    """Create database and tables."""
    # Connect without specifying a database
    conn = await aiomysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
    )

    try:
        async with conn.cursor() as cursor:
            # Create database
            print("Creating database 'connectorMCP'...")
            await cursor.execute(
                "CREATE DATABASE IF NOT EXISTS connectorMCP "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            print("✅ Database created!")

            # Use the new database
            await cursor.execute("USE connectorMCP")

            # Create users table
            print("\nCreating 'users' table...")
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id VARCHAR(36) PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(255),
                    google_id VARCHAR(255) UNIQUE NOT NULL,
                    profile_picture TEXT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_email (email),
                    INDEX idx_google_id (google_id)
                )
            """)
            print("✅ Users table created!")

            # Create chat_history table
            print("\nCreating 'chat_history' table...")
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    datasource VARCHAR(50) NOT NULL,
                    messages JSON NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_user_id (user_id)
                )
            """)
            print("✅ Chat history table created!")

            await conn.commit()
            print("\n🎉 Database setup complete!")
            print("\nNext step: Update your .env files to use:")
            print("MYSQL_DATABASE=connectorMCP")

    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(setup_database())
