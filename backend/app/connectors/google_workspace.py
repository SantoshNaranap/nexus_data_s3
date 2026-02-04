"""
Google Workspace connector configuration.

Provides MCP tools for interacting with Google Workspace:
- Google Drive (files, docs, sheets)
- Gmail
- Google Calendar
- And more
"""

from typing import Dict, List, Optional, Any

from .base import BaseConnector, ConnectorMetadata, CredentialField


class GoogleWorkspaceConnector(BaseConnector):
    """Google Workspace connector configuration."""

    @property
    def metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            id="google_workspace",
            name="Google Workspace",
            description="Access Google Docs, Sheets, Drive, Gmail, Calendar, and more",
            icon="google_workspace",
        )

    @property
    def credential_fields(self) -> List[CredentialField]:
        return [
            CredentialField(
                name="google_oauth_client_id",
                env_var="GOOGLE_OAUTH_CLIENT_ID",
                display_name="OAuth Client ID",
                description="Google OAuth Client ID from Cloud Console",
                required=True,
            ),
            CredentialField(
                name="google_oauth_client_secret",
                env_var="GOOGLE_OAUTH_CLIENT_SECRET",
                display_name="OAuth Client Secret",
                description="Google OAuth Client Secret from Cloud Console",
                required=True,
            ),
            CredentialField(
                name="user_google_email",
                env_var="USER_GOOGLE_EMAIL",
                display_name="User Email",
                description="Google account email for single-user mode",
                required=False,
                sensitive=False,
            ),
        ]

    @property
    def server_script_path(self) -> str:
        return "../connectors/google_workspace/main.py"

    @property
    def server_args(self) -> List[str]:
        return ["--tool-tier", "core", "--single-user"]

    @property
    def additional_env(self) -> Dict[str, str]:
        return {
            "WORKSPACE_MCP_PORT": "8001",  # Use port 8001 to avoid conflict with FastAPI
            "OAUTHLIB_INSECURE_TRANSPORT": "1",  # For development
        }

    @property
    def cacheable_tools(self) -> List[str]:
        return [
            "get_events",
            "search_gmail_messages",
            "search_drive_files",
        ]

    @property
    def system_prompt_addition(self) -> str:
        # This is now minimal - main prompt is in prompts.py
        # Only include connector-specific runtime info here
        return ""

    def get_direct_routing(self, message: str) -> Optional[List[Dict[str, Any]]]:
        """Direct routing disabled - let Claude decide which tools to use."""
        # We removed keyword-based routing because:
        # 1. Claude is better at understanding user intent
        # 2. Simple keyword matching often misses context
        # 3. Claude can chain tools appropriately (search -> read)
        return None


# Export singleton instance
google_workspace_connector = GoogleWorkspaceConnector()
