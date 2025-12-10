"""Authentication endpoints for Google OAuth and JWT."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth import get_current_user, get_current_user_optional
from app.models.database import User
from app.services.auth_service import auth_service, oauth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.get("/google")
async def google_login(request: Request):
    """
    Initiate Google OAuth flow.

    Redirects user to Google OAuth consent page.
    """
    # Build redirect URI
    redirect_uri = request.url_for("google_callback")

    logger.info(f"Initiating Google OAuth flow, redirect URI: {redirect_uri}")

    # Redirect to Google OAuth
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def google_callback(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Google OAuth callback.

    Exchanges authorization code for tokens, creates/updates user,
    and returns JWT token in HTTPOnly cookie.
    """
    try:
        # Exchange authorization code for access token
        token = await oauth.google.authorize_access_token(request)

        # Get user info from Google
        user_info = token.get("userinfo")
        if not user_info:
            logger.error("Failed to get user info from Google token")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user information from Google",
            )

        # Extract user information
        email = user_info.get("email")
        google_id = user_info.get("sub")  # Google user ID
        name = user_info.get("name")
        profile_picture = user_info.get("picture")

        if not email or not google_id:
            logger.error("Missing required user information from Google")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required user information",
            )

        logger.info(f"Google OAuth successful for user: {email}")

        # Get or create user in database
        user = await auth_service.get_or_create_user(
            db=db,
            email=email,
            google_id=google_id,
            name=name,
            profile_picture=profile_picture,
        )

        # Create JWT access token
        access_token = auth_service.create_access_token(
            data={"user_id": user.id, "email": user.email}
        )

        # For development, redirect to frontend with token in query param
        # In production, you might want to redirect to a success page
        frontend_url = "http://localhost:5173"  # Frontend URL from settings

        # Set token in HTTPOnly cookie
        response = RedirectResponse(url=f"{frontend_url}/auth/callback?success=true")
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,  # Set to True in production (HTTPS)
            samesite="lax",
            max_age=86400,  # 24 hours
        )

        logger.info(f"User authenticated successfully: {email}")
        return response

    except Exception as e:
        logger.error(f"Google OAuth callback error: {e}")
        # Redirect to frontend with error
        frontend_url = "http://localhost:5173"
        return RedirectResponse(url=f"{frontend_url}/auth/callback?error=auth_failed")


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
