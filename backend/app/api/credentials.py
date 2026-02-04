"""Credentials API endpoints with per-user OAuth support."""

import logging
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.credential_service import credential_service
from app.services.user_oauth_service import user_oauth_service
from app.services.oauth_state_service import oauth_state_service
from app.middleware.auth import get_current_user_optional, get_current_user
from app.core.database import get_db
from app.core.config import settings
from app.models.database import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


class CredentialsSaveRequest(BaseModel):
    """Request model for saving credentials."""
    datasource: str
    credentials: Dict[str, str]


class CredentialsResponse(BaseModel):
    """Response model for credentials operations."""
    success: bool
    message: str
    datasource: str


@router.post("", response_model=CredentialsResponse)
async def save_credentials(
    request: CredentialsSaveRequest,
    user: User = Depends(get_current_user),  # Require authentication
    db: AsyncSession = Depends(get_db),
):
    """
    Save credentials for a datasource.

    Requires authentication - credentials are stored encrypted in the database.
    """
    try:
        # Authenticated user - save to database
        await credential_service.save_credentials(
            datasource=request.datasource,
            credentials=request.credentials,
            db=db,
            user_id=user.id,
        )
        logger.info(f"Credentials saved for user {user.id[:8]}... datasource: {request.datasource}")

        return CredentialsResponse(
            success=True,
            message="Credentials saved successfully",
            datasource=request.datasource,
        )

    except Exception as e:
        logger.error(f"Error saving credentials: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save credentials: {str(e)}",
        )


@router.get("/{datasource}/status")
async def get_credentials_status(
    datasource: str,
    req: Request,
    user: Optional[User] = Depends(get_current_user_optional),  # Allow both auth and anon
    db: AsyncSession = Depends(get_db),
):
    """Check if credentials are configured for a datasource."""
    try:
        if user:
            # Check for authenticated user
            has_credentials = await credential_service.has_credentials(
                datasource=datasource,
                db=db,
                user_id=user.id,
            )
        else:
            # Check for anonymous user
            session_id = req.cookies.get("session_id")
            if not session_id:
                return {"configured": False}

            has_credentials = await credential_service.has_credentials(
                datasource=datasource,
                session_id=session_id,
            )

        return {"configured": has_credentials}

    except Exception as e:
        logger.error(f"Error checking credentials status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check credentials status: {str(e)}",
        )


@router.delete("/{datasource}")
async def delete_credentials(
    datasource: str,
    user: User = Depends(get_current_user),  # Require authentication
    db: AsyncSession = Depends(get_db),
):
    """Delete credentials for a datasource. Requires authentication."""
    try:
        await credential_service.delete_credentials(
            datasource=datasource,
            db=db,
            user_id=user.id,
        )
        logger.info(f"Credentials deleted for user {user.id[:8]}... datasource: {datasource}")

        return {
            "success": True,
            "message": "Credentials deleted successfully",
        }

    except Exception as e:
        logger.error(f"Error deleting credentials: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete credentials: {str(e)}",
        )


# ============ Per-User OAuth Endpoints ============


@router.get("/oauth/available")
async def get_oauth_availability():
    """Check which datasources have OAuth configured."""
    return {
        "slack": user_oauth_service.is_oauth_configured("slack"),
        "github": user_oauth_service.is_oauth_configured("github"),
        "jira": user_oauth_service.is_oauth_configured("jira"),
    }


@router.get("/{datasource}/oauth")
async def start_oauth(
    datasource: str,
    user: User = Depends(get_current_user),  # Require authentication for OAuth
    db: AsyncSession = Depends(get_db),
):
    """
    Start OAuth flow for a datasource.

    Redirects user to the OAuth provider (Slack/GitHub/Jira) to authorize access.
    After authorization, user is redirected back to the callback URL.
    """
    datasource_lower = datasource.lower()

    if datasource_lower not in ["slack", "github", "jira"]:
        raise HTTPException(
            status_code=400,
            detail=f"OAuth not supported for datasource: {datasource}",
        )

    if not user_oauth_service.is_oauth_configured(datasource_lower):
        raise HTTPException(
            status_code=501,
            detail=f"OAuth is not configured for {datasource}. Please contact your administrator.",
        )

    # Generate state with user context and store in database
    context = {
        "user_id": user.id,
        "datasource": datasource_lower,
    }
    state = await oauth_state_service.create_and_store_state(db, context)

    # Get authorization URL
    auth_url = user_oauth_service.get_auth_url(datasource_lower, state, user.id)

    logger.info(f"User {user.email} starting OAuth for {datasource}")
    return RedirectResponse(url=auth_url)


@router.get("/{datasource}/oauth/callback")
async def oauth_callback(
    datasource: str,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle OAuth callback from provider.

    Exchanges the authorization code for tokens, stores them securely,
    and redirects user back to the app.
    """
    datasource_lower = datasource.lower()

    # Handle OAuth errors
    if error:
        logger.error(f"{datasource} OAuth error: {error}")
        return RedirectResponse(
            url=f"{settings.frontend_url}?oauth_error={datasource}&message={error}"
        )

    # Validate required parameters
    if not code or not state:
        logger.error(f"Missing code or state in {datasource} OAuth callback")
        return RedirectResponse(
            url=f"{settings.frontend_url}?oauth_error={datasource}&message=missing_params"
        )

    # Validate and consume state (database-backed for multi-instance)
    state_data = await oauth_state_service.validate_and_consume_state(db, state)
    if state_data is None:
        logger.error(f"Invalid OAuth state for {datasource} - possible CSRF attack or expired")
        return RedirectResponse(
            url=f"{settings.frontend_url}?oauth_error={datasource}&message=invalid_state"
        )

    user_id = state_data.get("user_id")
    if not user_id:
        logger.error(f"Missing user_id in OAuth state for {datasource}")
        return RedirectResponse(
            url=f"{settings.frontend_url}?oauth_error={datasource}&message=invalid_state"
        )

    try:
        # Exchange code for tokens
        token_response = await user_oauth_service.exchange_code(datasource_lower, code)

        # Process response into credentials format
        credentials = await user_oauth_service.process_oauth_response(datasource_lower, token_response)

        # Save credentials for user
        await credential_service.save_credentials(
            datasource=datasource_lower,
            credentials=credentials,
            db=db,
            user_id=user_id,
        )

        logger.info(f"OAuth successful for user {user_id[:8]}... datasource: {datasource}")

        # Redirect back to app with success
        return RedirectResponse(
            url=f"{settings.frontend_url}?oauth_success={datasource}"
        )

    except Exception as e:
        logger.error(f"{datasource} OAuth callback error: {e}")
        return RedirectResponse(
            url=f"{settings.frontend_url}?oauth_error={datasource}&message=oauth_failed"
        )
