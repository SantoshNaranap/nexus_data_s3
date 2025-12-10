"""Authentication middleware and dependencies."""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status, Cookie, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.database import User
from app.services.auth_service import auth_service

logger = logging.getLogger(__name__)

# HTTP Bearer token scheme (for Authorization header)
security = HTTPBearer(auto_error=False)


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(None),
) -> User:
    """
    Get current authenticated user from JWT token.

    Checks for JWT token in:
    1. Cookie (access_token)
    2. Authorization header (Bearer token)

    Args:
        db: Database session
        credentials: HTTP Authorization credentials
        access_token: JWT token from cookie

    Returns:
        User object

    Raises:
        HTTPException: If token is invalid or user not found
    """
    # Extract token from cookie or Authorization header
    token = None

    if access_token:
        token = access_token
        logger.debug("Token found in cookie")
    elif credentials:
        token = credentials.credentials
        logger.debug("Token found in Authorization header")

    if not token:
        logger.warning("No authentication token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode and validate token
    payload = auth_service.decode_access_token(token)
    if not payload:
        logger.warning("Invalid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract user_id from token
    user_id: str = payload.get("user_id")
    if not user_id:
        logger.warning("Token missing user_id")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    user = await auth_service.get_user_by_id(db, user_id)
    if not user:
        logger.warning(f"User not found: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.debug(f"User authenticated: {user.email}")
    return user


async def get_current_user_optional(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(None),
) -> Optional[User]:
    """
    Get current user if authenticated, otherwise return None.

    This is useful for endpoints that are optionally authenticated.

    Args:
        db: Database session
        credentials: HTTP Authorization credentials
        access_token: JWT token from cookie

    Returns:
        User object or None
    """
    try:
        return await get_current_user(db, credentials, access_token)
    except HTTPException:
        return None
