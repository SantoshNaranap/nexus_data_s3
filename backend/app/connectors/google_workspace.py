"""
Google Workspace connector configuration.

Provides MCP tools for interacting with Google Workspace:
- Google Drive (files, docs, sheets)
- Gmail
- Google Calendar
- And more
"""

from typing import Dict, List, Optional, Any
import json

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
            "list_messages",
            "search_drive_files",
        ]

    @property
    def system_prompt_addition(self) -> str:
        # Get email from settings if available
        try:
            from app.core.config import settings
            email_info = f" (configured as: {settings.user_google_email})" if settings.user_google_email else ""
        except:
            email_info = ""

        return f"""
GOOGLE WORKSPACE TOOLS - COMPREHENSIVE GUIDE:

**User email is pre-configured{email_info}** - NEVER ask for email, just call tools!

**PRIMARY TOOLS:**
- `get_events(time_min, time_max)` - Get calendar events. Works for today, this week, etc.
- `list_messages(query, max_results)` - List/search Gmail messages
- `get_message(message_id)` - Read full email content
- `search_drive_files(query)` - Search Google Drive files
- `get_file(file_id)` - Get file details/content

**CRITICAL RULES - NEVER VIOLATE:**
1. NEVER ask for the user's email - it's pre-configured
2. NEVER say "I don't have access" without calling a tool first
3. ALWAYS call tools directly when user asks about their Google data
4. ALWAYS show the actual data returned - don't summarize away content
5. If OAuth is needed, the tool will tell you - don't preemptively refuse

**WORKFLOW EXAMPLES:**

"What's on my calendar?" or "My meetings today":
→ get_events() with appropriate time range
→ Display ALL events with times and details

"Show my emails" or "Recent messages":
→ list_messages(max_results=20)
→ Display subjects, senders, and dates

"Find email about [topic]":
→ list_messages(query="[topic]")
→ Show matching messages

"Show my Drive files" or "What documents do I have?":
→ search_drive_files()
→ Display ALL files with names and types

"Find [document name]":
→ search_drive_files(query="[document name]")
→ Display matching files

"Read email from [person]":
→ list_messages(query="from:[person]")
→ Then get_message() for full content

**CALENDAR QUERIES:**
- "Today's meetings" → get_events with today's date range
- "This week" → get_events with week date range
- "Tomorrow" → get_events with tomorrow's date range

**NEVER DO THIS:**
- Don't ask for email address - use the configured one
- Don't say "need authorization" without trying the tool first
- Don't refuse to access data - the user authorized this connector
- Don't summarize emails to "you have 5 emails" - show the actual subjects
"""

    def get_direct_routing(self, message: str) -> Optional[List[Dict[str, Any]]]:
        """Direct routing for simple Google Workspace queries only.

        For queries that need search terms (like 'find documents about X'),
        we return None to let Claude extract and pass the proper query parameters.
        """
        message_lower = message.lower().strip()

        # Only route very simple calendar queries - let Claude handle specific searches
        if message_lower in ["what's on my calendar today", "my calendar today", "calendar today",
                             "today's meetings", "meetings today", "my meetings"]:
            return [{"tool": "get_events", "args": {}}]

        # All other queries (email searches, drive searches, etc.) should go through Claude
        # so it can extract the proper search terms
        return None

    def get_env_from_oauth_tokens(self, tokens: Dict[str, Any]) -> Dict[str, str]:
        """
        Convert OAuth tokens to environment variables for Google Workspace.

        The Google Workspace MCP server expects these environment variables
        for OAuth authentication.

        Args:
            tokens: Dict containing:
                - access_token: Google OAuth access token
                - refresh_token: Google OAuth refresh token
                - provider_email: User's Google email
                - scopes: List of granted OAuth scopes

        Returns:
            Dict of environment variables for the MCP server
        """
        env = {}

        # Pass OAuth tokens to the MCP server
        if tokens.get("access_token"):
            env["GOOGLE_ACCESS_TOKEN"] = tokens["access_token"]

        if tokens.get("refresh_token"):
            env["GOOGLE_REFRESH_TOKEN"] = tokens["refresh_token"]

        if tokens.get("provider_email"):
            env["USER_GOOGLE_EMAIL"] = tokens["provider_email"]

        # Pass scopes as JSON array
        if tokens.get("scopes"):
            scopes = tokens["scopes"]
            if isinstance(scopes, list):
                env["GOOGLE_OAUTH_SCOPES"] = json.dumps(scopes)
            elif isinstance(scopes, str):
                env["GOOGLE_OAUTH_SCOPES"] = scopes

        # Also pass client credentials (needed for token refresh)
        try:
            from app.core.config import settings
            if settings.google_oauth_client_id:
                env["GOOGLE_OAUTH_CLIENT_ID"] = settings.google_oauth_client_id
            if settings.google_oauth_client_secret:
                env["GOOGLE_OAUTH_CLIENT_SECRET"] = settings.google_oauth_client_secret
        except ImportError:
            pass

        return env


# Export singleton instance
google_workspace_connector = GoogleWorkspaceConnector()
