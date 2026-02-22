"""OAuth endpoints for provider authentication (Google, Slack, GitHub, etc.)."""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.logging import get_logger
from app.middleware.auth import get_current_user
from app.models.database import User
from app.services.oauth_service import oauth_service
from app.services.oauth_providers import is_oauth_provider, OAUTH_PROVIDERS

logger = get_logger(__name__)

router = APIRouter(prefix="/api/oauth", tags=["OAuth"])


# ============ Request/Response Models ============


class AuthorizeResponse(BaseModel):
    """Response for OAuth authorization initiation."""
    authorization_url: str


class ConnectionResponse(BaseModel):
    """Response for an OAuth connection."""
    id: str
    provider: str
    provider_email: Optional[str]
    token_type: str
    expires_at: Optional[str]
    scopes: Optional[str]
    is_expired: bool
    needs_refresh: bool
    created_at: str
    updated_at: str


class ConnectionStatusResponse(BaseModel):
    """Response for connection status check."""
    connected: bool
    provider: str
    provider_email: Optional[str] = None
    expires_at: Optional[str] = None
    needs_refresh: bool = False


class AvailableProvidersResponse(BaseModel):
    """Response listing available OAuth providers."""
    providers: List[str]


# ============ Endpoints ============


@router.get("/providers", response_model=AvailableProvidersResponse)
async def list_providers():
    """List available OAuth providers."""
    return AvailableProvidersResponse(providers=list(OAUTH_PROVIDERS.keys()))


@router.post("/{provider}/authorize", response_model=AuthorizeResponse)
async def authorize(
    provider: str,
    current_user: User = Depends(get_current_user),
    scopes: Optional[str] = Query(None, description="Comma-separated list of scopes"),
):
    """
    Initiate OAuth authorization flow.

    Returns the authorization URL to redirect the user to.
    """
    if not is_oauth_provider(provider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown OAuth provider: {provider}. Available: {list(OAUTH_PROVIDERS.keys())}",
        )

    # Parse scopes if provided
    scope_list = None
    if scopes:
        scope_list = [s.strip() for s in scopes.split(",")]

    try:
        authorization_url = oauth_service.get_authorization_url(
            provider=provider,
            user_id=current_user.id,
            scopes=scope_list,
        )

        logger.info(f"OAuth authorization initiated for user {current_user.id[:8]}... provider {provider}")
        return AuthorizeResponse(authorization_url=authorization_url)

    except ValueError as e:
        logger.error(f"OAuth authorization error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{provider}/callback")
async def callback(
    provider: str,
    code: str = Query(..., description="Authorization code from provider"),
    state: str = Query(..., description="State token for CSRF protection"),
    error: Optional[str] = Query(None, description="Error from provider"),
    error_description: Optional[str] = Query(None, description="Error description"),
    db: AsyncSession = Depends(get_db),
):
    """
    Handle OAuth callback from provider.

    This endpoint receives the authorization code and state from the OAuth provider,
    exchanges the code for tokens, and stores them in the database.

    Redirects to frontend with success or error status.
    """
    frontend_url = settings.frontend_url

    # Check for errors from provider
    if error:
        logger.warning(f"OAuth callback error from {provider}: {error} - {error_description}")
        return RedirectResponse(
            url=f"{frontend_url}/settings?oauth=error&provider={provider}&error={error}",
            status_code=status.HTTP_302_FOUND,
        )

    if not is_oauth_provider(provider):
        return RedirectResponse(
            url=f"{frontend_url}/settings?oauth=error&provider={provider}&error=unknown_provider",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        # Handle callback and store tokens
        connection = await oauth_service.handle_callback(
            provider=provider,
            code=code,
            state=state,
            db=db,
        )

        logger.info(f"OAuth callback successful for provider {provider}, user email: {connection.provider_email}")

        # Redirect to frontend with success
        return RedirectResponse(
            url=f"{frontend_url}/settings?oauth=success&provider={provider}",
            status_code=status.HTTP_302_FOUND,
        )

    except ValueError as e:
        logger.error(f"OAuth callback validation error: {e}")
        return RedirectResponse(
            url=f"{frontend_url}/settings?oauth=error&provider={provider}&error=invalid_state",
            status_code=status.HTTP_302_FOUND,
        )
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return RedirectResponse(
            url=f"{frontend_url}/settings?oauth=error&provider={provider}&error=token_exchange_failed",
            status_code=status.HTTP_302_FOUND,
        )


@router.get("/connections", response_model=List[ConnectionResponse])
async def list_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all OAuth connections for the current user."""
    connections = await oauth_service.list_connections(db, current_user.id)

    return [
        ConnectionResponse(
            id=conn.id,
            provider=conn.provider,
            provider_email=conn.provider_email,
            token_type=conn.token_type,
            expires_at=conn.expires_at.isoformat() if conn.expires_at else None,
            scopes=conn.scopes,
            is_expired=conn.is_expired,
            needs_refresh=conn.needs_refresh,
            created_at=conn.created_at.isoformat(),
            updated_at=conn.updated_at.isoformat(),
        )
        for conn in connections
    ]


@router.get("/connections/{provider}/status", response_model=ConnectionStatusResponse)
async def get_connection_status(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check OAuth connection status for a specific provider."""
    if not is_oauth_provider(provider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown OAuth provider: {provider}",
        )

    connection = await oauth_service.get_connection(db, current_user.id, provider)

    if not connection:
        return ConnectionStatusResponse(
            connected=False,
            provider=provider,
        )

    return ConnectionStatusResponse(
        connected=True,
        provider=provider,
        provider_email=connection.provider_email,
        expires_at=connection.expires_at.isoformat() if connection.expires_at else None,
        needs_refresh=connection.needs_refresh,
    )


@router.delete("/connections/{provider}")
async def disconnect(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Disconnect an OAuth provider.

    Revokes the token at the provider (if supported) and deletes the connection.
    """
    if not is_oauth_provider(provider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown OAuth provider: {provider}",
        )

    success = await oauth_service.revoke_connection(db, current_user.id, provider)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No connection found for provider: {provider}",
        )

    logger.info(f"OAuth connection revoked for user {current_user.id[:8]}... provider {provider}")
    return {"message": f"Disconnected from {provider}"}


@router.post("/connections/{provider}/refresh")
async def refresh_connection(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually refresh OAuth tokens for a provider."""
    if not is_oauth_provider(provider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown OAuth provider: {provider}",
        )

    try:
        connection = await oauth_service.refresh_tokens(db, current_user.id, provider)

        return {
            "message": "Tokens refreshed successfully",
            "expires_at": connection.expires_at.isoformat() if connection.expires_at else None,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh tokens",
        )
