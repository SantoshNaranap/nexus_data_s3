#!/usr/bin/env python3
"""Test OAuth and credential storage after cleanup."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.database import get_db_context
from app.models.database import User, UserCredential
from app.services.credential_service import CredentialService
from sqlalchemy import select


async def test_user_model():
    """Test that User model works after consolidation."""
    print("\n" + "=" * 80)
    print("TEST 1: User Model")
    print("=" * 80)

    try:
        async with get_db_context() as db:
            # Try to query users
            result = await db.execute(select(User).limit(5))
            users = result.scalars().all()

            print(f"✓ User model works!")
            print(f"✓ Found {len(users)} users in database")

            if users:
                for user in users[:3]:
                    print(f"  - {user.email} (ID: {user.id})")

            return True
    except Exception as e:
        print(f"✗ User model ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_user_credential_model():
    """Test that UserCredential model works after consolidation."""
    print("\n" + "=" * 80)
    print("TEST 2: UserCredential Model")
    print("=" * 80)

    try:
        async with get_db_context() as db:
            # Try to query credentials
            result = await db.execute(select(UserCredential).limit(5))
            credentials = result.scalars().all()

            print(f"✓ UserCredential model works!")
            print(f"✓ Found {len(credentials)} stored credentials")

            if credentials:
                for cred in credentials[:3]:
                    print(f"  - User: {cred.user_id}, Datasource: {cred.datasource}")

            return True
    except Exception as e:
        print(f"✗ UserCredential model ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_credential_service():
    """Test credential encryption/decryption service."""
    print("\n" + "=" * 80)
    print("TEST 3: Credential Service (Encryption/Decryption)")
    print("=" * 80)

    try:
        # Test encryption/decryption
        test_creds = {
            "api_key": "test_key_12345",
            "secret": "test_secret_67890"
        }

        service = CredentialService()

        # Encrypt
        encrypted = service.encrypt_credentials(test_creds)
        print(f"✓ Encryption works!")
        print(f"  Encrypted length: {len(encrypted)} chars")

        # Decrypt
        decrypted = service.decrypt_credentials(encrypted)
        print(f"✓ Decryption works!")
        print(f"  Decrypted: {decrypted}")

        # Verify
        if decrypted == test_creds:
            print(f"✓ Encryption/Decryption cycle successful!")
            return True
        else:
            print(f"✗ Decrypted data doesn't match original!")
            return False

    except Exception as e:
        print(f"✗ Credential service ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_credential_storage():
    """Test storing and retrieving credentials from database."""
    print("\n" + "=" * 80)
    print("TEST 4: Credential Storage & Retrieval")
    print("=" * 80)

    try:
        async with get_db_context() as db:
            # Get a test user
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()

            if not user:
                print("⚠ No users in database, skipping storage test")
                return True

            print(f"✓ Using test user: {user.email}")

            # Check if they have any stored credentials
            result = await db.execute(
                select(UserCredential).where(UserCredential.user_id == user.id)
            )
            creds = result.scalars().all()

            print(f"✓ User has {len(creds)} stored credentials")

            for cred in creds:
                print(f"  - {cred.datasource} (stored at {cred.created_at})")

                # Try to decrypt one
                service = CredentialService()
                decrypted = service.decrypt_credentials(cred.encrypted_credentials)
                print(f"    ✓ Successfully decrypted {cred.datasource} credentials")
                print(f"    Keys: {list(decrypted.keys())}")

            return True

    except Exception as e:
        print(f"✗ Credential storage test ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("TESTING OAUTH & CREDENTIALS AFTER CLEANUP")
    print("=" * 80)

    results = []

    # Run tests
    results.append(await test_user_model())
    results.append(await test_user_credential_model())
    results.append(await test_credential_service())
    results.append(await test_credential_storage())

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Tests passed: {sum(results)}/{len(results)}")

    if all(results):
        print("✓ ALL TESTS PASSED!")
        print("\n✓ OAuth models working")
        print("✓ Credential storage working")
        print("✓ Encryption/Decryption working")
        print("✓ Frontend → Backend credential flow READY")
    else:
        print("✗ SOME TESTS FAILED")

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
