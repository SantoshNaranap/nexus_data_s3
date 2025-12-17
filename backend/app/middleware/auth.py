"""Authentication middleware and dependencies.

NOTE: Authentication is DISABLED in this branch (krishnan-test).
All auth functions return None, allowing unauthenticated access.
"""

import logging
from typing import Optional

from fastapi import Depends, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.database import User

logger = logging.getLogger(__name__)

# HTTP Bearer token scheme (for Authorization header)
security = HTTPBearer(auto_error=False)


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(None),
) -> Optional[User]:
    """
    AUTH DISABLED: Always returns None.

    In the krishnan-test branch, authentication is bypassed.
    All endpoints work without requiring a logged-in user.
    """
    logger.debug("Auth disabled - returning None for user")
    return None


async def get_current_user_optional(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(None),
) -> Optional[User]:
    """
    AUTH DISABLED: Always returns None.

    In the krishnan-test branch, authentication is bypassed.
    """
    return None
