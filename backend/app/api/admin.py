"""Admin endpoints for managing organization-level datasource connections."""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.logging import get_logger
from app.middleware.auth import get_current_user
from app.models.database import User
from app.services.tenant_service import tenant_service
from app.services.tenant_datasource_service import tenant_datasource_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])

# In-memory store for OAuth states (in production, use Redis or database)
oauth_states: dict = {}


# ============ Request/Response Models ============


class DataSourceStatus(BaseModel):
    """Status of a datasource connection."""
    datasource: str
    connected: bool
    metadata: Optional[dict] = None
    connected_by: Optional[str] = None
    connected_at: Optional[str] = None


class TenantUserInfo(BaseModel):
    """User info for admin view."""
    id: str
    email: str
    name: Optional[str]
    role: str
    created_at: Optional[str]


# ============ Helper Functions ============


def require_admin(user: User) -> User:
    """Require the user to be an admin."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


def require_tenant(user: User) -> User:
    """Require the user to belong to a tenant."""
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not belong to an organization",
        )
    return user


# ============ Admin Info Endpoints ============


@router.get("/me")
async def get_admin_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current admin user info with tenant details."""
    require_tenant(current_user)

    tenant = await tenant_service.get_tenant_by_id(db, current_user.tenant_id)

    return {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "name": current_user.name,
            "role": current_user.role,
            "is_admin": current_user.is_admin,
        },
        "tenant": tenant.to_dict() if tenant else None,
    }


@router.get("/users", response_model=List[TenantUserInfo])
async def get_tenant_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all users in the admin's organization (admin only)."""
    require_admin(current_user)
    require_tenant(current_user)

    users = await tenant_service.get_tenant_users(db, current_user.tenant_id)

    return [
        TenantUserInfo(
            id=u.id,
            email=u.email,
            name=u.name,
            role=u.role,
            created_at=u.created_at.isoformat() if u.created_at else None,
        )
        for u in users
    ]


# ============ Datasource Management Endpoints ============


@router.get("/datasources", response_model=List[DataSourceStatus])
async def list_datasources(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all organization datasource connections.

    Returns connection status for each supported datasource.
    """
    require_tenant(current_user)

    # Get all connected datasources for tenant
    connected = await tenant_datasource_service.get_all_tenant_datasources(
        db, current_user.tenant_id
    )
    connected_map = {ds.datasource: ds for ds in connected}

    # Build status for all supported datasources
    supported = ["slack", "github", "jira"]
    statuses = []

    for ds_type in supported:
        if ds_type in connected_map:
            ds = connected_map[ds_type]
            statuses.append(
                DataSourceStatus(
                    datasource=ds_type,
                    connected=True,
                    metadata=ds.oauth_metadata,
                    connected_by=ds.connected_by,
                    connected_at=ds.created_at.isoformat() if ds.created_at else None,
                )
            )
        else:
            statuses.append(
                DataSourceStatus(
                    datasource=ds_type,
                    connected=False,
                )
            )

    return statuses


@router.delete("/datasources/{datasource}")
async def disconnect_datasource(
    datasource: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect an organization datasource (admin only)."""
    require_admin(current_user)
    require_tenant(current_user)

    if datasource not in ["slack", "github", "jira"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown datasource: {datasource}",
        )

    deleted = await tenant_datasource_service.delete_tenant_datasource(
        db, current_user.tenant_id, datasource
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Datasource {datasource} not connected",
        )

    logger.info(f"Admin {current_user.email} disconnected {datasource}")
    return {"message": f"Disconnected {datasource} successfully"}


# ============ Slack OAuth Endpoints ============


@router.get("/datasources/slack/connect")
async def slack_connect(
    current_user: User = Depends(get_current_user),
):
    """Start Slack OAuth flow (admin only)."""
    require_admin(current_user)
    require_tenant(current_user)

    if not settings.slack_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Slack OAuth is not configured",
        )

    # Generate state with user/tenant context
    state = tenant_datasource_service.generate_oauth_state()
    oauth_states[state] = {
        "user_id": current_user.id,
        "tenant_id": current_user.tenant_id,
        "datasource": "slack",
    }

    auth_url = tenant_datasource_service.get_slack_auth_url(state)
    logger.info(f"Admin {current_user.email} starting Slack OAuth")
    return RedirectResponse(url=auth_url)


