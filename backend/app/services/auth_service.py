"""Authentication service for email/password auth, Google OAuth, and JWT management."""

import logging
import secrets
import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from urllib.parse import urlencode

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import User, Tenant
from app.services.tenant_service import tenant_service

logger = logging.getLogger(__name__)

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

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
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=settings.jwt_access_token_expire_minutes
            )

        to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})

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

    # ============ Google OAuth Methods ============

    @staticmethod
    def generate_oauth_state() -> str:
        """Generate a secure random state for OAuth CSRF protection."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def get_google_auth_url(state: str, redirect_uri: Optional[str] = None) -> str:
        """
        Generate Google OAuth authorization URL.

        Args:
            state: CSRF protection state token
            redirect_uri: Optional override for redirect URI

        Returns:
            Full Google OAuth authorization URL
        """
        redirect = redirect_uri or settings.google_oauth_redirect_uri
        if not redirect:
            # Default to api_base_url + callback path
            redirect = f"{settings.api_base_url}/api/auth/google/callback"

        params = {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "select_account",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    @staticmethod
    async def exchange_google_code(code: str, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
        """
        Exchange authorization code for Google tokens.

        Args:
            code: Authorization code from Google
            redirect_uri: Optional override for redirect URI

        Returns:
            Token response containing access_token, id_token, etc.
        """
        redirect = redirect_uri or settings.google_oauth_redirect_uri
        if not redirect:
            redirect = f"{settings.api_base_url}/api/auth/google/callback"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_oauth_client_id,
                    "client_secret": settings.google_oauth_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect,
                },
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def get_google_user_info(access_token: str) -> Dict[str, Any]:
        """
        Get user info from Google using access token.

        Args:
            access_token: Google OAuth access token

        Returns:
            User info dict with id, email, name, picture
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def get_user_by_google_id(db: AsyncSession, google_id: str) -> Optional[User]:
        """Get user by Google ID."""
        result = await db.execute(
            select(User).where(User.google_id == google_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_google_user(
        db: AsyncSession,
        google_id: str,
        email: str,
        name: Optional[str] = None,
        profile_picture: Optional[str] = None,
    ) -> User:
        """
        Create a new user from Google OAuth.

        Args:
            db: Database session
            google_id: Google user ID
            email: User's email from Google
            name: User's name from Google
            profile_picture: User's profile picture URL

        Returns:
            Created User object
        """
        user = User(
            email=email,
            google_id=google_id,
            name=name,
            profile_picture=profile_picture,
            auth_provider="google",
            password_hash=None,  # No password for OAuth users
        )

        db.add(user)
        await db.commit()
        await db.refresh(user)

        logger.info(f"New Google OAuth user created: {email}")
        return user

    @staticmethod
    async def handle_google_oauth(
        db: AsyncSession,
        google_id: str,
        email: str,
        name: Optional[str] = None,
        profile_picture: Optional[str] = None,
    ) -> User:
        """
        Handle Google OAuth login/signup with tenant assignment.

        - If user exists (by google_id or email), return them
        - If user doesn't exist, create them
        - Assign user to tenant based on email domain
        - First user in tenant becomes admin

        Args:
            db: Database session
            google_id: Google user ID
            email: User's email from Google
            name: User's name from Google
            profile_picture: User's profile picture URL

        Returns:
            User object (existing or newly created)
        """
        # Check if user exists by Google ID
        user = await AuthService.get_user_by_google_id(db, google_id)
        if user:
            # Update profile info if changed
            if name and user.name != name:
                user.name = name
            if profile_picture and user.profile_picture != profile_picture:
                user.profile_picture = profile_picture
            await db.commit()
            await db.refresh(user)
            logger.info(f"Existing Google user logged in: {email}")
            return user

        # Check if user exists by email (might have signed up with email/password)
        user = await AuthService.get_user_by_email(db, email)
        if user:
            # Link Google account to existing user
            user.google_id = google_id
            user.auth_provider = "google"
            if profile_picture and not user.profile_picture:
                user.profile_picture = profile_picture
            await db.commit()
            await db.refresh(user)
            logger.info(f"Linked Google account to existing user: {email}")
            return user

        # Create new user
        user = await AuthService.create_google_user(
            db=db,
            google_id=google_id,
            email=email,
            name=name,
            profile_picture=profile_picture,
        )

        # Get or create tenant for user's domain
        domain = tenant_service.extract_domain_from_email(email)
        tenant = await tenant_service.get_or_create_tenant(db, domain)

        # Assign user to tenant (first user becomes admin)
        await tenant_service.assign_user_to_tenant(db, user, tenant)

        return user


# Export singleton instance
auth_service = AuthService()
