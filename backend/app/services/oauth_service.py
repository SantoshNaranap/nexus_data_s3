"""OAuth service for managing OAuth connections and tokens."""

import logging
import json
import secrets
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.models.database import OAuthConnection
from app.services.oauth_providers import get_oauth_provider, is_oauth_provider
from app.services.oauth_providers.base import OAuthTokens

logger = logging.getLogger(__name__)


class OAuthService:
    """Service for managing OAuth connections."""

    def __init__(self):
        # Encryption cipher (same key as credential_service)
        encryption_key = settings.encryption_key
        self.cipher = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)

        # In-memory state storage (for CSRF protection)
        # state_token -> {user_id, provider, created_at, redirect_uri}
        self._oauth_states: Dict[str, Dict[str, Any]] = {}
        self._state_timeout = timedelta(minutes=10)

    def _encrypt(self, data: str) -> str:
        """Encrypt a string using Fernet."""
        encrypted = self.cipher.encrypt(data.encode())
        return encrypted.decode()

    def _decrypt(self, encrypted_data: str) -> str:
        """Decrypt a string using Fernet."""
        decrypted = self.cipher.decrypt(encrypted_data.encode())
        return decrypted.decode()

    def _cleanup_expired_states(self) -> None:
        """Clean up expired OAuth state tokens."""
        now = datetime.utcnow()
        expired = [
            state for state, data in self._oauth_states.items()
            if now - data["created_at"] > self._state_timeout
        ]
        for state in expired:
            del self._oauth_states[state]

    def generate_state(
        self,
        user_id: str,
        provider: str,
        redirect_uri: str,
    ) -> str:
        """
        Generate a CSRF-protected state token for OAuth flow.

        Args:
            user_id: The user initiating the OAuth flow
            provider: The OAuth provider name
            redirect_uri: The callback redirect URI

        Returns:
            A secure random state token
        """
        self._cleanup_expired_states()

        state = secrets.token_urlsafe(32)
        self._oauth_states[state] = {
            "user_id": user_id,
            "provider": provider,
            "redirect_uri": redirect_uri,
            "created_at": datetime.utcnow(),
        }

        logger.info(f"Generated OAuth state for user {user_id[:8]}... provider {provider}")
        return state

    def validate_state(self, state: str) -> Optional[Dict[str, Any]]:
        """
        Validate and consume an OAuth state token.

        Args:
            state: The state token from the callback

        Returns:
            The state data if valid, None otherwise
        """
        self._cleanup_expired_states()

        state_data = self._oauth_states.pop(state, None)
        if not state_data:
            logger.warning(f"Invalid or expired OAuth state token")
            return None

        return state_data

    def get_authorization_url(
        self,
        provider: str,
        user_id: str,
        redirect_uri: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ) -> str:
        """
        Get the OAuth authorization URL for a provider.

        Args:
            provider: The OAuth provider name (e.g., 'google_workspace')
            user_id: The user ID initiating the flow
            redirect_uri: Optional custom redirect URI
            scopes: Optional custom scopes

        Returns:
            The full authorization URL
        """
        oauth_provider = get_oauth_provider(provider)

        # Use default redirect URI if not provided
        if redirect_uri is None:
            if provider == "google_workspace":
                redirect_uri = settings.google_oauth_redirect_uri
            else:
                raise ValueError(f"No default redirect URI for provider {provider}")

        # Generate state token
        state = self.generate_state(user_id, provider, redirect_uri)

        return oauth_provider.get_authorization_url(
            redirect_uri=redirect_uri,
            state=state,
            scopes=scopes,
        )

    async def handle_callback(
        self,
        provider: str,
        code: str,
        state: str,
        db: AsyncSession,
    ) -> OAuthConnection:
        """
        Handle OAuth callback and store tokens.

        Args:
            provider: The OAuth provider name
            code: The authorization code
            state: The state token for validation
            db: Database session

        Returns:
            The created/updated OAuthConnection
        """
        # Validate state
        state_data = self.validate_state(state)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state")

        if state_data["provider"] != provider:
            raise ValueError("Provider mismatch in OAuth callback")

        user_id = state_data["user_id"]
        redirect_uri = state_data["redirect_uri"]

        # Exchange code for tokens
        oauth_provider = get_oauth_provider(provider)
        tokens = await oauth_provider.exchange_code_for_tokens(code, redirect_uri)

        # Store tokens
        connection = await self.store_tokens(db, user_id, provider, tokens)

        logger.info(f"OAuth callback completed for user {user_id[:8]}... provider {provider}")
        return connection

    async def store_tokens(
        self,
        db: AsyncSession,
        user_id: str,
        provider: str,
        tokens: OAuthTokens,
    ) -> OAuthConnection:
        """
        Store or update OAuth tokens in the database.

        Args:
            db: Database session
            user_id: The user ID
            provider: The OAuth provider name
            tokens: The OAuth tokens to store

        Returns:
            The created/updated OAuthConnection
        """
        try:
            # Check for existing connection
            stmt = select(OAuthConnection).where(
                OAuthConnection.user_id == user_id,
                OAuthConnection.provider == provider
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            # Encrypt tokens
            encrypted_access = self._encrypt(tokens.access_token)
            encrypted_refresh = self._encrypt(tokens.refresh_token) if tokens.refresh_token else None

            if existing:
                # Update existing connection
                existing.access_token = encrypted_access
                if encrypted_refresh:
                    existing.refresh_token = encrypted_refresh
                existing.token_type = tokens.token_type
                existing.expires_at = tokens.expires_at
                existing.scopes = json.dumps(tokens.scopes) if tokens.scopes else None
                if tokens.provider_user_id:
                    existing.provider_user_id = tokens.provider_user_id
                if tokens.provider_email:
                    existing.provider_email = tokens.provider_email
                if tokens.metadata:
                    existing.metadata = json.dumps(tokens.metadata)
                existing.updated_at = datetime.utcnow()

                await db.commit()
                await db.refresh(existing)
                logger.info(f"Updated OAuth connection for user {user_id[:8]}... provider {provider}")
                return existing
            else:
                # Create new connection
                connection = OAuthConnection(
                    user_id=user_id,
                    provider=provider,
                    provider_user_id=tokens.provider_user_id,
                    provider_email=tokens.provider_email,
                    access_token=encrypted_access,
                    refresh_token=encrypted_refresh,
                    token_type=tokens.token_type,
                    expires_at=tokens.expires_at,
                    scopes=json.dumps(tokens.scopes) if tokens.scopes else None,
                    metadata=json.dumps(tokens.metadata) if tokens.metadata else None,
                )
                db.add(connection)
                await db.commit()
                await db.refresh(connection)
                logger.info(f"Created OAuth connection for user {user_id[:8]}... provider {provider}")
                return connection

        except SQLAlchemyError as e:
            logger.error(f"Database error storing OAuth tokens: {str(e)}")
            await db.rollback()
            raise

    async def get_connection(
        self,
        db: AsyncSession,
        user_id: str,
        provider: str,
    ) -> Optional[OAuthConnection]:
        """
        Get an OAuth connection for a user and provider.

        Args:
            db: Database session
            user_id: The user ID
            provider: The OAuth provider name

        Returns:
            The OAuthConnection if exists, None otherwise
        """
        try:
            stmt = select(OAuthConnection).where(
                OAuthConnection.user_id == user_id,
                OAuthConnection.provider == provider
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Database error getting OAuth connection: {str(e)}")
            raise

    async def get_decrypted_tokens(
        self,
        db: AsyncSession,
        user_id: str,
        provider: str,
        auto_refresh: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Get decrypted OAuth tokens for a user and provider.

        Args:
            db: Database session
            user_id: The user ID
            provider: The OAuth provider name
            auto_refresh: Whether to automatically refresh expired tokens

        Returns:
            Dictionary with decrypted tokens, or None if not found
        """
        connection = await self.get_connection(db, user_id, provider)
        if not connection:
            return None

        # Check if refresh is needed
        if auto_refresh and connection.needs_refresh and connection.refresh_token:
            try:
                connection = await self.refresh_tokens(db, user_id, provider)
            except Exception as e:
                logger.error(f"Failed to refresh tokens: {e}")
                # Return existing tokens even if refresh failed
                pass

        return {
            "access_token": self._decrypt(connection.access_token),
            "refresh_token": self._decrypt(connection.refresh_token) if connection.refresh_token else None,
            "token_type": connection.token_type,
            "expires_at": connection.expires_at,
            "scopes": json.loads(connection.scopes) if connection.scopes else None,
            "provider_email": connection.provider_email,
        }

    async def refresh_tokens(
        self,
        db: AsyncSession,
        user_id: str,
        provider: str,
    ) -> OAuthConnection:
        """
        Refresh OAuth tokens for a connection.

        Args:
            db: Database session
            user_id: The user ID
            provider: The OAuth provider name

        Returns:
            The updated OAuthConnection
        """
        connection = await self.get_connection(db, user_id, provider)
        if not connection:
            raise ValueError(f"No OAuth connection found for user {user_id} provider {provider}")

        if not connection.refresh_token:
            raise ValueError("No refresh token available")

        # Decrypt refresh token
        refresh_token = self._decrypt(connection.refresh_token)

        # Get new tokens from provider
        oauth_provider = get_oauth_provider(provider)
        new_tokens = await oauth_provider.refresh_access_token(refresh_token)

        # Store new tokens
        return await self.store_tokens(db, user_id, provider, new_tokens)

    async def revoke_connection(
        self,
        db: AsyncSession,
        user_id: str,
        provider: str,
    ) -> bool:
        """
        Revoke and delete an OAuth connection.

        Args:
            db: Database session
            user_id: The user ID
            provider: The OAuth provider name

        Returns:
            True if connection was revoked and deleted
        """
        connection = await self.get_connection(db, user_id, provider)
        if not connection:
            return False

        try:
            # Try to revoke token at provider
            oauth_provider = get_oauth_provider(provider)
            access_token = self._decrypt(connection.access_token)
            await oauth_provider.revoke_token(access_token)
        except Exception as e:
            logger.warning(f"Failed to revoke token at provider: {e}")
            # Continue with deletion even if revocation fails

        try:
            # Delete connection from database
            await db.delete(connection)
            await db.commit()
            logger.info(f"Revoked OAuth connection for user {user_id[:8]}... provider {provider}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Database error revoking OAuth connection: {str(e)}")
            await db.rollback()
            raise

    async def list_connections(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> List[OAuthConnection]:
        """
        List all OAuth connections for a user.

        Args:
            db: Database session
            user_id: The user ID

        Returns:
            List of OAuthConnection objects
        """
        try:
            stmt = select(OAuthConnection).where(
                OAuthConnection.user_id == user_id
            )
            result = await db.execute(stmt)
            return result.scalars().all()
        except SQLAlchemyError as e:
            logger.error(f"Database error listing OAuth connections: {str(e)}")
            raise

    async def is_connected(
        self,
        db: AsyncSession,
        user_id: str,
        provider: str,
    ) -> bool:
        """
        Check if a user has an active OAuth connection.

        Args:
            db: Database session
            user_id: The user ID
            provider: The OAuth provider name

        Returns:
            True if connected
        """
        connection = await self.get_connection(db, user_id, provider)
        return connection is not None


# Global OAuth service instance
oauth_service = OAuthService()
