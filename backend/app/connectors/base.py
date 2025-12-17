"""
Base connector configuration class.

Each connector should inherit from this class and define its own:
- Metadata (name, description, icon)
- Credential fields and environment mappings
- System prompt additions
- Direct tool routing patterns
- Cacheable tools list
"""

import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class CredentialField:
    """Definition for a credential field."""
    name: str  # Internal field name (e.g., "slack_bot_token")
    env_var: str  # Environment variable name (e.g., "SLACK_BOT_TOKEN")
    display_name: str  # User-facing name (e.g., "Bot Token")
    description: str = ""
    required: bool = True
    sensitive: bool = True  # Should be masked in UI


@dataclass
class ConnectorMetadata:
    """Connector metadata for UI display."""
    id: str  # Unique identifier (e.g., "slack")
    name: str  # Display name (e.g., "Slack")
    description: str  # Short description
    icon: str = ""  # Icon identifier
    enabled: bool = True


class BaseConnector(ABC):
    """
    Base class for all connector configurations.

    To add a new connector:
    1. Create a new file in app/connectors/ (e.g., myconnector.py)
    2. Create a class that inherits from BaseConnector
    3. Implement all abstract properties and methods
    4. Register it in app/connectors/__init__.py

    Example:
        class MyConnector(BaseConnector):
            @property
            def metadata(self) -> ConnectorMetadata:
                return ConnectorMetadata(
                    id="myconnector",
                    name="My Connector",
                    description="Does cool stuff",
                )
            # ... implement other methods
    """

    @property
    @abstractmethod
    def metadata(self) -> ConnectorMetadata:
        """Return connector metadata for UI display."""
        pass

    @property
    @abstractmethod
    def credential_fields(self) -> List[CredentialField]:
        """
        Define credential fields this connector needs.

        Example:
            return [
                CredentialField(
                    name="api_key",
                    env_var="MY_API_KEY",
                    display_name="API Key",
                    description="Your API key from the dashboard",
                    required=True,
                ),
            ]
        """
        pass

    @property
    @abstractmethod
    def server_script_path(self) -> str:
        """
        Path to the MCP server script relative to project root.

        Example: "../connectors/slack/src/slack_server.py"
        """
        pass

    @property
    def server_args(self) -> List[str]:
        """
        Additional arguments to pass to the server script.
        Override if your connector needs special args.

        Example: ["--tool-tier", "core", "--single-user"]
        """
        return []

    @property
    def additional_env(self) -> Dict[str, str]:
        """
        Additional environment variables to set (beyond credentials).
        Override if your connector needs extra env vars.
        """
        return {}

    @property
    @abstractmethod
    def system_prompt_addition(self) -> str:
        """
        Additional system prompt guidance for Claude when using this connector.

        This should include:
        - Tool descriptions and when to use them
        - Required parameters for each tool
        - Common user request patterns and how to handle them
        - Any connector-specific gotchas
        """
        pass

    @property
    def cacheable_tools(self) -> List[str]:
        """
        List of tool names whose results can be cached.
        Only include read-only operations.

        Override to specify which tools can be cached.
        """
        return []

    @property
    def prewarm_on_startup(self) -> bool:
        """
        Whether to pre-warm this connector's connection on startup.
        Override to enable pre-warming for frequently used connectors.
        """
        return False

    def get_direct_routing(self, message: str) -> Optional[List[Dict[str, Any]]]:
        """
        Direct tool routing for common patterns.

        Override this method to provide instant tool routing for common queries.
        This bypasses the LLM routing layer for faster responses.

        Args:
            message: The user's message (lowercase)

        Returns:
            List of tool calls to make, or None if no direct routing applies.
            Each tool call is a dict with "tool" and "args" keys.

        Example:
            if "list channels" in message:
                return [{"tool": "list_channels", "args": {}}]
            return None
        """
        return None

    def get_env_from_credentials(self, credentials: Dict[str, str]) -> Dict[str, str]:
        """
        Convert user credentials dict to environment variables dict.

        Uses the credential_fields mapping to transform frontend field names
        to environment variable names.

        Args:
            credentials: Dict of credential values from the database

        Returns:
            Dict of environment variables to set
        """
        env = {}
        for field in self.credential_fields:
            if field.name in credentials and credentials[field.name]:
                env[field.env_var] = credentials[field.name]
        return env

    def get_env_from_oauth_tokens(self, tokens: Dict[str, Any]) -> Dict[str, str]:
        """
        Convert OAuth tokens dict to environment variables dict.

        Override this method for OAuth-enabled connectors to map
        access_token, refresh_token, etc. to the appropriate env vars.

        Args:
            tokens: Dict containing OAuth token data:
                - access_token: The OAuth access token
                - refresh_token: Optional refresh token
                - token_type: Token type (usually "Bearer")
                - expires_at: Token expiration datetime
                - scopes: List of granted scopes
                - provider_email: User's email on the provider

        Returns:
            Dict of environment variables to set
        """
        # Default implementation does nothing - override for OAuth connectors
        return {}

    def get_server_command(self) -> tuple:
        """
        Get the command and args to start the MCP server.

        Returns:
            Tuple of (command, args_list)
        """
        import sys
        python_cmd = sys.executable
        script_path = os.path.abspath(self.server_script_path)
        args = [script_path] + self.server_args
        return python_cmd, args

    def to_dict(self) -> Dict[str, Any]:
        """Convert connector metadata to dict for API responses."""
        meta = self.metadata
        return {
            "id": meta.id,
            "name": meta.name,
            "description": meta.description,
            "icon": meta.icon or meta.id,
            "enabled": meta.enabled,
        }

    def get_default_env_from_settings(self, settings: Any) -> Dict[str, str]:
        """
        Get default environment variables from application settings.

        This reads the default credential values from the settings object
        using the credential field names as attribute names.

        Args:
            settings: The application settings object

        Returns:
            Dict of environment variables with default values from settings
        """
        env = {}
        for field in self.credential_fields:
            # Get the value from settings using the field name
            value = getattr(settings, field.name, None)
            if value is not None:
                # Convert to string (handles port numbers, etc.)
                env[field.env_var] = str(value) if not isinstance(value, str) else value
        return env
