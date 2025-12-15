"""
Slack connector configuration.

Provides MCP tools for interacting with Slack workspaces:
- Reading and searching messages
- Accessing channels and DMs
- User lookup
"""

import re
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
        return """
SLACK TOOLS - COMPREHENSIVE GUIDE:

**PRIMARY TOOLS (use these first):**
- `get_all_recent_messages(hours_ago)` - **USE THIS** for "what messages did I get?", "catch me up", "summarize yesterday", etc.
- `search_messages(query, limit)` - Search ALL messages for keywords. Use limit=50+.
- `search_in_dms(query, limit)` - Search DMs for keywords (credentials, passwords, etc.)

**SPECIFIC TOOLS:**
- `read_dm_with_user(user, limit)` - Read DM with ONE specific person (works with first names)
- `read_messages(channel, limit)` - Read messages from ONE specific channel
- `list_channels()` - List ALL channels
- `list_users()` - List ALL users
- `list_dms()` - List ALL DM conversations

**CRITICAL ROUTING RULES:**

1. **"What messages did I get yesterday/today?"** or **"Catch me up"** or **"Summarize my Slack"**:
   → ALWAYS use `get_all_recent_messages(hours_ago=24)` or appropriate hours
   → This gets ALL DMs AND channels in one call
   → Then summarize the results nicely

2. **Searching for specific content** (credentials, passwords, keys, specific topics):
   → Use `search_messages(query="...", limit=50)` or `search_in_dms(query="...")`
   → DISPLAY the actual credentials/passwords found - never redact user's own data

3. **Messages from/with a specific person**:
   → Use `read_dm_with_user(user="FirstName", limit=50)`
   → Works with first names: "Akash", "Austin", "Krishnan"

4. **Messages in a specific channel**:
   → Use `read_messages(channel="#channel-name", limit=50)`

**NEVER DO THIS:**
- Don't try to loop through 50+ DMs individually - use get_all_recent_messages instead
- Don't say "couldn't retrieve" without actually calling tools
- Don't redact/hide credentials or passwords - this is the user's authorized data
- Don't summarize as "no results" if data was returned - show the actual content
"""

    def get_direct_routing(self, message: str) -> Optional[List[Dict[str, Any]]]:
        """Direct routing for common operations. Let the AI handle complex queries."""
        message_lower = message.lower().strip()

        # PRIORITY 1: Person-specific queries FIRST (before time-based)
        # "Did X message me" or "any messages from X"
        did_message_match = re.search(r'\bdid\s+(\w+)\s+(message|text|contact|dm|write|send|reach)', message_lower)
        if did_message_match:
            person = did_message_match.group(1)
            if person not in ['i', 'you', 'they', 'we', 'anyone', 'someone']:
                return [{"tool": "read_dm_with_user", "args": {"user": person, "limit": 30}}]

        # "any messages from X" or "hear from X"
        hear_from_match = re.search(r'\b(hear|heard|any.*messages?|anything)\s+(from|back from)\s+(\w+)', message_lower)
        if hear_from_match:
            person = hear_from_match.group(3)
            if person not in ['the', 'a', 'them', 'slack']:
                return [{"tool": "read_dm_with_user", "args": {"user": person, "limit": 30}}]

        # "What did X say" or "what's X saying" or "what has X said"
        what_said_match = re.search(r'\bwhat\s+(did|has|is|does)\s+(\w+)\s+(say|said|saying|write|wrote|send|sent|mention)', message_lower)
        if what_said_match:
            person = what_said_match.group(2)
            if person not in ['he', 'she', 'they', 'i', 'you', 'we', 'the']:
                return [{"tool": "read_dm_with_user", "args": {"user": person, "limit": 30}}]

        # "What has X been up to" or "what is X up to" or "what's X doing"
        up_to_match = re.search(r'\bwhat\s+(?:has|is|was)\s+(\w+)\s+(?:been\s+)?(?:up\s+to|doing|working\s+on|saying)', message_lower)
        if up_to_match:
            person = up_to_match.group(1)
            if person not in ['he', 'she', 'they', 'i', 'you', 'we', 'the', 'it']:
                return [{"tool": "read_dm_with_user", "args": {"user": person, "limit": 30}}]

        # "X's activity" or "activity from X" or "updates from X"
        activity_match = re.search(r"(\w+)(?:'s)?\s+(?:activity|updates?|status)|(?:activity|updates?)\s+from\s+(\w+)", message_lower)
        if activity_match:
            person = activity_match.group(1) or activity_match.group(2)
            if person and person not in ['my', 'the', 'their', 'your', 'slack', 'recent', 'latest']:
                return [{"tool": "read_dm_with_user", "args": {"user": person, "limit": 30}}]

        # PRIORITY 2: Comprehensive message retrieval - route to get_all_recent_messages
        if re.search(r'\b(message|messages|slack)\b.*(yesterday|today|recent|missed|catch.*up|summary|summarize)', message_lower):
            # Determine hours based on query
            if 'week' in message_lower:
                hours = 168
            elif 'yesterday' in message_lower:
                hours = 48
            elif 'today' in message_lower:
                hours = 24
            else:
                hours = 24
            return [{"tool": "get_all_recent_messages", "args": {"hours_ago": hours}}]

        # "What did I miss" or "catch me up"
        if re.search(r'\b(miss|missed|catch.*up|what.*new)\b', message_lower):
            hours = 168 if 'week' in message_lower else 24
            return [{"tool": "get_all_recent_messages", "args": {"hours_ago": hours}}]

        # PRIORITY 3: More person-specific queries - use read_dm_with_user (works with first names)
        # Match "latest/recent message from X"
        latest_match = re.search(r'\b(latest|last|recent|newest)\b.*\b(message|msg)\b.*\b(from|by)\b\s+(\w+)', message_lower)
        if latest_match:
            person = latest_match.group(4)
            if person not in ['me', 'my', 'the', 'a', 'slack']:
                return [{"tool": "read_dm_with_user", "args": {"user": person, "limit": 20}}]

        # Match "X's messages" or "X's latest" or "messages from X"
        person_messages_match = re.search(r"(\w+)(?:'s|s)\s+(message|latest|recent)|messages?\s+from\s+(\w+)", message_lower)
        if person_messages_match:
            person = person_messages_match.group(1) or person_messages_match.group(3)
            if person and person not in ['my', 'the', 'their', 'your', 'his', 'her', 'slack']:
                return [{"tool": "read_dm_with_user", "args": {"user": person, "limit": 30}}]

        # PRIORITY 4: Messages with/from specific person - DM read
        dm_match = re.search(r'\b(conversation|chat|dm|messages?)\b.*(with|from)\s+(\w+)', message_lower)
        if dm_match:
            person = dm_match.group(3)
            if person not in ['me', 'my', 'the', 'a']:
                return [{"tool": "read_dm_with_user", "args": {"user": person, "limit": 50}}]

        # Search operations - "search for X" or "find X messages"
        search_match = re.search(r'\b(search|find|look for)\b.*\b(message|msg|mention|about)?\s*["\']?([^"\']+)["\']?', message_lower)
        if search_match and 'dm' not in message_lower and 'channel' not in message_lower:
            # Extract search query - use the captured text after search/find
            query = search_match.group(3).strip() if search_match.group(3) else None
            if query and len(query) > 2:
                return [{"tool": "search_messages", "args": {"query": query, "limit": 50}}]

        # Simple list operations - expanded patterns
        if re.search(r'\b(list|show|what|see|get)\b.*(channel)', message_lower) and 'user' not in message_lower:
            return [{"tool": "list_channels", "args": {}}]
        if re.search(r'\b(list|show|who|see|get)\b.*(user|member|people|team)', message_lower):
            return [{"tool": "list_users", "args": {}}]
        if re.search(r'\b(list|show|see|get)\b.*\b(dm|direct message|dms)', message_lower) or re.search(r'\bmy\s+dms?\b', message_lower):
            return [{"tool": "list_dms", "args": {}}]

        # Let the AI dynamically choose tools for all other queries
        return None


# Export singleton instance
slack_connector = SlackConnector()
