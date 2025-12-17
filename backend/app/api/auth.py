"""Authentication endpoints for email/password auth and JWT."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.logging import get_logger, security_logger
from app.middleware.auth import get_current_user, get_current_user_optional
from app.models.database import User
from app.services.auth_service import (
    auth_service,
    AccountLockedError,
    InvalidCredentialsError,
)

logger = get_logger(__name__)


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request, handling proxies."""
    # Check for forwarded header (behind proxy/load balancer)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    # Check for real IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    # Fall back to direct client
    return request.client.host if request.client else "unknown"

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
    signup_request: SignupRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user with email and password.

    Returns JWT token in HTTPOnly cookie on success.
    """
    # Validate password complexity
    is_valid, errors = auth_service.validate_password(signup_request.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Password does not meet requirements", "errors": errors},
        )

    # Check if email already exists
    if await auth_service.email_exists(db, signup_request.email):
        logger.warning(f"Signup attempt with existing email: {signup_request.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create the user
    try:
        user = await auth_service.create_user(
            db=db,
            email=signup_request.email,
            password=signup_request.password,
            name=signup_request.name,
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
        path="/",  # Explicit path for consistent cookie handling
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
    login_request: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user with email and password.

    Returns JWT token in HTTPOnly cookie on success.
    Includes account lockout protection after failed attempts.
    """
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")[:500]  # Truncate to avoid storage issues

    try:
        # Authenticate user (includes lockout checking)
        user = await auth_service.authenticate_user(
            db=db,
            email=login_request.email,
            password=login_request.password,
            ip_address=client_ip,
            user_agent=user_agent,
        )
    except AccountLockedError as e:
        security_logger.log_auth_failure(
            "account_locked",
            {"email": login_request.email, "locked_until": str(e.locked_until)},
        )
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={
                "message": "Account temporarily locked due to too many failed attempts",
                "locked_until": e.locked_until.isoformat(),
                "retry_after_seconds": int((e.locked_until - __import__('datetime').datetime.utcnow()).total_seconds()),
            },
        )
    except InvalidCredentialsError:
        security_logger.log_auth_failure("invalid_credentials", {"email": login_request.email})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
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
        path="/",  # Explicit path for consistent cookie handling
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
    }


@router.post("/logout")
async def logout(response: Response):
    """
    Logout user by clearing authentication cookie.
    """
    response = JSONResponse(content={"message": "Logged out successfully"})
    # Must use same cookie settings as set_cookie for proper deletion
    cookie_settings = settings.cookie_settings
    response.delete_cookie(
        key="access_token",
        path="/",  # Ensure cookie is deleted for all paths
        httponly=cookie_settings["httponly"],
        secure=cookie_settings["secure"],
        samesite=cookie_settings["samesite"],
    )
    logger.info("User logged out, access_token cookie cleared")
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
