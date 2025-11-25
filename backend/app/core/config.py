"""Application configuration."""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings."""

    # API Configuration
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    # Anthropic Claude
    anthropic_api_key: str

    # AWS S3
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-1"

    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = ""
    mysql_password: str = ""
    mysql_database: str = ""

    # JIRA
    jira_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""

    # Shopify
    shopify_shop_url: str = ""
    shopify_access_token: str = ""
    shopify_api_version: str = "2024-01"

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields in .env


settings = Settings()
