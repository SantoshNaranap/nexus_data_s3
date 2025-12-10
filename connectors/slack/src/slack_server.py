#!/usr/bin/env python3
"""
Slack MCP Server

Provides MCP tools for interacting with Slack workspaces, channels, and messages.
Uses the Slack Web API via slack_sdk.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from mcp.server import Server
from mcp.types import Tool, TextContent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("slack-mcp-server")

# Initialize Slack client
slack_token = os.getenv("SLACK_BOT_TOKEN", "")
slack_client = WebClient(token=slack_token)

# Create MCP server
app = Server("slack-connector")

# Cache for channel/user lookups
_channel_cache: dict = {}
_user_cache: dict = {}


def _get_channel_id(channel_name: str) -> Optional[str]:
    """Get channel ID from name, with caching."""
    if channel_name.startswith("C") or channel_name.startswith("D"):
        return channel_name  # Already an ID

    # Remove # prefix if present
    channel_name = channel_name.lstrip("#")

    # Check cache
    if channel_name in _channel_cache:
        return _channel_cache[channel_name]

    try:
        # Search in public channels
        result = slack_client.conversations_list(types="public_channel,private_channel")
        for channel in result["channels"]:
            _channel_cache[channel["name"]] = channel["id"]
            if channel["name"] == channel_name:
                return channel["id"]
    except SlackApiError as e:
        logger.error(f"Error looking up channel: {e}")

    return None


def _get_user_id(user_identifier: str) -> Optional[str]:
    """Get user ID from name/email, with caching."""
    if user_identifier.startswith("U"):
        return user_identifier  # Already an ID

    # Remove @ prefix if present
    user_identifier = user_identifier.lstrip("@")

    # Check cache
    if user_identifier in _user_cache:
        return _user_cache[user_identifier]

    try:
        result = slack_client.users_list()
        for user in result["members"]:
            _user_cache[user["name"]] = user["id"]
            if user.get("profile", {}).get("email"):
                _user_cache[user["profile"]["email"]] = user["id"]
            if user.get("real_name"):
                _user_cache[user["real_name"].lower()] = user["id"]

            if user["name"] == user_identifier or \
               user.get("profile", {}).get("email") == user_identifier or \
               user.get("real_name", "").lower() == user_identifier.lower():
                return user["id"]
    except SlackApiError as e:
        logger.error(f"Error looking up user: {e}")

    return None


def _format_timestamp(ts: str) -> str:
    """Convert Slack timestamp to readable format."""
    try:
        dt = datetime.fromtimestamp(float(ts))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return ts


def _get_user_name(user_id: str) -> str:
    """Get user display name from ID."""
    try:
        result = slack_client.users_info(user=user_id)
        user = result["user"]
        return user.get("real_name") or user.get("name") or user_id
    except SlackApiError:
        return user_id


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available Slack tools."""
    return [
        # Channel tools
        Tool(
            name="list_channels",
            description="""List all Slack channels in the workspace.

Returns public and private channels the bot has access to.
Use this to discover available channels before reading/posting messages.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_private": {
                        "type": "boolean",
                        "description": "Include private channels (default: true)",
                        "default": True,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max channels to return (default: 100)",
                        "default": 100,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_channel_info",
            description="""Get detailed information about a specific channel.

Includes member count, topic, purpose, and creation date.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name (e.g., 'general') or ID",
                    },
                },
                "required": ["channel"],
            },
        ),

        # Message tools
        Tool(
            name="read_messages",
            description="""Read recent messages from a Slack channel.

Returns the latest messages with sender info and timestamps.
Great for catching up on channel activity or finding specific discussions.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name (e.g., 'general') or ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of messages to retrieve (default: 20, max: 100)",
                        "default": 20,
                    },
                },
                "required": ["channel"],
            },
        ),
        Tool(
            name="search_messages",
            description="""Search for messages across Slack.

Search by keywords, in specific channels, from specific users, or within date ranges.
Returns matching messages with context.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (supports Slack search modifiers like 'from:@user', 'in:#channel')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default: 20)",
                        "default": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="send_message",
            description="""Send a message to a Slack channel.

Supports plain text and basic formatting (bold, italic, code blocks).
Can also reply to threads.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name (e.g., 'general') or ID",
                    },
                    "text": {
                        "type": "string",
                        "description": "Message text (supports Slack markdown)",
                    },
                    "thread_ts": {
                        "type": "string",
                        "description": "Optional: Thread timestamp to reply to",
                    },
                },
                "required": ["channel", "text"],
            },
        ),
        Tool(
            name="send_dm",
            description="""Send a direct message to a user.

