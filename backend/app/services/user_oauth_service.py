"""Per-user OAuth service for connecting individual user accounts to data sources."""

import logging
import secrets
import httpx
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession
from cryptography.fernet import Fernet

from app.core.config import settings

logger = logging.getLogger(__name__)

# OAuth endpoints for each datasource
OAUTH_CONFIG = {
    "slack": {
        "auth_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        # User scopes for accessing their own data
        "scopes": "channels:read,channels:history,groups:read,groups:history,im:read,im:history,mpim:read,mpim:history,users:read,search:read,files:read",
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


class UserOAuthService:
    """Service for managing per-user OAuth connections to data sources."""

    def __init__(self):
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
    def generate_state() -> str:
        """Generate a secure random state for OAuth CSRF protection."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def is_oauth_configured(datasource: str) -> bool:
        """Check if OAuth is configured for a datasource."""
        ds = datasource.lower()
        if ds == "slack":
            return bool(settings.slack_client_id and settings.slack_client_secret)
        elif ds == "github":
            return bool(settings.github_client_id and settings.github_client_secret)
        elif ds == "jira":
            return bool(settings.jira_client_id and settings.jira_client_secret)
        return False

    # ============ Slack OAuth ============

    def get_slack_auth_url(self, state: str, user_id: str) -> str:
        """Generate Slack OAuth authorization URL for user."""
        redirect_uri = settings.slack_oauth_redirect_uri
        if not redirect_uri:
            redirect_uri = f"{settings.api_base_url}/api/credentials/slack/oauth/callback"

        params = {
            "client_id": settings.slack_client_id,
            "user_scope": OAUTH_CONFIG["slack"]["scopes"],  # User scopes, not bot scopes
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"{OAUTH_CONFIG['slack']['auth_url']}?{urlencode(params)}"

    async def exchange_slack_code(self, code: str) -> Dict[str, Any]:
        """Exchange Slack OAuth code for user tokens."""
        redirect_uri = settings.slack_oauth_redirect_uri
        if not redirect_uri:
            redirect_uri = f"{settings.api_base_url}/api/credentials/slack/oauth/callback"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                OAUTH_CONFIG["slack"]["token_url"],
                data={
                    "client_id": settings.slack_client_id,
                    "client_secret": settings.slack_client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            response.raise_for_status()
            return response.json()

    def parse_slack_credentials(self, token_response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Slack OAuth response into credentials format.

        Maps to connector credential_fields:
        - slack_user_token → SLACK_USER_TOKEN (user's own token for DMs, search)
        """
        # For user OAuth, we get authed_user with access_token
        authed_user = token_response.get("authed_user", {})
        user_token = authed_user.get("access_token")

        return {
            # Map to connector's expected field names
            "slack_user_token": user_token,  # Primary token for user OAuth
            "slack_bot_token": user_token,   # Also set as bot token for compatibility
            # Metadata
            "slack_user_id": authed_user.get("id"),
            "slack_team_id": token_response.get("team", {}).get("id"),
            "slack_team_name": token_response.get("team", {}).get("name"),
            "oauth_type": "user",
        }

    # ============ GitHub OAuth ============

    def get_github_auth_url(self, state: str, user_id: str) -> str:
        """Generate GitHub OAuth authorization URL for user."""
        redirect_uri = settings.github_oauth_redirect_uri
        if not redirect_uri:
            redirect_uri = f"{settings.api_base_url}/api/credentials/github/oauth/callback"

        params = {
            "client_id": settings.github_client_id,
            "scope": OAUTH_CONFIG["github"]["scopes"],
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"{OAUTH_CONFIG['github']['auth_url']}?{urlencode(params)}"

    async def exchange_github_code(self, code: str) -> Dict[str, Any]:
        """Exchange GitHub OAuth code for tokens."""
        redirect_uri = settings.github_oauth_redirect_uri
        if not redirect_uri:
            redirect_uri = f"{settings.api_base_url}/api/credentials/github/oauth/callback"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                OAUTH_CONFIG["github"]["token_url"],
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
        """Get GitHub user info."""
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

    def parse_github_credentials(self, token_response: Dict[str, Any], user_info: Dict[str, Any]) -> Dict[str, Any]:
        """Parse GitHub OAuth response into credentials format.

        Maps to connector credential_fields:
        - github_token → GITHUB_TOKEN
        """
        return {
            # Map to connector's expected field name
            "github_token": token_response.get("access_token"),
            # Metadata
            "token_type": token_response.get("token_type", "bearer"),
            "github_login": user_info.get("login"),
            "github_name": user_info.get("name"),
            "oauth_type": "user",
        }

    # ============ Jira OAuth ============

    def get_jira_auth_url(self, state: str, user_id: str) -> str:
        """Generate Jira OAuth authorization URL for user."""
        redirect_uri = settings.jira_oauth_redirect_uri
        if not redirect_uri:
            redirect_uri = f"{settings.api_base_url}/api/credentials/jira/oauth/callback"

        params = {
            "audience": OAUTH_CONFIG["jira"]["audience"],
            "client_id": settings.jira_client_id,
            "scope": OAUTH_CONFIG["jira"]["scopes"],
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
            "prompt": "consent",
        }
        return f"{OAUTH_CONFIG['jira']['auth_url']}?{urlencode(params)}"

    async def exchange_jira_code(self, code: str) -> Dict[str, Any]:
        """Exchange Jira OAuth code for tokens."""
        redirect_uri = settings.jira_oauth_redirect_uri
        if not redirect_uri:
            redirect_uri = f"{settings.api_base_url}/api/credentials/jira/oauth/callback"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                OAUTH_CONFIG["jira"]["token_url"],
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

    def parse_jira_credentials(self, token_response: Dict[str, Any], sites: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse Jira OAuth response into credentials format.

        Maps to connector credential_fields:
        - jira_url → JIRA_URL
        - jira_api_token → JIRA_API_TOKEN (OAuth access token)
        - jira_cloud_id → JIRA_CLOUD_ID (for OAuth API calls)

        Note: Jira OAuth uses Bearer tokens instead of Basic Auth.
        The connector may need to detect oauth_type and use Bearer auth.
        """
        site = sites[0] if sites else {}
        site_url = site.get("url", "")

        # Clean up site URL - remove trailing slash, ensure https
        if site_url and not site_url.startswith("https://"):
            site_url = f"https://{site_url}"
        site_url = site_url.rstrip("/")

        # Calculate token expiry time (Jira tokens expire in 1 hour = 3600 seconds)
        expires_in = token_response.get("expires_in", 3600)
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

        return {
            # Map to connector's expected field names
            "jira_url": site_url,
            "jira_api_token": token_response.get("access_token"),  # OAuth token as API token
            "jira_cloud_id": site.get("id"),  # Cloud ID for OAuth API endpoints
            # OAuth-specific fields
            "jira_refresh_token": token_response.get("refresh_token"),
            "jira_site_name": site.get("name"),
            "oauth_type": "user",  # Indicates Bearer auth should be used
            # Token expiry tracking for proactive refresh
            "expires_at": expires_at,
            "expires_in": expires_in,
        }

    async def refresh_jira_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh Jira OAuth access token using refresh token.

        Args:
            refresh_token: The refresh token from initial OAuth flow

        Returns:
            New token response with access_token and possibly new refresh_token
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                OAUTH_CONFIG["jira"]["token_url"],
                json={
                    "grant_type": "refresh_token",
                    "client_id": settings.jira_client_id,
                    "client_secret": settings.jira_client_secret,
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
            return response.json()

    async def refresh_jira_credentials(self, current_credentials: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Refresh Jira credentials using the stored refresh token.

        Args:
            current_credentials: Current stored credentials with refresh_token

        Returns:
            Updated credentials dict with new access_token, or None if refresh fails
        """
        refresh_token = current_credentials.get("jira_refresh_token")
        if not refresh_token:
            logger.warning("No refresh token available for Jira credentials")
            return None

        try:
            token_response = await self.refresh_jira_token(refresh_token)

            # Update credentials with new tokens
            updated_credentials = current_credentials.copy()
            updated_credentials["jira_api_token"] = token_response.get("access_token")

            # Update refresh token if a new one was provided
            if token_response.get("refresh_token"):
                updated_credentials["jira_refresh_token"] = token_response.get("refresh_token")

            # Update token expiry time
            expires_in = token_response.get("expires_in", 3600)
            updated_credentials["expires_at"] = (
                datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            ).isoformat()
            updated_credentials["expires_in"] = expires_in
            updated_credentials["last_refreshed_at"] = datetime.now(timezone.utc).isoformat()

            logger.info("Successfully refreshed Jira OAuth token")
            return updated_credentials

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to refresh Jira token: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error refreshing Jira token: {e}")
            return None

    # ============ Generic Methods ============

    def get_auth_url(self, datasource: str, state: str, user_id: str) -> Optional[str]:
        """Get OAuth authorization URL for any supported datasource."""
        ds = datasource.lower()
        if ds == "slack":
            return self.get_slack_auth_url(state, user_id)
        elif ds == "github":
            return self.get_github_auth_url(state, user_id)
        elif ds == "jira":
            return self.get_jira_auth_url(state, user_id)
        return None

    async def exchange_code(self, datasource: str, code: str) -> Dict[str, Any]:
        """Exchange OAuth code for tokens for any supported datasource."""
        ds = datasource.lower()
        if ds == "slack":
            return await self.exchange_slack_code(code)
        elif ds == "github":
            return await self.exchange_github_code(code)
        elif ds == "jira":
            return await self.exchange_jira_code(code)
        raise ValueError(f"Unsupported datasource: {datasource}")

    async def process_oauth_response(self, datasource: str, token_response: Dict[str, Any]) -> Dict[str, Any]:
        """Process OAuth response and return standardized credentials."""
        ds = datasource.lower()

        if ds == "slack":
            if not token_response.get("ok"):
                raise ValueError(token_response.get("error", "Slack OAuth failed"))
            return self.parse_slack_credentials(token_response)

        elif ds == "github":
            access_token = token_response.get("access_token")
            if not access_token:
                raise ValueError(token_response.get("error", "GitHub OAuth failed"))
            user_info = await self.get_github_user_info(access_token)
            return self.parse_github_credentials(token_response, user_info)

        elif ds == "jira":
            access_token = token_response.get("access_token")
            if not access_token:
                raise ValueError("Jira OAuth failed - no access token")
            sites = await self.get_jira_accessible_resources(access_token)
            if not sites:
                raise ValueError("No Jira sites accessible with this token")
            return self.parse_jira_credentials(token_response, sites)

        raise ValueError(f"Unsupported datasource: {datasource}")


# Singleton instance
user_oauth_service = UserOAuthService()
