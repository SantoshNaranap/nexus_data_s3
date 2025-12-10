"""Test credential persistence for authenticated users."""

import asyncio
from sqlalchemy import select

from app.core.database import get_db_context
from app.models.database import User, UserCredential
from app.services.credential_service import credential_service


async def test_credential_persistence():
    """Test that credentials persist across sessions for authenticated users."""
    print("\n=== Testing Credential Persistence ===\n")

    async with get_db_context() as db:
        # Get first user from database
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()

        if not user:
            print("❌ No users found in database. Create a user first by logging in via Google OAuth.")
            return

        print(f"✓ Testing with user: {user.email}")
        print(f"  User ID: {user.id}\n")

        # Test 1: Save JIRA credentials
        print("1. Saving JIRA credentials...")
        test_credentials = {
            "jira_url": "https://test.atlassian.net",
            "jira_email": "test@example.com",
            "jira_api_token": "test_token_12345"
        }

        await credential_service.save_credentials(
            datasource="jira",
            credentials=test_credentials,
            db=db,
            user_id=user.id
        )
        print("✓ Credentials saved to database\n")

        # Test 2: Verify credentials exist in database
        print("2. Checking database...")
        result = await db.execute(
            select(UserCredential).where(
                UserCredential.user_id == user.id,
                UserCredential.datasource == "jira"
            )
        )
        db_cred = result.scalar_one_or_none()

        if db_cred:
            print(f"✓ Found credentials in database")
            print(f"  Datasource: {db_cred.datasource}")
            print(f"  Created: {db_cred.created_at}")
            print(f"  Encrypted: {db_cred.encrypted_credentials[:50]}...\n")
        else:
            print("❌ Credentials not found in database!\n")
            return

        # Test 3: Retrieve and decrypt credentials
        print("3. Retrieving credentials...")
        retrieved = await credential_service.get_credentials(
            datasource="jira",
            db=db,
            user_id=user.id
        )

        if retrieved:
            print("✓ Credentials retrieved and decrypted successfully")
            print(f"  JIRA URL: {retrieved.get('jira_url')}")
            print(f"  JIRA Email: {retrieved.get('jira_email')}")
            print(f"  Token present: {'jira_api_token' in retrieved}\n")
        else:
            print("❌ Failed to retrieve credentials!\n")
            return

        # Test 4: Verify persistence (simulate new session)
        print("4. Simulating new session (new database connection)...")

    # New database session (simulates new login/page refresh)
    async with get_db_context() as db2:
        retrieved_again = await credential_service.get_credentials(
            datasource="jira",
            db=db2,
            user_id=user.id
        )

        if retrieved_again:
            print("✓ Credentials persisted across sessions!")
            print(f"  Still retrievable: {retrieved_again.get('jira_url')}\n")
        else:
            print("❌ Credentials lost after new session!\n")
            return

    print("=" * 50)
    print("✅ ALL TESTS PASSED")
    print("=" * 50)
    print("\nConclusion:")
    print("- Backend credential persistence is working correctly")
    print("- Credentials are saved to database")
    print("- Credentials persist across sessions")
    print("- Issue is likely in the FRONTEND")
    print("\nFrontend checklist:")
    print("1. Is frontend calling POST /api/credentials when user submits?")
    print("2. Is frontend checking GET /api/credentials/{datasource}/status on load?")
    print("3. Is frontend sending JWT auth token in requests?")
    print("4. Is JWT token being refreshed properly?")


if __name__ == "__main__":
    asyncio.run(test_credential_persistence())
