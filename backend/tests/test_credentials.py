#!/usr/bin/env python3
"""Test credential management and encryption."""

import asyncio
import os
from app.services.credential_service import credential_service
from app.core.database import async_session_maker
from app.core.config import settings


async def test_credentials():
    """Test credential management."""
    print("=" * 80)
    print("Testing Credential Management")
    print("=" * 80)

    # Test 1: Verify ENCRYPTION_KEY is loaded
    print("\n\nTEST 1: Verify ENCRYPTION_KEY")
    print("-" * 80)
    try:
        encryption_key = settings.encryption_key
        if encryption_key:
            print(f"✅ ENCRYPTION_KEY is loaded: {encryption_key[:20]}...{encryption_key[-20:]}")
        else:
            print("⚠️ ENCRYPTION_KEY is not set in .env (will use generated key)")
    except Exception as e:
        print(f"❌ Failed to load ENCRYPTION_KEY: {e}")

    # Test 2: Test encryption/decryption
    print("\n\nTEST 2: Test Encryption/Decryption")
    print("-" * 80)
    try:
        test_credentials = {
            "jira_url": "https://example.atlassian.net",
            "jira_email": "test@example.com",
            "jira_api_token": "test_token_12345",
        }

        # Encrypt
        encrypted = credential_service._encrypt_credentials(test_credentials)
        print(f"Encrypted: {encrypted[:50]}...")

        # Decrypt
        decrypted = credential_service._decrypt_credentials(encrypted)
        print(f"Decrypted: {decrypted}")

        # Verify
        if decrypted == test_credentials:
            print("✅ Encryption/Decryption works correctly!")
        else:
            print("❌ Encryption/Decryption mismatch!")
    except Exception as e:
        print(f"❌ Encryption test failed: {e}")
        import traceback
        traceback.print_exc()

    # Test 3: Test in-memory session-based credentials (anonymous users)
    print("\n\nTEST 3: Test Session-Based Credentials (Anonymous Users)")
    print("-" * 80)
    try:
        test_session_id = "test_session_12345"
        test_creds = {
            "jira_url": "https://test.atlassian.net",
            "jira_email": "test@test.com",
            "jira_api_token": "session_token",
        }

        # Save credentials
        await credential_service.save_credentials(
            datasource="jira",
            credentials=test_creds,
            session_id=test_session_id,
        )
        print(f"✅ Saved credentials for session {test_session_id[:8]}...")

        # Retrieve credentials
        retrieved = await credential_service.get_credentials(
            datasource="jira",
            session_id=test_session_id,
        )

        if retrieved == test_creds:
            print(f"✅ Retrieved credentials match: {retrieved}")
        else:
            print(f"❌ Retrieved credentials don't match!")

        # Check if credentials exist
        has_creds = await credential_service.has_credentials(
            datasource="jira",
            session_id=test_session_id,
        )
        print(f"✅ has_credentials check: {has_creds}")

        # Delete credentials
        await credential_service.delete_credentials(
            datasource="jira",
            session_id=test_session_id,
        )
        print(f"✅ Deleted credentials for session {test_session_id[:8]}...")

        # Verify deletion
        deleted_check = await credential_service.has_credentials(
            datasource="jira",
            session_id=test_session_id,
        )
        print(f"✅ Credentials deleted (should be False): {deleted_check}")

    except Exception as e:
        print(f"❌ Session credentials test failed: {e}")
        import traceback
        traceback.print_exc()

    # Test 4: Test database-backed credentials (authenticated users)
    print("\n\nTEST 4: Test Database-Backed Credentials (Authenticated Users)")
    print("-" * 80)
    try:
        test_user_id = "test_user_db_12345"
        test_db_creds = {
            "jira_url": "https://db-test.atlassian.net",
            "jira_email": "dbtest@test.com",
            "jira_api_token": "db_token_12345",
        }

        # Use database session
        async with async_session_maker() as db:
            # Save credentials
            await credential_service.save_credentials(
                datasource="jira",
                credentials=test_db_creds,
                db=db,
                user_id=test_user_id,
            )
            print(f"✅ Saved credentials to database for user {test_user_id[:8]}...")

            # Retrieve credentials
            retrieved_db = await credential_service.get_credentials(
                datasource="jira",
                db=db,
                user_id=test_user_id,
            )

            if retrieved_db == test_db_creds:
                print(f"✅ Retrieved database credentials match: {retrieved_db}")
            else:
                print(f"❌ Retrieved database credentials don't match!")

            # Check if credentials exist
            has_db_creds = await credential_service.has_credentials(
                datasource="jira",
                db=db,
                user_id=test_user_id,
            )
            print(f"✅ Database has_credentials check: {has_db_creds}")

            # Delete credentials
            await credential_service.delete_credentials(
                datasource="jira",
                db=db,
                user_id=test_user_id,
            )
            print(f"✅ Deleted database credentials for user {test_user_id[:8]}...")

            # Verify deletion
            deleted_db_check = await credential_service.has_credentials(
                datasource="jira",
                db=db,
                user_id=test_user_id,
            )
            print(f"✅ Database credentials deleted (should be False): {deleted_db_check}")

    except Exception as e:
        print(f"❌ Database credentials test failed: {e}")
        import traceback
        traceback.print_exc()

    # Test 5: Check JIRA credentials from .env
    print("\n\nTEST 5: Check JIRA Credentials from .env")
    print("-" * 80)
    try:
        print(f"JIRA_URL: {settings.jira_url}")
        print(f"JIRA_EMAIL: {settings.jira_email}")
        print(f"JIRA_API_TOKEN: {settings.jira_api_token[:20]}...{settings.jira_api_token[-10:]}")
        print("✅ JIRA credentials loaded from .env")
    except Exception as e:
        print(f"❌ Failed to load JIRA credentials: {e}")

    print("\n" + "=" * 80)
    print("Credential tests completed!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_credentials())
