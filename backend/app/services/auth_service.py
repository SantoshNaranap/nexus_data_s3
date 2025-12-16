"""Authentication service for email/password auth and JWT management."""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import User
from app.services.security_service import security_service, PasswordValidationError

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthenticationError(Exception):
    """Base class for authentication errors."""
    pass


class AccountLockedError(AuthenticationError):
    """Raised when account is locked due to failed attempts."""

    def __init__(self, locked_until: datetime):
        self.locked_until = locked_until
        super().__init__(f"Account locked until {locked_until}")


class InvalidCredentialsError(AuthenticationError):
    """Raised when credentials are invalid."""
    pass


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
    def validate_password(password: str) -> Tuple[bool, List[str]]:
        """
        Validate password meets complexity requirements.

        Args:
            password: Password to validate

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        return security_service.validate_password(password)

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
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> User:
        """
        Authenticate a user with email and password.

        Includes account lockout checking and login attempt tracking.

        Args:
            db: Database session
            email: User's email
            password: Plain text password
            ip_address: Client IP address for logging
            user_agent: Client user agent for logging

        Returns:
            User object if authenticated

        Raises:
            AccountLockedError: If account is locked
            InvalidCredentialsError: If credentials are invalid
        """
        # Check if account is locked
        is_locked, locked_until = await security_service.check_account_locked(db, email)
        if is_locked and locked_until:
            await security_service.record_login_attempt(
                db, email, False, ip_address, user_agent, "account_locked"
            )
            raise AccountLockedError(locked_until)

        # Get user
        user = await AuthService.get_user_by_email(db, email)
        if not user:
            await security_service.record_login_attempt(
                db, email, False, ip_address, user_agent, "user_not_found"
            )
            raise InvalidCredentialsError("Invalid email or password")

        # Verify password
        if not AuthService.verify_password(password, user.password_hash):
            await security_service.record_login_attempt(
                db, email, False, ip_address, user_agent, "invalid_password"
            )
            # Increment failed attempts (may lock account)
            await security_service.increment_failed_attempts(db, user)
            raise InvalidCredentialsError("Invalid email or password")

        # Success - reset failed attempts and record success
        await security_service.reset_failed_attempts(db, user)
        await security_service.record_login_attempt(
            db, email, True, ip_address, user_agent
        )

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


# Export singleton instance
auth_service = AuthService()
