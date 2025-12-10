"""Test script for authentication system.

This script helps verify that the authentication system is set up correctly.
"""

import asyncio
import sys
from datetime import datetime


async def test_database_connection():
    """Test database connection."""
    print("\n=== Testing Database Connection ===")
    try:
        from app.core.database import engine

        async with engine.connect() as conn:
            result = await conn.execute("SELECT 1")
            print("✓ Database connection successful")
            return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False


async def test_database_tables():
    """Test if database tables are created."""
    print("\n=== Testing Database Tables ===")
    try:
        from app.core.database import engine
        from sqlalchemy import text

        async with engine.connect() as conn:
            # Check if users table exists
            result = await conn.execute(
                text("SHOW TABLES LIKE 'users'")
            )
            users_exists = result.fetchone() is not None

            # Check if chat_history table exists
            result = await conn.execute(
                text("SHOW TABLES LIKE 'chat_history'")
            )
            chat_history_exists = result.fetchone() is not None

            if users_exists:
                print("✓ Users table exists")
            else:
                print("✗ Users table not found")

            if chat_history_exists:
                print("✓ Chat history table exists")
            else:
                print("✗ Chat history table not found")

            return users_exists and chat_history_exists
    except Exception as e:
        print(f"✗ Error checking tables: {e}")
        return False


async def test_jwt_creation():
    """Test JWT token creation and validation."""
    print("\n=== Testing JWT Token Creation ===")
    try:
        from app.services.auth_service import auth_service

        # Create test token
        test_data = {"user_id": "test-user-123", "email": "test@example.com"}
        token = auth_service.create_access_token(test_data)

        print(f"✓ JWT token created: {token[:50]}...")

        # Decode token
        decoded = auth_service.decode_access_token(token)

        if decoded and decoded.get("user_id") == "test-user-123":
            print("✓ JWT token decoded successfully")
            print(f"  User ID: {decoded.get('user_id')}")
            print(f"  Email: {decoded.get('email')}")
            return True
        else:
            print("✗ JWT token validation failed")
            return False
    except Exception as e:
        print(f"✗ JWT test failed: {e}")
        return False


async def test_config():
    """Test configuration settings."""
    print("\n=== Testing Configuration ===")
    try:
        from app.core.config import settings

        required_settings = {
            "MySQL Host": settings.mysql_host,
            "MySQL Database": settings.mysql_database,
            "Google OAuth Client ID": settings.google_oauth_client_id[:20] + "..." if settings.google_oauth_client_id else "NOT SET",
            "JWT Secret Key": "SET" if settings.jwt_secret_key else "NOT SET",
            "JWT Algorithm": settings.jwt_algorithm,
        }

        all_set = True
        for name, value in required_settings.items():
            if value and value != "NOT SET":
                print(f"✓ {name}: {value}")
            else:
                print(f"✗ {name}: NOT SET")
                all_set = False

        return all_set
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False


async def test_create_test_user():
    """Test creating a user in the database."""
    print("\n=== Testing User Creation ===")
    try:
        from app.core.database import get_db_context
        from app.services.auth_service import auth_service

        async with get_db_context() as db:
            # Try to create a test user
            user = await auth_service.get_or_create_user(
                db=db,
                email="test@mosaic.local",
                google_id="test-google-id-123",
                name="Test User",
                profile_picture="https://example.com/avatar.jpg",
            )

            print(f"✓ User created/retrieved: {user.email}")
            print(f"  ID: {user.id}")
            print(f"  Name: {user.name}")
            print(f"  Google ID: {user.google_id}")

            return True
    except Exception as e:
        print(f"✗ User creation test failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Authentication System Test Suite")
    print("=" * 60)

    results = []

    # Test configuration
    results.append(await test_config())

    # Test database connection
    results.append(await test_database_connection())

    # Test database tables
    results.append(await test_database_tables())

    # Test JWT
    results.append(await test_jwt_creation())

    # Test user creation
    results.append(await test_create_test_user())

    print("\n" + "=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)

    if all(results):
        print("\n✓ All tests passed! Authentication system is ready.")
        return 0
    else:
        print("\n✗ Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