Opens a DM conversation if one doesn't exist.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "user": {
                        "type": "string",
                        "description": "User name, email, or ID",
                    },
                    "text": {
                        "type": "string",
                        "description": "Message text",
                    },
                },
                "required": ["user", "text"],
            },
        ),

        # User tools
        Tool(
            name="list_users",
            description="""List all users in the Slack workspace.

Returns user names, emails, and status information.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max users to return (default: 100)",
                        "default": 100,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_user_info",
            description="""Get detailed information about a specific user.

Includes profile, status, timezone, and contact info.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "user": {
                        "type": "string",
                        "description": "User name, email, or ID",
                    },
                },
                "required": ["user"],
            },
        ),
        Tool(
            name="get_user_presence",
            description="""Check if a user is online/away.

Shows current presence status and last activity.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "user": {
                        "type": "string",
                        "description": "User name, email, or ID",
                    },
                },
                "required": ["user"],
            },
        ),

        # Thread tools
        Tool(
            name="get_thread_replies",
            description="""Get all replies in a message thread.

Use this to read full conversation threads.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name or ID where the thread is",
                    },
                    "thread_ts": {
                        "type": "string",
                        "description": "Timestamp of the parent message",
                    },
                },
                "required": ["channel", "thread_ts"],
            },
        ),

        # Reaction tools
        Tool(
            name="add_reaction",
            description="""Add an emoji reaction to a message.

Use standard emoji names without colons (e.g., 'thumbsup', 'heart').""",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name or ID",
                    },
                    "timestamp": {
                        "type": "string",
                        "description": "Message timestamp to react to",
                    },
                    "emoji": {
                        "type": "string",
                        "description": "Emoji name (e.g., 'thumbsup', 'heart', 'eyes')",
                    },
                },
                "required": ["channel", "timestamp", "emoji"],
            },
        ),

        # File tools
        Tool(
            name="list_files",
            description="""List files shared in the workspace.

Filter by channel, user, or file type.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Optional: Filter by channel",
                    },
                    "user": {
                        "type": "string",
                        "description": "Optional: Filter by user who shared",
                    },
                    "types": {
                        "type": "string",
                        "description": "Optional: File types (e.g., 'images', 'pdfs', 'docs')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max files to return (default: 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
        ),

        # DM/Conversation tools
        Tool(
            name="read_dm_with_user",
            description="""Read direct message conversation with a specific user.

Use this to:
- Get conversation history between you and another person
- Summarize discussions with a colleague
- Find messages exchanged with someone

Supports date filtering to narrow down to specific time periods.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "user": {
                        "type": "string",
                        "description": "User name, real name, email, or ID to get DM history with",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of messages to retrieve (default: 50, max: 200)",
                        "default": 50,
                    },
                    "days_ago": {
                        "type": "integer",
                        "description": "Only get messages from the last N days (default: all)",
                    },
                    "since_date": {
                        "type": "string",
                        "description": "Get messages since this date (YYYY-MM-DD format)",
                    },
                },
                "required": ["user"],
            },
        ),
        Tool(
            name="get_user_messages_in_channel",
            description="""Get all messages from a specific user in a channel.

Use this to:
- See what someone has said in a channel
- Track a person's contributions to a discussion
- Find messages from a specific colleague

Supports date filtering.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name or ID",
                    },
                    "user": {
                        "type": "string",
                        "description": "User name, real name, email, or ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max messages to scan (default: 100, max: 500)",
                        "default": 100,
                    },
                    "days_ago": {
                        "type": "integer",
                        "description": "Only get messages from the last N days",
                    },
                },
                "required": ["channel", "user"],
            },
        ),
        Tool(
            name="list_dms",
            description="""List all direct message conversations.

Returns a list of all DM channels with the user you're chatting with.
Useful for discovering who you've been messaging.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max DMs to return (default: 50)",
                        "default": 50,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="search_in_dms",
            description="""Search for specific content across all your direct messages.

Use this to:
- Find credentials, passwords, or API keys someone sent you
- Search for specific information shared privately
- Find links or files shared in DMs

Searches across ALL your DM conversations.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'mysql password', 'API key', 'credentials')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default: 30)",
                        "default": 30,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_channel_activity",
            description="""Get a summary of recent activity in a channel.

Use this to quickly understand what's been happening in a channel.
Returns message count, active users, and key discussion topics.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name or ID",
                    },
                    "days_ago": {
                        "type": "integer",
                        "description": "Look at activity from the last N days (default: 7)",
                        "default": 7,
                    },
                },
                "required": ["channel"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "list_channels":
            return await handle_list_channels(arguments)
        elif name == "get_channel_info":
            return await handle_get_channel_info(arguments)
        elif name == "read_messages":
            return await handle_read_messages(arguments)
        elif name == "search_messages":
            return await handle_search_messages(arguments)
        elif name == "send_message":
            return await handle_send_message(arguments)
        elif name == "send_dm":
            return await handle_send_dm(arguments)
        elif name == "list_users":
            return await handle_list_users(arguments)
        elif name == "get_user_info":
            return await handle_get_user_info(arguments)
        elif name == "get_user_presence":
            return await handle_get_user_presence(arguments)
        elif name == "get_thread_replies":
            return await handle_get_thread_replies(arguments)
        elif name == "add_reaction":
            return await handle_add_reaction(arguments)
        elif name == "list_files":
            return await handle_list_files(arguments)
        # New DM/conversation tools
        elif name == "read_dm_with_user":
            return await handle_read_dm_with_user(arguments)
        elif name == "get_user_messages_in_channel":
            return await handle_get_user_messages_in_channel(arguments)
        elif name == "list_dms":
            return await handle_list_dms(arguments)
        elif name == "search_in_dms":
            return await handle_search_in_dms(arguments)
        elif name == "get_channel_activity":
            return await handle_get_channel_activity(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except SlackApiError as e:
        logger.error(f"Slack API error in {name}: {str(e)}")
        return [TextContent(type="text", text=f"Slack API Error: {e.response['error']}")]
    except Exception as e:
        logger.error(f"Unexpected error in {name}: {str(e)}")
        return [TextContent(type="text", text=f"Unexpected error: {str(e)}")]


# ==================== Channel Handlers ====================

async def handle_list_channels(arguments: dict) -> list[TextContent]:
    """List all channels."""
    include_private = arguments.get("include_private", True)
    limit = arguments.get("limit", 100)

    types = "public_channel"
    if include_private:
        types += ",private_channel"

    result = slack_client.conversations_list(types=types, limit=limit)

    channels = []
    for channel in result["channels"]:
        channels.append({
            "id": channel["id"],
            "name": channel["name"],
            "is_private": channel.get("is_private", False),
            "num_members": channel.get("num_members", 0),
            "topic": channel.get("topic", {}).get("value", ""),
            "purpose": channel.get("purpose", {}).get("value", ""),
        })

    response = {
        "count": len(channels),
        "channels": channels,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_get_channel_info(arguments: dict) -> list[TextContent]:
    """Get channel details."""
    channel = arguments["channel"]
    channel_id = _get_channel_id(channel)

    if not channel_id:
        return [TextContent(type="text", text=f"Channel not found: {channel}")]

    result = slack_client.conversations_info(channel=channel_id)
    ch = result["channel"]

    response = {
        "id": ch["id"],
        "name": ch["name"],
        "is_private": ch.get("is_private", False),
        "is_archived": ch.get("is_archived", False),
        "num_members": ch.get("num_members", 0),
        "topic": ch.get("topic", {}).get("value", ""),
        "purpose": ch.get("purpose", {}).get("value", ""),
        "created": _format_timestamp(str(ch.get("created", ""))),
        "creator": _get_user_name(ch.get("creator", "")),
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


# ==================== Message Handlers ====================

async def handle_read_messages(arguments: dict) -> list[TextContent]:
    """Read messages from a channel."""
    channel = arguments["channel"]
    limit = min(arguments.get("limit", 20), 100)

    channel_id = _get_channel_id(channel)
    if not channel_id:
        return [TextContent(type="text", text=f"Channel not found: {channel}")]

    result = slack_client.conversations_history(channel=channel_id, limit=limit)

    messages = []
    for msg in result["messages"]:
        user_name = _get_user_name(msg.get("user", "unknown"))
        messages.append({
            "timestamp": msg["ts"],
            "time": _format_timestamp(msg["ts"]),
            "user": user_name,
            "text": msg.get("text", ""),
            "has_thread": msg.get("reply_count", 0) > 0,
            "reply_count": msg.get("reply_count", 0),
            "reactions": [
                {"emoji": r["name"], "count": r["count"]}
                for r in msg.get("reactions", [])
            ],
        })

    response = {
        "channel": channel,
        "count": len(messages),
        "messages": messages,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_search_messages(arguments: dict) -> list[TextContent]:
    """Search messages."""
    query = arguments["query"]
    limit = arguments.get("limit", 20)

    result = slack_client.search_messages(query=query, count=limit)

    messages = []
    for match in result["messages"]["matches"]:
        messages.append({
            "channel": match.get("channel", {}).get("name", ""),
            "timestamp": match["ts"],
            "time": _format_timestamp(match["ts"]),
            "user": match.get("username", ""),
            "text": match.get("text", ""),
            "permalink": match.get("permalink", ""),
        })

    response = {
        "query": query,
        "total": result["messages"]["total"],
        "count": len(messages),
        "messages": messages,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_send_message(arguments: dict) -> list[TextContent]:
    """Send a message to a channel."""
    channel = arguments["channel"]
    text = arguments["text"]
    thread_ts = arguments.get("thread_ts")

    channel_id = _get_channel_id(channel)
    if not channel_id:
        return [TextContent(type="text", text=f"Channel not found: {channel}")]

    kwargs = {"channel": channel_id, "text": text}
    if thread_ts:
        kwargs["thread_ts"] = thread_ts

    result = slack_client.chat_postMessage(**kwargs)

    response = {
        "status": "sent",
        "channel": channel,
        "timestamp": result["ts"],
        "message": text[:100] + "..." if len(text) > 100 else text,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_send_dm(arguments: dict) -> list[TextContent]:
    """Send a direct message."""
    user = arguments["user"]
    text = arguments["text"]

    user_id = _get_user_id(user)
    if not user_id:
        return [TextContent(type="text", text=f"User not found: {user}")]

    # Open DM conversation
    dm_result = slack_client.conversations_open(users=[user_id])
    dm_channel = dm_result["channel"]["id"]

    # Send message
    result = slack_client.chat_postMessage(channel=dm_channel, text=text)

    response = {
        "status": "sent",
        "user": user,
        "timestamp": result["ts"],
        "message": text[:100] + "..." if len(text) > 100 else text,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


# ==================== User Handlers ====================

async def handle_list_users(arguments: dict) -> list[TextContent]:
    """List all users."""
    limit = arguments.get("limit", 100)

    result = slack_client.users_list(limit=limit)

    users = []
    for user in result["members"]:
        if user.get("deleted") or user.get("is_bot"):
            continue

        profile = user.get("profile", {})
        users.append({
            "id": user["id"],
            "name": user["name"],
            "real_name": user.get("real_name", ""),
            "email": profile.get("email", ""),
            "title": profile.get("title", ""),
            "status_text": profile.get("status_text", ""),
            "status_emoji": profile.get("status_emoji", ""),
            "is_admin": user.get("is_admin", False),
        })

    response = {
        "count": len(users),
        "users": users,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_get_user_info(arguments: dict) -> list[TextContent]:
    """Get user details."""
    user = arguments["user"]
    user_id = _get_user_id(user)

    if not user_id:
        return [TextContent(type="text", text=f"User not found: {user}")]

    result = slack_client.users_info(user=user_id)
    u = result["user"]
    profile = u.get("profile", {})

    response = {
        "id": u["id"],
        "name": u["name"],
        "real_name": u.get("real_name", ""),
        "email": profile.get("email", ""),
        "title": profile.get("title", ""),
        "phone": profile.get("phone", ""),
        "status_text": profile.get("status_text", ""),
        "status_emoji": profile.get("status_emoji", ""),
        "timezone": u.get("tz", ""),
        "is_admin": u.get("is_admin", False),
        "is_owner": u.get("is_owner", False),
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_get_user_presence(arguments: dict) -> list[TextContent]:
    """Get user presence status."""
    user = arguments["user"]
    user_id = _get_user_id(user)

    if not user_id:
        return [TextContent(type="text", text=f"User not found: {user}")]

    result = slack_client.users_getPresence(user=user_id)

    response = {
        "user": user,
        "presence": result["presence"],
        "online": result["presence"] == "active",
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


# ==================== Thread Handlers ====================

async def handle_get_thread_replies(arguments: dict) -> list[TextContent]:
    """Get thread replies."""
    channel = arguments["channel"]
    thread_ts = arguments["thread_ts"]

    channel_id = _get_channel_id(channel)
    if not channel_id:
        return [TextContent(type="text", text=f"Channel not found: {channel}")]

    result = slack_client.conversations_replies(channel=channel_id, ts=thread_ts)

    messages = []
    for msg in result["messages"]:
        user_name = _get_user_name(msg.get("user", "unknown"))
        messages.append({
            "timestamp": msg["ts"],
            "time": _format_timestamp(msg["ts"]),
            "user": user_name,
            "text": msg.get("text", ""),
            "is_parent": msg["ts"] == thread_ts,
        })

    response = {
        "channel": channel,
        "thread_ts": thread_ts,
        "reply_count": len(messages) - 1,  # Exclude parent
        "messages": messages,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


# ==================== Reaction Handlers ====================

async def handle_add_reaction(arguments: dict) -> list[TextContent]:
    """Add emoji reaction to a message."""
    channel = arguments["channel"]
    timestamp = arguments["timestamp"]
    emoji = arguments["emoji"].strip(":")  # Remove colons if present

    channel_id = _get_channel_id(channel)
    if not channel_id:
        return [TextContent(type="text", text=f"Channel not found: {channel}")]

    slack_client.reactions_add(channel=channel_id, timestamp=timestamp, name=emoji)

    response = {
        "status": "added",
        "emoji": emoji,
        "channel": channel,
        "timestamp": timestamp,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


# ==================== File Handlers ====================

async def handle_list_files(arguments: dict) -> list[TextContent]:
    """List files in workspace."""
    channel = arguments.get("channel")
    user = arguments.get("user")
    types = arguments.get("types")
    limit = arguments.get("limit", 20)

    kwargs = {"count": limit}

    if channel:
        channel_id = _get_channel_id(channel)
        if channel_id:
            kwargs["channel"] = channel_id

    if user:
        user_id = _get_user_id(user)
        if user_id:
            kwargs["user"] = user_id

    if types:
        kwargs["types"] = types

    result = slack_client.files_list(**kwargs)

    files = []
    for f in result["files"]:
        files.append({
            "id": f["id"],
            "name": f["name"],
            "title": f.get("title", ""),
            "type": f.get("filetype", ""),
            "size": f.get("size", 0),
            "created": _format_timestamp(str(f.get("created", ""))),
            "user": _get_user_name(f.get("user", "")),
            "url": f.get("url_private", ""),
        })

    response = {
        "count": len(files),
        "files": files,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


# ==================== DM/Conversation Handlers ====================

def _parse_date_filter(days_ago: Optional[int] = None, since_date: Optional[str] = None) -> Optional[str]:
    """Convert date filters to Slack timestamp."""
    if days_ago:
        cutoff = datetime.now() - timedelta(days=days_ago)
        return str(cutoff.timestamp())
    elif since_date:
        try:
            cutoff = datetime.strptime(since_date, "%Y-%m-%d")
            return str(cutoff.timestamp())
        except ValueError:
            return None
    return None


async def handle_read_dm_with_user(arguments: dict) -> list[TextContent]:
    """Read DM conversation with a specific user."""
    user = arguments["user"]
    limit = min(arguments.get("limit", 50), 200)
    days_ago = arguments.get("days_ago")
    since_date = arguments.get("since_date")

    user_id = _get_user_id(user)
    if not user_id:
        return [TextContent(type="text", text=f"User not found: {user}")]

    # Open/get DM channel with user
    try:
        dm_result = slack_client.conversations_open(users=[user_id])
        dm_channel = dm_result["channel"]["id"]
    except SlackApiError as e:
        return [TextContent(type="text", text=f"Could not open DM with {user}: {e.response['error']}")]

    # Build history query
    kwargs = {"channel": dm_channel, "limit": limit}
    oldest = _parse_date_filter(days_ago, since_date)
    if oldest:
        kwargs["oldest"] = oldest

    result = slack_client.conversations_history(**kwargs)

    messages = []
    for msg in result["messages"]:
        sender_name = _get_user_name(msg.get("user", "unknown"))
        messages.append({
            "timestamp": msg["ts"],
            "time": _format_timestamp(msg["ts"]),
            "user": sender_name,
            "text": msg.get("text", ""),
            "has_thread": msg.get("reply_count", 0) > 0,
        })

    # Get user's real name for response
    user_name = _get_user_name(user_id)

    response = {
        "dm_with": user_name,
        "count": len(messages),
        "date_filter": f"Last {days_ago} days" if days_ago else (f"Since {since_date}" if since_date else "All time"),
        "messages": messages,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_get_user_messages_in_channel(arguments: dict) -> list[TextContent]:
    """Get messages from a specific user in a channel."""
    channel = arguments["channel"]
    user = arguments["user"]
    limit = min(arguments.get("limit", 100), 500)
    days_ago = arguments.get("days_ago")

    channel_id = _get_channel_id(channel)
    if not channel_id:
        return [TextContent(type="text", text=f"Channel not found: {channel}")]

    user_id = _get_user_id(user)
    if not user_id:
        return [TextContent(type="text", text=f"User not found: {user}")]

    # Build history query
    kwargs = {"channel": channel_id, "limit": limit}
    oldest = _parse_date_filter(days_ago)
    if oldest:
        kwargs["oldest"] = oldest

    result = slack_client.conversations_history(**kwargs)

    # Filter messages by user
    user_messages = []
    for msg in result["messages"]:
        if msg.get("user") == user_id:
            user_messages.append({
                "timestamp": msg["ts"],
                "time": _format_timestamp(msg["ts"]),
                "text": msg.get("text", ""),
                "has_thread": msg.get("reply_count", 0) > 0,
                "reactions": [
                    {"emoji": r["name"], "count": r["count"]}
                    for r in msg.get("reactions", [])
                ],
            })

    user_name = _get_user_name(user_id)

    response = {
        "channel": channel,
        "user": user_name,
        "count": len(user_messages),
        "scanned": len(result["messages"]),
        "date_filter": f"Last {days_ago} days" if days_ago else "All available",
        "messages": user_messages,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_list_dms(arguments: dict) -> list[TextContent]:
    """List all DM conversations."""
    limit = arguments.get("limit", 50)

    result = slack_client.conversations_list(types="im", limit=limit)

    dms = []
    for dm in result["channels"]:
        user_id = dm.get("user")
        if user_id:
            user_name = _get_user_name(user_id)
            dms.append({
                "channel_id": dm["id"],
                "user_id": user_id,
                "user_name": user_name,
                "is_open": dm.get("is_open", False),
            })

    response = {
        "count": len(dms),
        "dms": dms,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_search_in_dms(arguments: dict) -> list[TextContent]:
    """Search for content across DMs."""
    query = arguments["query"]
    limit = arguments.get("limit", 30)

    # Use Slack search with "is:dm" modifier to search only DMs
    search_query = f"{query} is:dm"
    result = slack_client.search_messages(query=search_query, count=limit)

    messages = []
    for match in result["messages"]["matches"]:
        messages.append({
            "channel": match.get("channel", {}).get("name", "DM"),
            "from_user": match.get("username", ""),
            "timestamp": match["ts"],
            "time": _format_timestamp(match["ts"]),
            "text": match.get("text", ""),
            "permalink": match.get("permalink", ""),
        })

    response = {
        "query": query,
        "total_matches": result["messages"]["total"],
        "count": len(messages),
        "messages": messages,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_get_channel_activity(arguments: dict) -> list[TextContent]:
    """Get activity summary for a channel."""
    channel = arguments["channel"]
    days_ago = arguments.get("days_ago", 7)

    channel_id = _get_channel_id(channel)
    if not channel_id:
        return [TextContent(type="text", text=f"Channel not found: {channel}")]

    oldest = _parse_date_filter(days_ago)
    kwargs = {"channel": channel_id, "limit": 200}
    if oldest:
        kwargs["oldest"] = oldest

    result = slack_client.conversations_history(**kwargs)

    # Analyze activity
    messages = result["messages"]
    user_counts: dict = {}
    thread_count = 0
    reaction_count = 0

    for msg in messages:
        user_id = msg.get("user", "unknown")
        user_name = _get_user_name(user_id)
        user_counts[user_name] = user_counts.get(user_name, 0) + 1

        if msg.get("reply_count", 0) > 0:
            thread_count += 1
        reaction_count += len(msg.get("reactions", []))

    # Sort users by message count
    top_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    response = {
        "channel": channel,
        "period": f"Last {days_ago} days",
        "total_messages": len(messages),
        "threads": thread_count,
        "reactions": reaction_count,
        "active_users": len(user_counts),
        "top_contributors": [{"user": u, "messages": c} for u, c in top_users],
        "recent_messages": [
            {
                "user": _get_user_name(m.get("user", "unknown")),
                "text": m.get("text", "")[:100] + "..." if len(m.get("text", "")) > 100 else m.get("text", ""),
                "time": _format_timestamp(m["ts"]),
            }
            for m in messages[:5]
        ],
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


def main():
    """Run the Slack MCP server."""
    import asyncio
    from mcp.server.stdio import stdio_server

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()
