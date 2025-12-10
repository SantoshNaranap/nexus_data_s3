"""Authentication service for Google OAuth and JWT management."""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from authlib.integrations.starlette_client import OAuth
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import User

logger = logging.getLogger(__name__)

# Initialize OAuth
oauth = OAuth()

# Configure Google OAuth
oauth.register(
    name="google",
    client_id=settings.google_oauth_client_id,
    client_secret=settings.google_oauth_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile",
    },
)


class AuthService:
    """Service for handling authentication operations."""

    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """
        Create JWT access token.

        Args:
            data: Data to encode in the token (must include user_id)
            expires_delta: Optional custom expiration time

        Returns:
            Encoded JWT token
        """
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=settings.jwt_access_token_expire_minutes
            )

        to_encode.update({"exp": expire, "iat": datetime.utcnow()})

        encoded_jwt = jwt.encode(
            to_encode,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        return encoded_jwt

    @staticmethod
    def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
        """
        Decode and validate JWT access token.

        Args:
            token: JWT token to decode

        Returns:
            Decoded token payload or None if invalid
        """
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            return payload
        except JWTError as e:
            logger.error(f"JWT decode error: {e}")
            return None

    @staticmethod
    async def get_or_create_user(
        db: AsyncSession,
        email: str,
        google_id: str,
        name: Optional[str] = None,
        profile_picture: Optional[str] = None,
    ) -> User:
        """
        Get existing user or create new user from Google profile.

        Args:
            db: Database session
            email: User's email
            google_id: Google user ID
            name: User's name
            profile_picture: URL to profile picture

        Returns:
            User object
        """
        # Try to find user by google_id first
        result = await db.execute(
            select(User).where(User.google_id == google_id)
        )
        user = result.scalar_one_or_none()

        if user:
            # Update user information if changed
            updated = False
            if user.email != email:
                user.email = email
                updated = True
            if name and user.name != name:
                user.name = name
                updated = True
            if profile_picture and user.profile_picture != profile_picture:
                user.profile_picture = profile_picture
                updated = True

            if updated:
                user.updated_at = datetime.utcnow()
                await db.commit()
                await db.refresh(user)

            logger.info(f"Existing user logged in: {email}")
            return user

        # Create new user
        user = User(
            email=email,
            google_id=google_id,
            name=name,
            profile_picture=profile_picture,
        )

        db.add(user)
        await db.commit()
        await db.refresh(user)

        logger.info(f"New user created: {email}")
        return user

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
        """
        Get user by ID.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            User object or None if not found
        """
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """
        Get user by email.

        Args:
            db: Database session
            email: User's email

        Returns:
            User object or None if not found
        """
        result = await db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_google_id(db: AsyncSession, google_id: str) -> Optional[User]:
        """
        Get user by Google ID.

        Args:
            db: Database session
            google_id: Google user ID

        Returns:
            User object or None if not found
        """
        result = await db.execute(
            select(User).where(User.google_id == google_id)
        )
        return result.scalar_one_or_none()


# Export singleton instance
auth_service = AuthService()
