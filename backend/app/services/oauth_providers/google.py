"""Google OAuth provider implementation."""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from urllib.parse import urlencode
import httpx

from app.core.config import settings
from app.services.oauth_providers.base import OAuthProvider, OAuthTokens

logger = logging.getLogger(__name__)


class GoogleOAuthProvider(OAuthProvider):
    """Google OAuth 2.0 provider for Google Workspace APIs."""

    # Google OAuth endpoints
    AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    REVOKE_URL = "https://oauth2.googleapis.com/revoke"

    # Default scopes for Google Workspace
    DEFAULT_SCOPES = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/documents.readonly",
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    ]

    @property
    def provider_name(self) -> str:
        return "google_workspace"

    @property
    def authorization_endpoint(self) -> str:
        return self.AUTHORIZATION_URL

    @property
    def token_endpoint(self) -> str:
        return self.TOKEN_URL

    @property
    def default_scopes(self) -> List[str]:
        return self.DEFAULT_SCOPES

    @property
    def client_id(self) -> str:
        return settings.google_oauth_client_id

    @property
    def client_secret(self) -> str:
        return settings.google_oauth_client_secret

    @property
    def redirect_uri(self) -> str:
        return settings.google_oauth_redirect_uri

    def get_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: Optional[List[str]] = None,
    ) -> str:
        """Generate Google OAuth authorization URL."""
        if not self.client_id:
            raise ValueError("Google OAuth client ID not configured")

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes or self.default_scopes),
            "state": state,
            "access_type": "offline",  # Request refresh token
            "prompt": "consent",  # Always show consent screen to get refresh token
            "include_granted_scopes": "true",
        }

        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: str,
    ) -> OAuthTokens:
        """Exchange authorization code for Google OAuth tokens."""
        if not self.client_id or not self.client_secret:
            raise ValueError("Google OAuth credentials not configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                error_data = response.json()
                logger.error(f"Google token exchange failed: {error_data}")
                raise Exception(f"Failed to exchange code: {error_data.get('error_description', 'Unknown error')}")

            token_data = response.json()

        # Calculate expiry time
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # Get user info
        user_info = await self.get_user_info(token_data["access_token"])

        return OAuthTokens(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_type=token_data.get("token_type", "Bearer"),
            expires_at=expires_at,
            scopes=token_data.get("scope", "").split(),
            provider_user_id=user_info.get("id"),
            provider_email=user_info.get("email"),
            metadata={
                "name": user_info.get("name"),
                "picture": user_info.get("picture"),
            },
        )

    async def refresh_access_token(
        self,
        refresh_token: str,
    ) -> OAuthTokens:
        """Refresh Google OAuth access token."""
        if not self.client_id or not self.client_secret:
            raise ValueError("Google OAuth credentials not configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                error_data = response.json()
                logger.error(f"Google token refresh failed: {error_data}")
                raise Exception(f"Failed to refresh token: {error_data.get('error_description', 'Unknown error')}")

            token_data = response.json()

        # Calculate new expiry time
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        return OAuthTokens(
            access_token=token_data["access_token"],
            refresh_token=refresh_token,  # Refresh token stays the same
            token_type=token_data.get("token_type", "Bearer"),
            expires_at=expires_at,
            scopes=token_data.get("scope", "").split(),
        )

    async def revoke_token(
        self,
        token: str,
    ) -> bool:
        """Revoke a Google OAuth token."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.REVOKE_URL,
                params={"token": token},
            )

            if response.status_code == 200:
                logger.info("Google token revoked successfully")
                return True
            else:
                logger.warning(f"Google token revocation returned status {response.status_code}")
                return False

    async def get_user_info(
        self,
        access_token: str,
    ) -> Dict[str, Any]:
        """Get user info from Google."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code != 200:
                logger.error(f"Failed to get Google user info: {response.status_code}")
                return {}

            return response.json()
