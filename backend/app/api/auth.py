"""Authentication endpoints for email/password auth, Google OAuth, and JWT."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.logging import get_logger, security_logger
from app.middleware.auth import get_current_user, get_current_user_optional
from app.models.database import User
from app.services.auth_service import auth_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# In-memory store for OAuth state (in production, use Redis or database)
oauth_states: dict = {}


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
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user with email and password.

    Returns JWT token in HTTPOnly cookie on success.
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

    # Update login timestamps for "What You Missed" feature
    await auth_service.update_last_login(db, user)

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
                "role": current_user.role,
                "tenant_id": current_user.tenant_id,
            },
        }
    else:
        return {"authenticated": False}


# ============ Google OAuth Endpoints ============


@router.get("/google")
async def google_login():
    """
    Redirect to Google OAuth consent screen.

    Initiates the OAuth flow by redirecting the user to Google's authorization page.
    """
    if not settings.google_oauth_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth is not configured",
        )

    # Generate state for CSRF protection
    state = auth_service.generate_oauth_state()
    oauth_states[state] = True  # Store state for validation

    # Get authorization URL
    auth_url = auth_service.get_google_auth_url(state)

    logger.info("Redirecting user to Google OAuth")
    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Google OAuth callback.

    Exchanges the authorization code for tokens, gets user info,
    creates/updates user, and redirects to frontend with auth cookie.
    """
    # Handle OAuth errors
    if error:
        logger.error(f"Google OAuth error: {error}")
        return RedirectResponse(
            url=f"{settings.frontend_url}/login?error=oauth_error&message={error}"
        )

    # Validate required parameters
    if not code or not state:
        logger.error("Missing code or state in Google OAuth callback")
        return RedirectResponse(
            url=f"{settings.frontend_url}/login?error=missing_params"
        )

    # Validate state (CSRF protection)
    if state not in oauth_states:
        logger.error("Invalid OAuth state - possible CSRF attack")
        return RedirectResponse(
            url=f"{settings.frontend_url}/login?error=invalid_state"
        )

    # Remove used state
    del oauth_states[state]

    try:
        # Exchange code for tokens
        token_response = await auth_service.exchange_google_code(code)
        access_token = token_response.get("access_token")

        if not access_token:
            raise ValueError("No access token in response")

        # Get user info from Google
        user_info = await auth_service.get_google_user_info(access_token)

        google_id = user_info.get("id")
        email = user_info.get("email")
        name = user_info.get("name")
        picture = user_info.get("picture")

        if not google_id or not email:
            raise ValueError("Missing required user info from Google")

        # Handle OAuth login/signup with tenant assignment
        user = await auth_service.handle_google_oauth(
            db=db,
            google_id=google_id,
            email=email,
            name=name,
            profile_picture=picture,
        )

        # Update login timestamps
        await auth_service.update_last_login(db, user)

        # Create JWT access token
        jwt_token = auth_service.create_access_token(
            data={"user_id": user.id, "email": user.email}
        )

        security_logger.log_auth_success(user.email, "google_oauth")
        logger.info(f"Google OAuth successful for: {email}")

        # Create redirect response with cookie
        response = RedirectResponse(url=settings.frontend_url)

        # Set JWT in HTTPOnly cookie
        cookie_settings = settings.cookie_settings
        response.set_cookie(
            key="access_token",
            value=jwt_token,
            httponly=cookie_settings["httponly"],
            secure=cookie_settings["secure"],
            samesite=cookie_settings["samesite"],
            max_age=settings.jwt_access_token_expire_minutes * 60,
        )

        return response

    except Exception as e:
        logger.error(f"Google OAuth callback error: {e}")
        return RedirectResponse(
            url=f"{settings.frontend_url}/login?error=oauth_failed&message={str(e)}"
        )


@router.get("/google/available")
async def google_oauth_available():
    """Check if Google OAuth is configured and available."""
    return {
        "available": bool(
            settings.google_oauth_client_id and settings.google_oauth_client_secret
        )
    }
