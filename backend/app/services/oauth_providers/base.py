"""Base OAuth provider abstract class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class OAuthTokens:
    """OAuth token data returned from providers."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_at: Optional[datetime] = None
    scopes: Optional[List[str]] = None
    provider_user_id: Optional[str] = None
    provider_email: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class OAuthProvider(ABC):
    """Abstract base class for OAuth providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'google_workspace')."""
        pass

    @property
    @abstractmethod
    def authorization_endpoint(self) -> str:
        """Return the OAuth authorization endpoint URL."""
        pass

    @property
    @abstractmethod
    def token_endpoint(self) -> str:
        """Return the OAuth token endpoint URL."""
        pass

    @property
    @abstractmethod
    def default_scopes(self) -> List[str]:
        """Return the default OAuth scopes to request."""
        pass

    @abstractmethod
    def get_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        scopes: Optional[List[str]] = None,
    ) -> str:
        """
        Generate the OAuth authorization URL.

        Args:
            redirect_uri: The callback URL after authorization
            state: CSRF protection state token
            scopes: Optional list of scopes (uses default_scopes if not provided)

        Returns:
            The full authorization URL to redirect the user to
        """
        pass

    @abstractmethod
    async def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: str,
    ) -> OAuthTokens:
        """
        Exchange authorization code for access tokens.

        Args:
            code: The authorization code from the callback
            redirect_uri: The redirect URI used in the authorization request

        Returns:
            OAuthTokens containing the access token and other data
        """
        pass

    @abstractmethod
    async def refresh_access_token(
        self,
        refresh_token: str,
    ) -> OAuthTokens:
        """
        Refresh an expired access token.

        Args:
            refresh_token: The refresh token

        Returns:
            OAuthTokens with the new access token
        """
        pass

    @abstractmethod
    async def revoke_token(
        self,
        token: str,
    ) -> bool:
        """
        Revoke an OAuth token.

        Args:
            token: The token to revoke (access or refresh)

        Returns:
            True if revocation succeeded
        """
        pass

    async def get_user_info(
        self,
        access_token: str,
    ) -> Dict[str, Any]:
        """
        Get user information using the access token.

        Args:
            access_token: The OAuth access token

        Returns:
            Dictionary with user info (email, id, name, etc.)
        """
        raise NotImplementedError("get_user_info not implemented for this provider")
