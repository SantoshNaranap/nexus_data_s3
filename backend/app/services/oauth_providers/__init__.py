"""OAuth providers package."""

from app.services.oauth_providers.base import OAuthProvider
from app.services.oauth_providers.google import GoogleOAuthProvider

# Registry of OAuth providers
OAUTH_PROVIDERS = {
    "google_workspace": GoogleOAuthProvider,
}


def get_oauth_provider(provider_name: str) -> OAuthProvider:
    """Get OAuth provider instance by name."""
    provider_class = OAUTH_PROVIDERS.get(provider_name)
    if not provider_class:
        raise ValueError(f"Unknown OAuth provider: {provider_name}")
    return provider_class()


def is_oauth_provider(datasource: str) -> bool:
    """Check if a datasource uses OAuth."""
    return datasource in OAUTH_PROVIDERS


__all__ = [
    "OAuthProvider",
    "GoogleOAuthProvider",
    "OAUTH_PROVIDERS",
    "get_oauth_provider",
    "is_oauth_provider",
]
