"""Credential management service with multi-tenant support."""

import logging
import json
import asyncio
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings

logger = logging.getLogger(__name__)

# Credential source types for priority tracking
CRED_SOURCE_USER = "user"       # User's personal credentials
CRED_SOURCE_TENANT = "tenant"   # Organization-level credentials
CRED_SOURCE_DEFAULT = "default" # Default env var credentials


class CredentialService:
    """
    Service for managing user credentials.

    For authenticated users: Stores credentials in database with encryption.
    For anonymous users: Stores credentials in-memory per session (backward compatibility).

    Supports encryption key rotation:
    - New credentials are encrypted with the current key (v2 format: "v2:<ciphertext>")
    - Legacy credentials (no prefix or v1 prefix) are decrypted with appropriate key
    - Credentials are re-encrypted with current key on read (transparent migration)
    """

    # Current encryption version
    CURRENT_VERSION = "v2"

    def __init__(self):
        # In-memory storage for anonymous users (session-based)
        # session_id -> datasource -> credentials
        self._credentials: Dict[str, Dict[str, Dict[str, str]]] = {}
        # session_id -> last_access_time
        self._session_timestamps: Dict[str, datetime] = {}
        # Session timeout (24 hours)
        self._session_timeout = timedelta(hours=24)
        # Lock for thread-safe access to in-memory credentials
        self._lock = asyncio.Lock()

        # Current encryption key (v2) from settings
        encryption_key = settings.encryption_key
        self.cipher = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)

        # Legacy encryption key (v1) for decryption during rotation
        self.cipher_v1 = None
        if settings.encryption_key_v1:
            legacy_key = settings.encryption_key_v1
            self.cipher_v1 = Fernet(legacy_key.encode() if isinstance(legacy_key, str) else legacy_key)

    def _encrypt_credentials(self, credentials: Dict[str, str]) -> str:
        """
        Encrypt credentials using current Fernet key with version prefix.

        Format: "v2:<base64_ciphertext>"
        """
        credentials_json = json.dumps(credentials)
        encrypted = self.cipher.encrypt(credentials_json.encode())
        return f"{self.CURRENT_VERSION}:{encrypted.decode()}"

    def _decrypt_credentials(self, encrypted_data: str) -> Dict[str, str]:
        """
        Decrypt credentials, handling both versioned and legacy formats.

        Supports:
        - "v2:<ciphertext>" - Current format, uses current key
        - "v1:<ciphertext>" - Legacy versioned format, uses v1 key
        - "<ciphertext>" - Legacy unversioned format, tries current then v1
        """
        # Check for versioned format
        if encrypted_data.startswith("v2:"):
            ciphertext = encrypted_data[3:]
            decrypted = self.cipher.decrypt(ciphertext.encode())
            return json.loads(decrypted.decode())

        if encrypted_data.startswith("v1:"):
            if not self.cipher_v1:
                raise ValueError("v1 credentials found but ENCRYPTION_KEY_V1 not configured")
            ciphertext = encrypted_data[3:]
            decrypted = self.cipher_v1.decrypt(ciphertext.encode())
            return json.loads(decrypted.decode())

        # Legacy unversioned format - try current key first, then v1
        try:
            decrypted = self.cipher.decrypt(encrypted_data.encode())
            return json.loads(decrypted.decode())
        except Exception:
            if self.cipher_v1:
                decrypted = self.cipher_v1.decrypt(encrypted_data.encode())
                return json.loads(decrypted.decode())
            raise

    def _needs_reencryption(self, encrypted_data: str) -> bool:
        """Check if encrypted data needs to be re-encrypted with current key."""
        return not encrypted_data.startswith(f"{self.CURRENT_VERSION}:")

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
            async with self._lock:
                await self._cleanup_expired_sessions_locked()

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
            async with self._lock:
                await self._cleanup_expired_sessions_locked()

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
        """Clean up expired sessions (non-locked version for backward compatibility)."""
        now = datetime.now()
        expired_sessions = [
            session_id
            for session_id, timestamp in self._session_timestamps.items()
            if now - timestamp > self._session_timeout
        ]

        for session_id in expired_sessions:
            self.delete_session(session_id)
            logger.info(f"Cleaned up expired session {session_id[:8]}...")

    async def _cleanup_expired_sessions_locked(self) -> None:
        """Clean up expired sessions (must be called with lock held)."""
        now = datetime.now()
        expired_sessions = [
            session_id
            for session_id, timestamp in self._session_timestamps.items()
            if now - timestamp > self._session_timeout
        ]

        for session_id in expired_sessions:
            self._credentials.pop(session_id, None)
            self._session_timestamps.pop(session_id, None)
            logger.info(f"Cleaned up expired session {session_id[:8]}...")

    # ============ Multi-tenant credential resolution ============

    async def get_effective_credentials(
        self,
        datasource: str,
        db: AsyncSession,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, str]], str]:
        """
        Get effective credentials for a datasource with priority resolution.

        Priority order:
        1. User's personal credentials (if set) - HIGHEST
        2. Tenant/org credentials (if connected)
        3. Default env var credentials - LOWEST

        Args:
            datasource: The datasource type (slack, github, jira, etc.)
            db: Database session
            user_id: Optional user ID for authenticated users
            session_id: Optional session ID for anonymous users

        Returns:
            Tuple of (credentials dict or None, source type)
            Source type is one of: "user", "tenant", "default", or "" if none found
        """
        # 1. Try user's personal credentials first
        if user_id:
            user_creds = await self.get_credentials(
                datasource=datasource,
                db=db,
                user_id=user_id,
            )
            if user_creds:
                logger.info(f"Using user credentials for {datasource}")
                return user_creds, CRED_SOURCE_USER

        # For anonymous users, check session storage
        if session_id and not user_id:
            session_creds = await self.get_credentials(
                datasource=datasource,
                session_id=session_id,
            )
            if session_creds:
                logger.info(f"Using session credentials for {datasource}")
                return session_creds, CRED_SOURCE_USER

        # 2. Try tenant/org credentials if user belongs to a tenant
        if user_id and db:
            try:
                from app.models.database import User
                from app.services.tenant_datasource_service import tenant_datasource_service

                # Get user to find their tenant
                result = await db.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()

                if user and user.tenant_id:
                    # Get tenant credentials
                    tenant_creds = await tenant_datasource_service.get_decrypted_credentials(
                        db=db,
                        tenant_id=user.tenant_id,
                        datasource=datasource,
                    )
                    if tenant_creds:
                        logger.info(f"Using tenant credentials for {datasource}")
                        return tenant_creds, CRED_SOURCE_TENANT

            except Exception as e:
                logger.warning(f"Error getting tenant credentials: {e}")

        # 3. Return None - caller should fall back to env var defaults
        logger.info(f"No stored credentials found for {datasource}, using defaults")
        return None, CRED_SOURCE_DEFAULT

    def get_default_credentials(self, datasource: str) -> Optional[Dict[str, str]]:
        """
        Get default credentials from environment variables.

        This is a fallback when no user or tenant credentials are found.

        Args:
            datasource: The datasource type

        Returns:
            Credentials dict or None if not configured
        """
        datasource_lower = datasource.lower()

        if datasource_lower == "slack":
            if settings.slack_bot_token:
                return {
                    "bot_token": settings.slack_bot_token,
                    "user_token": settings.slack_user_token,
                    "app_token": settings.slack_app_token,
                }
        elif datasource_lower == "github":
            if settings.github_token:
                return {
                    "access_token": settings.github_token,
                }
        elif datasource_lower == "jira":
            if settings.jira_url and settings.jira_api_token:
                return {
                    "url": settings.jira_url,
                    "email": settings.jira_email,
                    "api_token": settings.jira_api_token,
                }
        elif datasource_lower == "mysql":
            if settings.mysql_host:
                return {
                    "host": settings.mysql_host,
                    "port": str(settings.mysql_port),
                    "user": settings.mysql_user,
                    "password": settings.mysql_password,
                    "database": settings.mysql_database,
                }
        elif datasource_lower == "s3":
            if settings.aws_access_key_id:
                return {
                    "aws_access_key_id": settings.aws_access_key_id,
                    "aws_secret_access_key": settings.aws_secret_access_key,
                    "aws_region": settings.aws_default_region,
                }

        return None

    async def get_credentials_with_fallback(
        self,
        datasource: str,
        db: AsyncSession,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, str]], str]:
        """
        Get credentials with automatic fallback to defaults.

        Combines get_effective_credentials and get_default_credentials.

        Args:
            datasource: The datasource type
            db: Database session
            user_id: Optional user ID
            session_id: Optional session ID

        Returns:
            Tuple of (credentials dict, source type)
        """
        # First try stored credentials (user -> tenant)
        creds, source = await self.get_effective_credentials(
            datasource=datasource,
            db=db,
            user_id=user_id,
            session_id=session_id,
        )

        if creds:
            return creds, source

        # Fall back to env var defaults
        default_creds = self.get_default_credentials(datasource)
        if default_creds:
            return default_creds, CRED_SOURCE_DEFAULT

        return None, ""


# Global credential service instance
credential_service = CredentialService()
