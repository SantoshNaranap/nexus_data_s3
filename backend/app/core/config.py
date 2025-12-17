"""Application configuration."""

import os
import logging
from pydantic_settings import BaseSettings
from pydantic import field_validator
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
    anthropic_api_key: str

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

    # Google Workspace (OAuth)
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8000/api/oauth/google_workspace/callback"
    user_google_email: str = ""  # Optional: for single-user mode (legacy)

    # Slack
    slack_bot_token: str = ""  # Bot token (xoxb-) for channels
    slack_user_token: str = ""  # User token (xoxp-) for DMs - required for reading DMs
    slack_app_token: str = ""  # Optional: for Socket Mode

    # GitHub
    github_token: str = ""  # Personal Access Token or GitHub App token

    # JWT Configuration
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440

    # Logging
    log_level: str = "INFO"
    log_format: str = "development"  # "development" for readable, "json" for structured

    # Encryption - will be auto-generated in development if not set
    encryption_key: str = ""

    # Frontend URL - IMPORTANT: Configure this in production!
    frontend_url: str = "http://localhost:5173"

    # Security settings
    cookie_secure: bool = False  # Set to True in production (requires HTTPS)
    cookie_samesite: str = "lax"  # "strict" for production, "lax" for development

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 60
    rate_limit_requests_per_hour: int = 1000

    # Database pool settings
    db_pool_size: int = 10  # Number of persistent connections
    db_max_overflow: int = 20  # Additional connections when pool exhausted
    db_pool_timeout: int = 30  # Seconds to wait for available connection
    db_pool_recycle: int = 3600  # Recycle connections after 1 hour

    # Thread pool settings for streaming
    stream_thread_pool_size: int = 50  # Max concurrent streaming sessions
    stream_queue_timeout: int = 30  # Seconds to wait for thread availability

    # Cache TTL settings (in seconds)
    cache_tools_ttl: int = 300  # 5 minutes for tool definitions
    cache_results_ttl: int = 30  # 30 seconds for query results
    cache_schema_ttl: int = 600  # 10 minutes for database schemas

    # Timeout settings (in seconds)
    query_timeout: int = 60  # Timeout for individual datasource queries
    mcp_connection_timeout: int = 30  # Timeout for MCP server connection
    claude_api_timeout: int = 120  # Timeout for Claude API calls

    # Chat history settings
    chat_max_messages_per_session: int = 100  # Max messages to keep per session
    chat_max_sessions_per_user: int = 50  # Max sessions per user
    chat_history_retention_days: int = 90  # Auto-delete history older than this

    # Agent orchestrator settings
    agent_max_iterations: int = 25  # Max tool use iterations
    agent_max_sources: int = 5  # Max sources to query in parallel

    # Security settings
    csrf_enabled: bool = True  # Enable CSRF protection
    max_login_attempts: int = 5  # Lock account after this many failures
    lockout_duration_minutes: int = 15  # Account lockout duration
    password_min_length: int = 8
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_digit: bool = True
    password_require_special: bool = False

    # Redis settings (for session storage and caching)
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = False  # Set to True to use Redis for sessions
    redis_session_ttl: int = 86400  # 24 hours

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

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields in .env


settings = Settings()
