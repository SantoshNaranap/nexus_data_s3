"""Tenant datasource service for managing organization-level OAuth connections."""

import logging
import secrets
import httpx
import json
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from cryptography.fernet import Fernet

from app.core.config import settings
from app.models.database import TenantDataSource, User

logger = logging.getLogger(__name__)

# OAuth endpoints for each datasource
OAUTH_ENDPOINTS = {
    "slack": {
        "auth_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scopes": "channels:read,channels:history,chat:write,users:read,search:read,files:read,reactions:write,im:read,im:history",
    },
    "github": {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": "repo,read:user,read:org",
    },
    "jira": {
        "auth_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        "audience": "api.atlassian.com",
        "scopes": "read:jira-work read:jira-user write:jira-work offline_access",
    },
}


class TenantDataSourceService:
    """Service for managing tenant-level datasource OAuth connections."""

    def __init__(self):
        """Initialize with encryption key."""
        self._fernet = None

    @property
    def fernet(self) -> Fernet:
        """Lazy-load Fernet encryptor."""
        if self._fernet is None:
            self._fernet = Fernet(settings.encryption_key.encode())
        return self._fernet

    def encrypt_credentials(self, credentials: Dict[str, Any]) -> str:
        """Encrypt credentials dictionary to string."""
        json_str = json.dumps(credentials)
        return self.fernet.encrypt(json_str.encode()).decode()

    def decrypt_credentials(self, encrypted: str) -> Dict[str, Any]:
        """Decrypt credentials string to dictionary."""
        json_str = self.fernet.decrypt(encrypted.encode()).decode()
        return json.loads(json_str)

    @staticmethod
    def generate_oauth_state() -> str:
        """Generate a secure random state for OAuth CSRF protection."""
        return secrets.token_urlsafe(32)

    # ============ Generic Methods ============

    async def get_tenant_datasource(
        self,
        db: AsyncSession,
        tenant_id: str,
        datasource: str,
    ) -> Optional[TenantDataSource]:
        """Get tenant datasource by tenant ID and datasource type."""
        result = await db.execute(
            select(TenantDataSource).where(
                TenantDataSource.tenant_id == tenant_id,
                TenantDataSource.datasource == datasource,
            )
        )
        return result.scalar_one_or_none()

    async def get_all_tenant_datasources(
        self,
        db: AsyncSession,
        tenant_id: str,
    ) -> List[TenantDataSource]:
        """Get all datasources for a tenant."""
        result = await db.execute(
            select(TenantDataSource).where(TenantDataSource.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    async def save_tenant_datasource(
        self,
        db: AsyncSession,
        tenant_id: str,
        datasource: str,
        credentials: Dict[str, Any],
        oauth_metadata: Optional[Dict[str, Any]] = None,
        connected_by: Optional[str] = None,
    ) -> TenantDataSource:
        """
        Save or update tenant datasource credentials.

        Args:
            db: Database session
            tenant_id: Tenant ID
            datasource: Datasource type (slack, github, jira)
            credentials: OAuth tokens and credentials
            oauth_metadata: Additional metadata (workspace name, etc.)
            connected_by: User ID who connected this datasource

        Returns:
            TenantDataSource object
        """
        encrypted_creds = self.encrypt_credentials(credentials)

        # Check if exists
        existing = await self.get_tenant_datasource(db, tenant_id, datasource)

        if existing:
            existing.encrypted_credentials = encrypted_creds
            existing.oauth_metadata = oauth_metadata
            existing.connected_by = connected_by
            await db.commit()
            await db.refresh(existing)
            logger.info(f"Updated tenant datasource: {datasource} for tenant {tenant_id}")
            return existing

        # Create new
        tenant_ds = TenantDataSource(
            tenant_id=tenant_id,
            datasource=datasource,
            encrypted_credentials=encrypted_creds,
            oauth_metadata=oauth_metadata,
            connected_by=connected_by,
        )
        db.add(tenant_ds)
        await db.commit()
        await db.refresh(tenant_ds)

        logger.info(f"Created tenant datasource: {datasource} for tenant {tenant_id}")
        return tenant_ds

    async def delete_tenant_datasource(
        self,
        db: AsyncSession,
        tenant_id: str,
        datasource: str,
    ) -> bool:
        """Delete a tenant datasource connection."""
        result = await db.execute(
            delete(TenantDataSource).where(
                TenantDataSource.tenant_id == tenant_id,
                TenantDataSource.datasource == datasource,
            )
        )
        await db.commit()
        deleted = result.rowcount > 0
        if deleted:
            logger.info(f"Deleted tenant datasource: {datasource} for tenant {tenant_id}")
        return deleted

    async def get_decrypted_credentials(
        self,
        db: AsyncSession,
        tenant_id: str,
        datasource: str,
    ) -> Optional[Dict[str, Any]]:
        """Get decrypted credentials for a tenant datasource."""
        tenant_ds = await self.get_tenant_datasource(db, tenant_id, datasource)
        if not tenant_ds:
            return None
        return self.decrypt_credentials(tenant_ds.encrypted_credentials)

    # ============ Slack OAuth ============

    def get_slack_auth_url(self, state: str) -> str:
        """Generate Slack OAuth authorization URL."""
        redirect_uri = settings.slack_oauth_redirect_uri
        if not redirect_uri:
            redirect_uri = f"{settings.api_base_url}/api/admin/datasources/slack/callback"

        params = {
            "client_id": settings.slack_client_id,
            "scope": OAUTH_ENDPOINTS["slack"]["scopes"],
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"{OAUTH_ENDPOINTS['slack']['auth_url']}?{urlencode(params)}"

    async def exchange_slack_code(self, code: str) -> Dict[str, Any]:
        """Exchange Slack OAuth code for tokens."""
        redirect_uri = settings.slack_oauth_redirect_uri
        if not redirect_uri:
            redirect_uri = f"{settings.api_base_url}/api/admin/datasources/slack/callback"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                OAUTH_ENDPOINTS["slack"]["token_url"],
                data={
                    "client_id": settings.slack_client_id,
                    "client_secret": settings.slack_client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            response.raise_for_status()
            return response.json()

    # ============ GitHub OAuth ============

    def get_github_auth_url(self, state: str) -> str:
        """Generate GitHub OAuth authorization URL."""
        redirect_uri = settings.github_oauth_redirect_uri
        if not redirect_uri:
            redirect_uri = f"{settings.api_base_url}/api/admin/datasources/github/callback"

        params = {
            "client_id": settings.github_client_id,
            "scope": OAUTH_ENDPOINTS["github"]["scopes"],
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"{OAUTH_ENDPOINTS['github']['auth_url']}?{urlencode(params)}"

    async def exchange_github_code(self, code: str) -> Dict[str, Any]:
        """Exchange GitHub OAuth code for tokens."""
        redirect_uri = settings.github_oauth_redirect_uri
        if not redirect_uri:
            redirect_uri = f"{settings.api_base_url}/api/admin/datasources/github/callback"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                OAUTH_ENDPOINTS["github"]["token_url"],
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()

    async def get_github_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get GitHub user/organization info."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            response.raise_for_status()
            return response.json()

    # ============ Jira OAuth ============

    def get_jira_auth_url(self, state: str) -> str:
        """Generate Jira OAuth authorization URL."""
        redirect_uri = settings.jira_oauth_redirect_uri
        if not redirect_uri:
            redirect_uri = f"{settings.api_base_url}/api/admin/datasources/jira/callback"

        params = {
            "audience": OAUTH_ENDPOINTS["jira"]["audience"],
            "client_id": settings.jira_client_id,
            "scope": OAUTH_ENDPOINTS["jira"]["scopes"],
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
            "prompt": "consent",
        }
        return f"{OAUTH_ENDPOINTS['jira']['auth_url']}?{urlencode(params)}"

    async def exchange_jira_code(self, code: str) -> Dict[str, Any]:
        """Exchange Jira OAuth code for tokens."""
        redirect_uri = settings.jira_oauth_redirect_uri
        if not redirect_uri:
            redirect_uri = f"{settings.api_base_url}/api/admin/datasources/jira/callback"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                OAUTH_ENDPOINTS["jira"]["token_url"],
                json={
                    "grant_type": "authorization_code",
                    "client_id": settings.jira_client_id,
                    "client_secret": settings.jira_client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            response.raise_for_status()
            return response.json()

    async def get_jira_accessible_resources(self, access_token: str) -> List[Dict[str, Any]]:
        """Get list of Jira sites accessible with token."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.atlassian.com/oauth/token/accessible-resources",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json()


# Singleton instance
tenant_datasource_service = TenantDataSourceService()
