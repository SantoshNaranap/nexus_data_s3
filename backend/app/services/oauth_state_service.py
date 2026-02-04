"""
OAuth state management service for production deployments.

Stores OAuth states in database instead of in-memory for multi-instance support.
Includes automatic cleanup of expired states.
"""

import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import get_logger

logger = get_logger(__name__)

# OAuth state TTL - 10 minutes is standard for OAuth flows
OAUTH_STATE_TTL_MINUTES = 10


class OAuthStateService:
    """
    Service for managing OAuth states in a distributed environment.

    Replaces in-memory dict storage with database-backed storage
    for multi-instance deployments behind load balancers.
    """

    def generate_state(self) -> str:
        """
        Generate a cryptographically secure OAuth state token.

        Returns:
            A URL-safe random string (43 characters)
        """
        return secrets.token_urlsafe(32)

    async def store_state(
        self,
        db: AsyncSession,
        state: str,
        context: Optional[Dict[str, Any]] = None,
        ttl_minutes: int = OAUTH_STATE_TTL_MINUTES,
    ) -> bool:
        """
        Store an OAuth state in the database.

        Args:
            db: Database session
            state: The OAuth state token
            context: Optional context data (user_id, tenant_id, datasource, etc.)
            ttl_minutes: Time-to-live in minutes (default 10)

        Returns:
            True if stored successfully
        """
        try:
            from app.models.database import OAuthState

            expires_at = datetime.now() + timedelta(minutes=ttl_minutes)

            oauth_state = OAuthState(
                state=state,
                context=context,
                expires_at=expires_at,
            )

            db.add(oauth_state)
            await db.commit()

            logger.info(f"Stored OAuth state (expires in {ttl_minutes}m)")
            return True

        except SQLAlchemyError as e:
            logger.error(f"Failed to store OAuth state: {e}")
            await db.rollback()
            return False

    async def validate_and_consume_state(
        self,
        db: AsyncSession,
        state: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Validate an OAuth state and consume it (one-time use).

        Args:
            db: Database session
            state: The OAuth state token to validate

        Returns:
            The context dict if valid, None if invalid/expired/already used
        """
        try:
            from app.models.database import OAuthState

            # Find the state
            result = await db.execute(
                select(OAuthState).where(OAuthState.state == state)
            )
            oauth_state = result.scalar_one_or_none()

            if not oauth_state:
                logger.warning("OAuth state not found - possible CSRF attack or expired")
                return None

            # Check if expired
            if oauth_state.is_expired:
                logger.warning("OAuth state expired")
                # Clean up expired state
                await db.delete(oauth_state)
                await db.commit()
                return None

            # Consume the state (delete it - one-time use)
            context = oauth_state.context
            await db.delete(oauth_state)
            await db.commit()

            logger.info("OAuth state validated and consumed")
            return context if context else {}

        except SQLAlchemyError as e:
            logger.error(f"Error validating OAuth state: {e}")
            return None

    async def cleanup_expired_states(self, db: AsyncSession) -> int:
        """
        Clean up expired OAuth states.

        Should be called periodically (e.g., every hour).

        Args:
            db: Database session

        Returns:
            Number of expired states deleted
        """
        try:
            from app.models.database import OAuthState

            result = await db.execute(
                delete(OAuthState).where(OAuthState.expires_at < datetime.now())
            )
            await db.commit()

            count = result.rowcount
            if count > 0:
                logger.info(f"Cleaned up {count} expired OAuth states")
            return count

        except SQLAlchemyError as e:
            logger.error(f"Error cleaning up OAuth states: {e}")
            await db.rollback()
            return 0

    async def create_and_store_state(
        self,
        db: AsyncSession,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Convenience method to generate and store a state in one call.

        Args:
            db: Database session
            context: Optional context data

        Returns:
            The generated state token
        """
        state = self.generate_state()
        await self.store_state(db, state, context)
        return state


# Global service instance
oauth_state_service = OAuthStateService()
