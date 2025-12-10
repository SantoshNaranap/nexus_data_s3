"""Credential management service."""

import logging
import json
from typing import Dict, Optional
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings

logger = logging.getLogger(__name__)


class CredentialService:
    """
    Service for managing user credentials.

    For authenticated users: Stores credentials in database with encryption.
    For anonymous users: Stores credentials in-memory per session (backward compatibility).
    """

    def __init__(self):
        # In-memory storage for anonymous users (session-based)
        # session_id -> datasource -> credentials
        self._credentials: Dict[str, Dict[str, Dict[str, str]]] = {}
        # session_id -> last_access_time
        self._session_timestamps: Dict[str, datetime] = {}
        # Session timeout (24 hours)
        self._session_timeout = timedelta(hours=24)

        # Encryption key from settings (guaranteed to be valid by config validator)
        encryption_key = settings.encryption_key
        self.cipher = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)

    def _encrypt_credentials(self, credentials: Dict[str, str]) -> str:
        """Encrypt credentials using Fernet."""
        credentials_json = json.dumps(credentials)
        encrypted = self.cipher.encrypt(credentials_json.encode())
        return encrypted.decode()

    def _decrypt_credentials(self, encrypted_data: str) -> Dict[str, str]:
        """Decrypt credentials using Fernet."""
        decrypted = self.cipher.decrypt(encrypted_data.encode())
        return json.loads(decrypted.decode())

    # ============ Multi-tenant methods (Database storage) ============

    async def save_credentials(
        self,
        datasource: str,
        credentials: Dict[str, str],
        db: Optional[AsyncSession] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """
        Save credentials for a datasource.

        For authenticated users (user_id provided): Store in database.
        For anonymous users (session_id only): Store in-memory.
        """
        if user_id and db:
            # Authenticated user - use database
            try:
                from app.models.database import UserCredential

                # Encrypt credentials
                encrypted_credentials = self._encrypt_credentials(credentials)

                # Check if credentials already exist
                stmt = select(UserCredential).where(
                    UserCredential.user_id == user_id,
                    UserCredential.datasource == datasource
                )
                result = await db.execute(stmt)
                existing_cred = result.scalar_one_or_none()

                if existing_cred:
                    # Update existing credentials
                    existing_cred.encrypted_credentials = encrypted_credentials
                    existing_cred.updated_at = datetime.now()
                    logger.info(f"Updated credentials for user {user_id[:8]}... datasource {datasource}")
                else:
                    # Create new credentials
                    new_cred = UserCredential(
                        user_id=user_id,
                        datasource=datasource,
                        encrypted_credentials=encrypted_credentials
                    )
                    db.add(new_cred)
                    logger.info(f"Created credentials for user {user_id[:8]}... datasource {datasource}")

                await db.commit()

            except SQLAlchemyError as e:
                logger.error(f"Database error saving credentials: {str(e)}")
                if db:
                    await db.rollback()
                raise
        elif session_id:
            # Anonymous user - use in-memory storage (backward compatibility)
            self._cleanup_expired_sessions()

            if session_id not in self._credentials:
                self._credentials[session_id] = {}

            self._credentials[session_id][datasource] = credentials
            self._session_timestamps[session_id] = datetime.now()

            logger.info(f"Saved credentials for {datasource} in session {session_id[:8]}...")
        else:
            raise ValueError("Either user_id with db or session_id must be provided")

    async def get_credentials(
        self,
        datasource: str,
        db: Optional[AsyncSession] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        """
        Get credentials for a datasource.

        For authenticated users (user_id provided): Retrieve from database.
        For anonymous users (session_id only): Retrieve from in-memory storage.
        """
        if user_id and db:
            # Authenticated user - get from database
            try:
                from app.models.database import UserCredential

                stmt = select(UserCredential).where(
                    UserCredential.user_id == user_id,
                    UserCredential.datasource == datasource
                )
                result = await db.execute(stmt)
                cred = result.scalar_one_or_none()

                if not cred:
                    logger.info(f"No credentials found for user {user_id[:8]}... datasource {datasource}")
                    return None

                # Decrypt credentials
                credentials = self._decrypt_credentials(cred.encrypted_credentials)

                logger.info(f"Retrieved credentials for user {user_id[:8]}... datasource {datasource}")
                return credentials

            except SQLAlchemyError as e:
                logger.error(f"Database error retrieving credentials: {str(e)}")
                raise
        elif session_id:
            # Anonymous user - get from in-memory storage
            self._cleanup_expired_sessions()

            if session_id not in self._credentials:
                return None

            credentials = self._credentials[session_id].get(datasource)

            if credentials:
                self._session_timestamps[session_id] = datetime.now()

            return credentials
        else:
            return None

    async def has_credentials(
        self,
        datasource: str,
        db: Optional[AsyncSession] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """
        Check if credentials exist for a datasource.

        For authenticated users: Check database.
        For anonymous users: Check in-memory storage.
        """
        if user_id and db:
            # Check database
            try:
                from app.models.database import UserCredential

                stmt = select(UserCredential).where(
                    UserCredential.user_id == user_id,
                    UserCredential.datasource == datasource
                )
                result = await db.execute(stmt)
                cred = result.scalar_one_or_none()
                return cred is not None

            except SQLAlchemyError as e:
                logger.error(f"Database error checking credentials: {str(e)}")
                return False
        elif session_id:
            # Check in-memory storage
            return (
                session_id in self._credentials
                and datasource in self._credentials[session_id]
            )
        else:
            return False

    async def delete_credentials(
        self,
        datasource: str,
        db: Optional[AsyncSession] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """
        Delete credentials for a datasource.

        For authenticated users: Delete from database.
        For anonymous users: Delete from in-memory storage.
        """
        if user_id and db:
            # Delete from database
            try:
                from app.models.database import UserCredential

                stmt = select(UserCredential).where(
                    UserCredential.user_id == user_id,
                    UserCredential.datasource == datasource
                )
                result = await db.execute(stmt)
                cred = result.scalar_one_or_none()

                if cred:
                    await db.delete(cred)
                    await db.commit()
                    logger.info(f"Deleted credentials for user {user_id[:8]}... datasource {datasource}")
                else:
                    logger.warning(f"Credentials not found for user {user_id[:8]}... datasource {datasource}")

            except SQLAlchemyError as e:
                logger.error(f"Database error deleting credentials: {str(e)}")
                if db:
                    await db.rollback()
                raise
        elif session_id:
            # Delete from in-memory storage
            if session_id in self._credentials:
                self._credentials[session_id].pop(datasource, None)
                logger.info(f"Deleted credentials for {datasource} from session {session_id[:8]}...")

    def delete_session(self, session_id: str) -> None:
        """Delete all credentials for a session."""
        self._credentials.pop(session_id, None)
        self._session_timestamps.pop(session_id, None)
        logger.info(f"Deleted session {session_id[:8]}...")

    def _cleanup_expired_sessions(self) -> None:
        """Clean up expired sessions."""
        now = datetime.now()
        expired_sessions = [
            session_id
            for session_id, timestamp in self._session_timestamps.items()
            if now - timestamp > self._session_timeout
        ]

        for session_id in expired_sessions:
            self.delete_session(session_id)
            logger.info(f"Cleaned up expired session {session_id[:8]}...")


# Global credential service instance
credential_service = CredentialService()