@router.get("/datasources/slack/callback")
async def slack_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle Slack OAuth callback."""
    if error:
        logger.error(f"Slack OAuth error: {error}")
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?error=slack_oauth_error&message={error}"
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?error=missing_params"
        )

    if state not in oauth_states:
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?error=invalid_state"
        )

    state_data = oauth_states.pop(state)
    tenant_id = state_data["tenant_id"]
    user_id = state_data["user_id"]

    try:
        # Exchange code for tokens
        token_response = await tenant_datasource_service.exchange_slack_code(code)

        if not token_response.get("ok"):
            raise ValueError(token_response.get("error", "Unknown Slack error"))

        # Extract credentials and metadata
        access_token = token_response.get("access_token")
        team = token_response.get("team", {})

        credentials = {
            "access_token": access_token,
            "bot_user_id": token_response.get("bot_user_id"),
            "team_id": team.get("id"),
        }

        metadata = {
            "team_name": team.get("name"),
            "team_id": team.get("id"),
        }

        # Save to tenant datasource
        await tenant_datasource_service.save_tenant_datasource(
            db=db,
            tenant_id=tenant_id,
            datasource="slack",
            credentials=credentials,
            oauth_metadata=metadata,
            connected_by=user_id,
        )

        logger.info(f"Slack connected for tenant {tenant_id}")
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?success=slack_connected"
        )

    except Exception as e:
        logger.error(f"Slack OAuth callback error: {e}")
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?error=slack_oauth_failed"
        )


# ============ GitHub OAuth Endpoints ============


@router.get("/datasources/github/connect")
async def github_connect(
    current_user: User = Depends(get_current_user),
):
    """Start GitHub OAuth flow (admin only)."""
    require_admin(current_user)
    require_tenant(current_user)

    if not settings.github_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GitHub OAuth is not configured",
        )

    state = tenant_datasource_service.generate_oauth_state()
    oauth_states[state] = {
        "user_id": current_user.id,
        "tenant_id": current_user.tenant_id,
        "datasource": "github",
    }

    auth_url = tenant_datasource_service.get_github_auth_url(state)
    logger.info(f"Admin {current_user.email} starting GitHub OAuth")
    return RedirectResponse(url=auth_url)


@router.get("/datasources/github/callback")
async def github_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle GitHub OAuth callback."""
    if error:
        logger.error(f"GitHub OAuth error: {error}")
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?error=github_oauth_error&message={error}"
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?error=missing_params"
        )

    if state not in oauth_states:
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?error=invalid_state"
        )

    state_data = oauth_states.pop(state)
    tenant_id = state_data["tenant_id"]
    user_id = state_data["user_id"]

    try:
        # Exchange code for tokens
        token_response = await tenant_datasource_service.exchange_github_code(code)

        access_token = token_response.get("access_token")
        if not access_token:
            raise ValueError(token_response.get("error", "No access token"))

        # Get user info for metadata
        user_info = await tenant_datasource_service.get_github_user_info(access_token)

        credentials = {
            "access_token": access_token,
            "token_type": token_response.get("token_type", "bearer"),
        }

        metadata = {
            "login": user_info.get("login"),
            "name": user_info.get("name"),
            "avatar_url": user_info.get("avatar_url"),
        }

        # Save to tenant datasource
        await tenant_datasource_service.save_tenant_datasource(
            db=db,
            tenant_id=tenant_id,
            datasource="github",
            credentials=credentials,
            oauth_metadata=metadata,
            connected_by=user_id,
        )

        logger.info(f"GitHub connected for tenant {tenant_id}")
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?success=github_connected"
        )

    except Exception as e:
        logger.error(f"GitHub OAuth callback error: {e}")
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?error=github_oauth_failed"
        )


# ============ Jira OAuth Endpoints ============


@router.get("/datasources/jira/connect")
async def jira_connect(
    current_user: User = Depends(get_current_user),
):
    """Start Jira OAuth flow (admin only)."""
    require_admin(current_user)
    require_tenant(current_user)

    if not settings.jira_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Jira OAuth is not configured",
        )

    state = tenant_datasource_service.generate_oauth_state()
    oauth_states[state] = {
        "user_id": current_user.id,
        "tenant_id": current_user.tenant_id,
        "datasource": "jira",
    }

    auth_url = tenant_datasource_service.get_jira_auth_url(state)
    logger.info(f"Admin {current_user.email} starting Jira OAuth")
    return RedirectResponse(url=auth_url)


@router.get("/datasources/jira/callback")
async def jira_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle Jira OAuth callback."""
    if error:
        logger.error(f"Jira OAuth error: {error}")
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?error=jira_oauth_error&message={error}"
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?error=missing_params"
        )

    if state not in oauth_states:
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?error=invalid_state"
        )

    state_data = oauth_states.pop(state)
    tenant_id = state_data["tenant_id"]
    user_id = state_data["user_id"]

    try:
        # Exchange code for tokens
        token_response = await tenant_datasource_service.exchange_jira_code(code)

        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")

        if not access_token:
            raise ValueError("No access token in response")

        # Get accessible Jira sites
        sites = await tenant_datasource_service.get_jira_accessible_resources(access_token)

        if not sites:
            raise ValueError("No Jira sites accessible with this token")

        # Use first site by default
        site = sites[0]

        credentials = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "cloud_id": site.get("id"),
            "site_url": site.get("url"),
        }

        metadata = {
            "site_name": site.get("name"),
            "site_url": site.get("url"),
            "cloud_id": site.get("id"),
        }

        # Save to tenant datasource
        await tenant_datasource_service.save_tenant_datasource(
            db=db,
            tenant_id=tenant_id,
            datasource="jira",
            credentials=credentials,
            oauth_metadata=metadata,
            connected_by=user_id,
        )

        logger.info(f"Jira connected for tenant {tenant_id}")
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?success=jira_connected"
        )

    except Exception as e:
        logger.error(f"Jira OAuth callback error: {e}")
        return RedirectResponse(
            url=f"{settings.frontend_url}/settings?error=jira_oauth_failed"
        )


# ============ OAuth Availability Check ============


@router.get("/oauth/available")
async def oauth_available():
    """Check which OAuth integrations are configured."""
    return {
        "slack": bool(settings.slack_client_id and settings.slack_client_secret),
        "github": bool(settings.github_client_id and settings.github_client_secret),
        "jira": bool(settings.jira_client_id and settings.jira_client_secret),
    }
