"""Authentication endpoints for email/password auth and JWT."""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_db_context
from app.core.config import settings
from app.core.logging import get_logger, security_logger
from app.middleware.auth import get_current_user, get_current_user_optional
from app.models.database import User
from app.services.auth_service import auth_service

logger = get_logger(__name__)

# Cache for pre-loaded digests (user_id -> digest_data)
DIGEST_CACHE: dict = {}


async def preload_digest_background(user_id: str, previous_login):
    """Background task to pre-load the 'What You Missed' digest after login."""
    try:
        logger.info(f"Starting background digest pre-load for user {user_id}")

        # Import here to avoid circular imports
        from app.services.digest_service import digest_service

        # Use a new database session for background task
        async with get_db_context() as db:
            result = await digest_service.generate_digest(
                db=db,
                user_id=user_id,
                since=previous_login,
            )

            # Cache the result
            DIGEST_CACHE[user_id] = {
                "data": result,
                "timestamp": asyncio.get_event_loop().time(),
            }

            logger.info(f"Digest pre-loaded for user {user_id} in {result.get('total_time_ms', 0):.0f}ms")

    except Exception as e:
        logger.error(f"Error pre-loading digest for user {user_id}: {e}")


def get_cached_digest(user_id: str):
    """Get cached digest if available and not stale (max 5 minutes)."""
    cached = DIGEST_CACHE.get(user_id)
    if cached:
        age = asyncio.get_event_loop().time() - cached["timestamp"]
        if age < 300:  # 5 minute cache
            return cached["data"]
        else:
            # Remove stale cache
            del DIGEST_CACHE[user_id]
    return None


router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ============ Request/Response Models ============


class SignupRequest(BaseModel):
    """Request model for user signup."""
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    name: Optional[str] = Field(None, max_length=255)


class LoginRequest(BaseModel):
    """Request model for user login."""
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    """Response model for authentication."""
    message: str
    user: dict


# ============ Endpoints ============


@router.post("/signup", response_model=AuthResponse)
async def signup(
    request: SignupRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user with email and password.

    Returns JWT token in HTTPOnly cookie on success.
    """
    # Check if email already exists
    if await auth_service.email_exists(db, request.email):
        logger.warning(f"Signup attempt with existing email: {request.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create the user
    try:
        user = await auth_service.create_user(
            db=db,
            email=request.email,
            password=request.password,
            name=request.name,
        )
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        )

    # Create JWT access token
    access_token = auth_service.create_access_token(
        data={"user_id": user.id, "email": user.email}
    )

    # Set token in HTTPOnly cookie
    cookie_settings = settings.cookie_settings
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=cookie_settings["httponly"],
        secure=cookie_settings["secure"],
        samesite=cookie_settings["samesite"],
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )

    security_logger.log_auth_success(user.email, "signup")
    logger.info(f"User signed up successfully: {user.email}")

    return AuthResponse(
        message="User created successfully",
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
        },
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user with email and password.

    Returns JWT token in HTTPOnly cookie on success.
    Starts background pre-loading of "What You Missed" digest.
    """
    # Authenticate user
    user = await auth_service.authenticate_user(
        db=db,
        email=request.email,
        password=request.password,
    )

    if not user:
        security_logger.log_auth_failure("invalid_credentials", {"email": request.email})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Capture previous_login BEFORE updating (for digest)
    previous_login = user.previous_login

    # Update login timestamps for "What You Missed" feature
    await auth_service.update_last_login(db, user)

    # Start background pre-loading of digest (non-blocking)
    asyncio.create_task(preload_digest_background(user.id, previous_login))
    logger.info(f"Triggered background digest pre-load for user {user.email}")

    # Create JWT access token
    access_token = auth_service.create_access_token(
        data={"user_id": user.id, "email": user.email}
    )

    # Set token in HTTPOnly cookie
    cookie_settings = settings.cookie_settings
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=cookie_settings["httponly"],
        secure=cookie_settings["secure"],
        samesite=cookie_settings["samesite"],
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )

    security_logger.log_auth_success(user.email, "login")
    logger.info(f"User logged in successfully: {user.email}")

    return AuthResponse(
        message="Login successful",
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "profile_picture": user.profile_picture,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "previous_login": user.previous_login.isoformat() if user.previous_login else None,
        },
    )


@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """
    Get current authenticated user information.

    Protected endpoint that requires valid JWT token.
    """
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "profile_picture": current_user.profile_picture,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
        "previous_login": current_user.previous_login.isoformat() if current_user.previous_login else None,
    }


@router.post("/logout")
async def logout(response: Response):
    """
    Logout user by clearing authentication cookie.
    """
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie(key="access_token")
    logger.info("User logged out")
    return response


@router.get("/status")
async def auth_status(
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Check authentication status.

    Returns authenticated user info if logged in, otherwise returns not authenticated.
    """
    if current_user:
        return {
            "authenticated": True,
            "user": {
                "id": current_user.id,
                "email": current_user.email,
                "name": current_user.name,
                "profile_picture": current_user.profile_picture,
            },
        }
    else:
        return {"authenticated": False}
