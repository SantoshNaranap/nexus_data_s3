"""Authentication service for email/password auth and JWT management."""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import User

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Service for handling authentication operations."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)

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
    async def create_user(
        db: AsyncSession,
        email: str,
        password: str,
        name: Optional[str] = None,
    ) -> User:
        """
        Create a new user with email and password.

        Args:
            db: Database session
            email: User's email
            password: Plain text password (will be hashed)
            name: User's name (optional)

        Returns:
            User object
        """
        # Hash the password
        password_hash = AuthService.hash_password(password)

        # Create new user
        user = User(
            email=email,
            password_hash=password_hash,
            name=name,
        )

        db.add(user)
        await db.commit()
        await db.refresh(user)

        logger.info(f"New user created: {email}")
        return user

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        email: str,
        password: str,
    ) -> Optional[User]:
        """
        Authenticate a user with email and password.

        Args:
            db: Database session
            email: User's email
            password: Plain text password

        Returns:
            User object if authenticated, None otherwise
        """
        user = await AuthService.get_user_by_email(db, email)
        if not user:
            return None

        if not AuthService.verify_password(password, user.password_hash):
            return None

        logger.info(f"User authenticated: {email}")
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
    async def email_exists(db: AsyncSession, email: str) -> bool:
        """
        Check if an email is already registered.

        Args:
            db: Database session
            email: Email to check

        Returns:
            True if email exists, False otherwise
        """
        user = await AuthService.get_user_by_email(db, email)
        return user is not None

    @staticmethod
    async def update_last_login(db: AsyncSession, user: User) -> None:
        """
        Update user's login timestamps for "What You Missed" feature.

        Moves current last_login to previous_login, then sets new last_login.
        This allows querying for "since last login" by using previous_login.

        Args:
            db: Database session
            user: User object to update
        """
        # Preserve the current last_login as previous_login
        user.previous_login = user.last_login
        # Set new last_login to now
        user.last_login = datetime.utcnow()

        await db.commit()
        await db.refresh(user)

        logger.info(f"Updated login timestamps for user: {user.email}")


# Export singleton instance
auth_service = AuthService()
