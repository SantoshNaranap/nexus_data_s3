"""
Slack connector configuration.

Provides MCP tools for interacting with Slack workspaces:
- Reading and searching messages
- Accessing channels and DMs
- User lookup
"""

from typing import Dict, List, Optional, Any

from .base import BaseConnector, ConnectorMetadata, CredentialField


class SlackConnector(BaseConnector):
    """Slack workspace connector configuration."""

    @property
    def metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            id="slack",
            name="Slack",
            description="Chat with your Slack workspace - read messages, search, send messages, and more",
            icon="slack",
        )

    @property
    def credential_fields(self) -> List[CredentialField]:
        return [
            CredentialField(
                name="slack_bot_token",
                env_var="SLACK_BOT_TOKEN",
                display_name="Bot Token",
                description="Bot token (xoxb-) for channels and public actions",
                required=True,
            ),
            CredentialField(
                name="slack_user_token",
                env_var="SLACK_USER_TOKEN",
                display_name="User Token",
                description="User token (xoxp-) for DMs and search - required for reading direct messages",
                required=False,
            ),
            CredentialField(
                name="slack_app_token",
                env_var="SLACK_APP_TOKEN",
                display_name="App Token",
                description="App token for Socket Mode (optional)",
                required=False,
            ),
        ]

    @property
    def server_script_path(self) -> str:
        return "../connectors/slack/src/slack_server.py"

    @property
    def cacheable_tools(self) -> List[str]:
        return [
            "list_channels",
            "get_channel_info",
            "read_messages",
            "search_messages",
            "list_users",
            "get_user_info",
            "get_user_presence",
            "get_thread_replies",
            "list_files",
            "read_dm_with_user",
            "get_user_messages_in_channel",
            "list_dms",
            "search_in_dms",
            "get_channel_activity",
            "get_all_recent_messages",
        ]

    @property
    def system_prompt_addition(self) -> str:
        # Main prompt is in prompts.py - keep this minimal
        return ""

    def get_direct_routing(self, message: str) -> Optional[List[Dict[str, Any]]]:
        """Direct routing disabled - let Claude decide which tools to use."""
        # We removed regex-based routing because:
        # 1. Claude is better at understanding user intent than regex patterns
        # 2. Complex regex often misses edge cases or matches incorrectly
        # 3. Claude can choose appropriate tools and parameters dynamically
        return None


# Export singleton instance
slack_connector = SlackConnector()
