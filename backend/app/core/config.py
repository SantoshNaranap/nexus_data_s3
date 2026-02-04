"""Application configuration."""

import os
import logging
from pydantic_settings import BaseSettings
from pydantic import field_validator, ConfigDict
from typing import List
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


def _get_or_generate_encryption_key() -> str:
    """
    Get encryption key from environment or generate and persist one.

    In development: Auto-generates and saves to .env file.
    In production: Should be set via environment variable.
    """
    env_key = os.getenv("ENCRYPTION_KEY", "").strip()
    if env_key:
        return env_key

    # Check if we're in production mode
    environment = os.getenv("ENVIRONMENT", "development").lower()
    if environment == "production":
        raise ValueError(
            "ENCRYPTION_KEY is required in production. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    # Development mode: generate and persist key
    new_key = Fernet.generate_key().decode()

    # Try to append to .env file
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    try:
        with open(env_file, "a") as f:
            f.write(f"\n# Auto-generated encryption key (DO NOT share in production)\nENCRYPTION_KEY={new_key}\n")
        logger.warning(f"Generated new ENCRYPTION_KEY and saved to {env_file}")
    except Exception as e:
        logger.warning(f"Could not save ENCRYPTION_KEY to .env: {e}. Key will be regenerated on restart!")

    return new_key


class Settings(BaseSettings):
    """Application settings."""

    # Environment
    environment: str = "development"  # development, staging, production

    # API Configuration
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    api_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment.lower() == "production"

    # Anthropic Claude
    anthropic_api_key: str = ""

    # AWS S3
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-1"

    # MySQL (Connector - for user data queries)
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = ""
    mysql_password: str = ""
    mysql_database: str = ""

    # Local MySQL (App database - for chat history, users, credentials)
    local_mysql_host: str = "localhost"
    local_mysql_port: int = 3306
    local_mysql_user: str = "root"
    local_mysql_password: str = ""
    local_mysql_database: str = "connectorMCP"

    # JIRA
    jira_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""

    # Shopify
    shopify_shop_url: str = ""
    shopify_access_token: str = ""
    shopify_api_version: str = "2024-01"

    # Google Workspace (OAuth) - for user login
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = ""  # e.g., https://yourapp.com/api/auth/google/callback
    user_google_email: str = ""  # Optional: for single-user mode

    # Slack - defaults for connector (can be overridden by tenant/user creds)
    slack_bot_token: str = ""  # Bot token (xoxb-) for channels
    slack_user_token: str = ""  # User token (xoxp-) for DMs - required for reading DMs
    slack_app_token: str = ""  # Optional: for Socket Mode
    # Slack OAuth - for admin datasource connection
    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_oauth_redirect_uri: str = ""  # e.g., https://yourapp.com/api/admin/datasources/slack/callback

    # GitHub - defaults for connector (can be overridden by tenant/user creds)
    github_token: str = ""  # Personal Access Token or GitHub App token
    # GitHub OAuth - for admin datasource connection
    github_client_id: str = ""
    github_client_secret: str = ""
    github_oauth_redirect_uri: str = ""  # e.g., https://yourapp.com/api/admin/datasources/github/callback

    # Jira OAuth - for admin datasource connection
    jira_client_id: str = ""
    jira_client_secret: str = ""
    jira_oauth_redirect_uri: str = ""  # e.g., https://yourapp.com/api/admin/datasources/jira/callback

    # JWT Configuration
    jwt_secret_key: str = "insecure-jwt-secret-key-dev-only"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440

    @field_validator("jwt_secret_key", mode="after")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Ensure JWT secret is explicitly set in production."""
        environment = os.getenv("ENVIRONMENT", "development").lower()
        if environment == "production":
            if not v or v == "insecure-jwt-secret-key-dev-only":
                raise ValueError(
                    "CRITICAL: JWT_SECRET_KEY must be explicitly set in production! "
                    "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
                )
            if len(v) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be at least 32 characters in production for security."
                )
        return v

    # Logging
    log_level: str = "INFO"
    log_format: str = "development"  # "development" for readable, "json" for structured

    # Encryption - will be auto-generated in development if not set
    # Primary encryption key (v2 - current)
    encryption_key: str = ""
    # Legacy encryption key (v1 - for decryption during rotation)
    encryption_key_v1: str = ""

    # Frontend URL - IMPORTANT: Configure this in production!
    frontend_url: str = "http://localhost:5173"

    # Security settings
    cookie_secure: bool = False  # Set to True in production (requires HTTPS)
    cookie_samesite: str = "lax"  # "strict" for production, "lax" for development

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 60
    rate_limit_requests_per_hour: int = 1000
    rate_limit_backend: str = "memory"  # "memory" or "redis"

    # Trusted proxies for X-Forwarded-For header validation
    # Comma-separated list of IP addresses or CIDR ranges
    # Only trust X-Forwarded-For from these addresses
    trusted_proxies: str = ""  # e.g., "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

    @property
    def trusted_proxy_list(self) -> list:
        """Parse trusted proxies from comma-separated string."""
        if not self.trusted_proxies:
            return []
        return [p.strip() for p in self.trusted_proxies.split(",") if p.strip()]

    # Application version (for health checks)
    version: str = "1.0.0"

    @property
    def cookie_settings(self) -> dict:
        """Get cookie security settings based on environment."""
        if self.is_production:
            return {
                "secure": True,
                "samesite": "strict",
                "httponly": True,
            }
        return {
            "secure": self.cookie_secure,
            "samesite": self.cookie_samesite,
            "httponly": True,
        }

    @field_validator("encryption_key", mode="before")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        """Ensure encryption key is set, generate if in development."""
        if v and v.strip():
            return v.strip()
        return _get_or_generate_encryption_key()

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # Ignore extra fields in .env
    )


settings = Settings()
