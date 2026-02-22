#!/usr/bin/env python3
"""
Slack MCP Server

Provides MCP tools for interacting with Slack workspaces, channels, and messages.
Uses the Slack Web API via slack_sdk.
"""

import json
import logging
import os
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Optional, List, Dict

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from mcp.server import Server
from mcp.types import Tool, TextContent

# Thread pool for parallel Slack API calls (Slack SDK is synchronous)
_executor = ThreadPoolExecutor(max_workers=20)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("slack-mcp-server")

# Cache for recent DM partners (for context-aware name resolution)
_recent_dm_partners: List[Dict[str, Any]] = []
_dm_cache_timestamp: Optional[datetime] = None

# Initialize Slack clients
# Bot token (xoxb-) - for channels, sending messages, listing users
bot_token = os.getenv("SLACK_BOT_TOKEN", "")
# User token (xoxp-) - for DMs, search, private content (optional but recommended)
user_token = os.getenv("SLACK_USER_TOKEN", "")

# Create clients - bot_client is required, user_client is optional
bot_client = WebClient(token=bot_token) if bot_token else None
user_client = WebClient(token=user_token) if user_token else None

# Default client for backward compatibility
slack_client = bot_client or user_client

def _get_client_for_operation(operation_type: str = "default") -> WebClient:
    """Get the appropriate client for the operation type.

    - 'dm': Uses user_client if available (required for reading DMs between users)
    - 'search': Uses user_client if available (better search results)
    - 'default': Uses bot_client, falls back to user_client
    """
    if operation_type in ("dm", "search"):
        # Prefer user token for DMs and search
        if user_client:
            return user_client
        elif bot_client:
            logger.warning(f"User token not available for {operation_type} operation. Using bot token (limited access).")
            return bot_client
        else:
            raise ValueError("No Slack token configured")
    else:
        # Default: prefer bot token
        if bot_client:
            return bot_client
        elif user_client:
            return user_client
        else:
            raise ValueError("No Slack token configured")

# Create MCP server
app = Server("slack-connector")

# Cache for channel/user lookups
_channel_cache: dict = {}
_user_cache: dict = {}
_user_info_cache: dict = {}  # user_id -> {name, real_name} for fast lookups
_users_loaded: bool = False


def _preload_all_users() -> None:
    """Pre-load all users into cache for fast lookups. Call this once before bulk operations."""
    global _users_loaded, _user_info_cache

    if _users_loaded and _user_info_cache:
        return  # Already loaded

    try:
        result = slack_client.users_list(limit=1000)
        for user in result.get("members", []):
            if user.get("deleted") or user.get("is_bot"):
                continue

            user_id = user["id"]
            real_name = user.get("real_name", "")
            username = user.get("name", "")
            email = user.get("profile", {}).get("email", "")
            display_name = user.get("profile", {}).get("display_name", "")

            _user_info_cache[user_id] = {
                "name": username,
                "real_name": real_name or username or user_id,
                "display_name": display_name,
                "email": email,
            }

            # Cache all lookup variations for _get_user_id
            if username:
                _user_cache[username] = user_id
                _user_cache[username.lower()] = user_id
            if email:
                _user_cache[email] = user_id
                _user_cache[email.lower()] = user_id
            if real_name:
                _user_cache[real_name.lower()] = user_id
                # Also cache first and last names for partial matching
                name_parts = real_name.lower().split()
                if name_parts:
                    # Cache first name -> user_id (may overwrite, that's ok for common names)
                    _user_cache[f"first:{name_parts[0]}"] = user_id
                    if len(name_parts) > 1:
                        # Cache last name -> user_id
                        _user_cache[f"last:{name_parts[-1]}"] = user_id
            if display_name:
                _user_cache[display_name.lower()] = user_id

        _users_loaded = True
        logger.info(f"Pre-loaded {len(_user_info_cache)} users into cache")
    except SlackApiError as e:
        logger.warning(f"Failed to preload users: {e}")


def _get_user_name_fast(user_id: str) -> str:
    """Get user display name from cache (no API call). Falls back to user_id if not cached."""
    if not user_id:
        return "Unknown"

    # Check info cache first (populated by _preload_all_users)
    if user_id in _user_info_cache:
        info = _user_info_cache[user_id]
        return info.get("real_name") or info.get("name") or user_id

    # If not in cache and users weren't loaded, try to load them
    if not _users_loaded:
        _preload_all_users()
        if user_id in _user_info_cache:
            info = _user_info_cache[user_id]
            return info.get("real_name") or info.get("name") or user_id

    # Fallback: return user_id (don't make API call for speed)
    return user_id


def _get_channel_id(channel_name: str) -> Optional[str]:
    """Get channel ID from name, with caching and fuzzy matching. Uses user token to access private channels."""
    if channel_name.startswith("C") or channel_name.startswith("D") or channel_name.startswith("G"):
        return channel_name  # Already an ID

    # Remove # prefix if present
    channel_name = channel_name.lstrip("#")

    # Normalize for matching: lowercase, replace spaces with dashes
    search_name = channel_name.lower().replace(" ", "-").replace("_", "-")

    # Check cache first (exact match)
    if channel_name in _channel_cache:
        return _channel_cache[channel_name]
    if search_name in _channel_cache:
        return _channel_cache[search_name]

    # Use user token to get private channels the user is a member of
    client = _get_client_for_operation("dm")

    try:
        # First try users_conversations which includes private channels user is in
        result = client.users_conversations(types="public_channel,private_channel", limit=500, exclude_archived=False)
        channels = result["channels"]
    except SlackApiError as e:
        logger.warning(f"users_conversations failed: {e}, falling back to conversations_list")
        try:
            result = client.conversations_list(types="public_channel,private_channel")
            channels = result["channels"]
        except SlackApiError as e2:
            logger.error(f"Error looking up channel: {e2}")
            return None

    # Build cache and look for matches
    exact_match = None
    fuzzy_matches = []

    for channel in channels:
        ch_name = channel["name"]
        ch_name_lower = ch_name.lower()
        _channel_cache[ch_name] = channel["id"]
        _channel_cache[ch_name_lower] = channel["id"]

        # Exact match
        if ch_name == channel_name or ch_name_lower == search_name:
            exact_match = channel["id"]
            continue

        # Fuzzy match: check if search term is contained in channel name
        # or if channel name contains all the key parts of search
        search_parts = search_name.replace("-", " ").split()
        if all(part in ch_name_lower for part in search_parts):
            fuzzy_matches.append((channel["id"], ch_name))
        elif search_name in ch_name_lower:
            fuzzy_matches.insert(0, (channel["id"], ch_name))  # Higher priority

    if exact_match:
        return exact_match

    if fuzzy_matches:
        # Return best fuzzy match
        best_id, best_name = fuzzy_matches[0]
        logger.info(f"Fuzzy matched '{channel_name}' to '#{best_name}'")
        return best_id

    return None


def _get_recent_dm_partners() -> List[Dict[str, Any]]:
    """Get list of recent DM conversation partners, sorted by most recent first.

    This is used for context-aware name resolution - if user asks about "Suresh",
    we check if they have a recent DM with someone named Suresh and prioritize that person.

    Returns list of dicts with: user_id, user_name, last_message_time
    """
    global _recent_dm_partners, _dm_cache_timestamp

    # Cache for 5 minutes
    if _dm_cache_timestamp and (datetime.now() - _dm_cache_timestamp).seconds < 300:
        return _recent_dm_partners

    client = _get_client_for_operation("dm")
    if not client:
        return []

    try:
        # Get recent DM conversations
        result = client.conversations_list(types="im", limit=50)
        dm_channels = result.get("channels", [])

        partners = []
        for dm in dm_channels:
            user_id = dm.get("user")
            if not user_id:
                continue

            # Get last message timestamp
            try:
                history = client.conversations_history(channel=dm["id"], limit=1)
                messages = history.get("messages", [])
                last_ts = float(messages[0]["ts"]) if messages else 0
            except:
                last_ts = 0

            user_name = _get_user_name(user_id)
            partners.append({
                "user_id": user_id,
                "user_name": user_name,
                "last_message_ts": last_ts,
            })

        # Sort by most recent
        partners.sort(key=lambda x: x["last_message_ts"], reverse=True)

        _recent_dm_partners = partners
        _dm_cache_timestamp = datetime.now()
        logger.info(f"Cached {len(partners)} recent DM partners for context-aware resolution")

        return partners

    except SlackApiError as e:
        logger.warning(f"Could not fetch DM partners for context: {e}")
        return []


def _resolve_user_with_context(user_identifier: str) -> Optional[str]:
    """Smart user resolution that uses DM history for context.

    When multiple users match (e.g., multiple "Suresh"), this prioritizes:
    1. Users you've recently DMed with
    2. Exact name matches
    3. Fuzzy matches

    This makes queries like "What did Suresh say to me?" work naturally
    by defaulting to the Suresh you actually talk to.
    """
    # First, try basic resolution
    result = _get_user_id(user_identifier)

    # If unambiguous, return as-is
    if result and not result.startswith("AMBIGUOUS:"):
        return result

    # If ambiguous, try to resolve using DM context
    if result and result.startswith("AMBIGUOUS:"):
        candidates_str = result.replace("AMBIGUOUS:", "")

        # Get recent DM partners
        dm_partners = _get_recent_dm_partners()
        dm_user_ids = {p["user_id"] for p in dm_partners}
        dm_user_names = {p["user_name"].lower() for p in dm_partners}

        search_lower = user_identifier.lower()

        # Check if any DM partner matches the search term
        for partner in dm_partners:
            partner_name_lower = partner["user_name"].lower()
            if (search_lower in partner_name_lower or
                partner_name_lower.startswith(search_lower) or
                search_lower == partner_name_lower.split()[0]):  # First name match
                logger.info(f"Context-resolved '{user_identifier}' to '{partner['user_name']}' (recent DM partner)")
                return partner["user_id"]

        # No DM context match, return the ambiguous result for clarification
        return result

    # Not found
    return result


def _get_user_id(user_identifier: str) -> Optional[str]:
    """Get user ID from name/email, with caching and robust fuzzy matching.

    Supports:
    - Exact username match
    - Exact email match
    - Exact real name match (case-insensitive)
    - Partial name match (first name, last name, or partial)
    - Display name match
    - Substring match (finds "Swati" in "Swati Sharma")

    Returns user_id or None. For ambiguous matches, returns special
    "AMBIGUOUS:name1|name2|name3" string that handlers can detect.
    When no match found, returns "NOT_FOUND:suggestions" with similar names.

    Note: For context-aware resolution (using DM history), use _resolve_user_with_context() instead.
    """
    if user_identifier.startswith("U"):
        return user_identifier  # Already an ID

    # Remove @ prefix if present
    user_identifier = user_identifier.lstrip("@").strip()
    search_lower = user_identifier.lower()

    # Check cache for exact match first
    if user_identifier in _user_cache:
        return _user_cache[user_identifier]
    if search_lower in _user_cache:
        return _user_cache[search_lower]
    # Check cached first/last name matches
    if f"first:{search_lower}" in _user_cache:
        return _user_cache[f"first:{search_lower}"]
    if f"last:{search_lower}" in _user_cache:
        return _user_cache[f"last:{search_lower}"]

    try:
        # Retry with backoff for rate limiting and pagination
        import time
        max_retries = 3
        all_members = []
        cursor = None

        # Paginate through all users
        while True:
            for attempt in range(max_retries):
                try:
                    if cursor:
                        result = slack_client.users_list(limit=200, cursor=cursor)
                    else:
                        result = slack_client.users_list(limit=200)
                    break
                except SlackApiError as e:
                    if 'ratelimited' in str(e) and attempt < max_retries - 1:
                        wait_time = int(e.response.headers.get('Retry-After', 2))
                        logger.warning(f"Rate limited, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                        time.sleep(wait_time)
                    else:
                        raise

            all_members.extend(result.get("members", []))
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        logger.info(f"🔍 Loaded {len(all_members)} users for lookup of '{user_identifier}'")

        # First pass: look for ALL matches (exact AND partial) to detect ambiguity
        exact_matches = []  # Now a list to handle multiple exact matches
        partial_matches = []
        substring_matches = []  # Lower priority - substring anywhere in name
        all_active_users = []  # For suggestions if no match

        for user in all_members:
            # Skip deleted users and bots
            if user.get("deleted") or user.get("is_bot"):
                continue

            user_id = user["id"]
            username = user.get("name", "")
            real_name = user.get("real_name", "")
            profile = user.get("profile", {})
            email = profile.get("email", "")
            display_name = profile.get("display_name", "")

            # Store all users for potential suggestions
            all_active_users.append({
                "id": user_id,
                "name": real_name or display_name or username,
                "email": email
            })

            # Cache all variations
            if username:
                _user_cache[username] = user_id
                _user_cache[username.lower()] = user_id
            if email:
                _user_cache[email] = user_id
                _user_cache[email.lower()] = user_id
            if real_name:
                _user_cache[real_name.lower()] = user_id
            if display_name:
                _user_cache[display_name.lower()] = user_id

            # Check for exact matches - but DON'T short-circuit, collect all!
            if username == user_identifier or \
               username.lower() == search_lower or \
               email == user_identifier or \
               email.lower() == search_lower or \
               real_name.lower() == search_lower or \
               display_name.lower() == search_lower:
                exact_matches.append((user_id, real_name or display_name or username, email))
                logger.info(f"✅ Exact match found: '{user_identifier}' -> '{real_name or username}' ({user_id})")
                # Don't continue - still check for partial matches to detect other "Dinesh" users

            # Check for partial matches (first name, last name, or contains)
            real_name_lower = real_name.lower()
            display_name_lower = display_name.lower()

            # Check if search term matches first or last name
            name_parts = real_name_lower.split()

            # Priority 1: First name exact match (highest confidence - "Akash" -> "Akash Anand")
            if name_parts and name_parts[0] == search_lower:
                partial_matches.insert(0, (user_id, real_name, email, "first_name"))
            # Priority 2: Last name exact match
            elif name_parts and len(name_parts) > 1 and name_parts[-1] == search_lower:
                partial_matches.append((user_id, real_name, email, "last_name"))
            # Priority 3: Any name part exact match (middle names)
            elif search_lower in name_parts:
                partial_matches.append((user_id, real_name, email, "name_part"))
            # Priority 4: Partial/substring match at word boundary
            elif real_name_lower.startswith(search_lower + " ") or (" " + search_lower) in real_name_lower:
                partial_matches.append((user_id, real_name, email, "partial"))
            elif display_name_lower.startswith(search_lower) or display_name_lower == search_lower:
                partial_matches.append((user_id, display_name, email, "display"))
            elif username.lower().startswith(search_lower):
                partial_matches.append((user_id, username, email, "username"))
            # Priority 5 (NEW): Substring match ANYWHERE in name (catches "Swati" in "Swati Sharma")
            elif search_lower in real_name_lower or search_lower in display_name_lower:
                substring_matches.append((user_id, real_name or display_name, email, "substring"))
            elif search_lower in username.lower():
                substring_matches.append((user_id, username, email, "substring_username"))

        # Combine exact and partial matches to detect ALL possible users
        # Normalize partial_matches format (4 elements) to match exact_matches (3 elements)
        all_matches = exact_matches + [(m[0], m[1], m[2]) for m in partial_matches]

        # Return exact match if found AND it's the only one
        if len(exact_matches) == 1 and len(partial_matches) == 0:
            logger.info(f"✅ Single exact match: '{user_identifier}' -> '{exact_matches[0][1]}'")
            return exact_matches[0][0]

        # If multiple exact matches or exact+partial, it's ambiguous
        if len(exact_matches) > 1 or (len(exact_matches) >= 1 and len(partial_matches) >= 1):
            # Dedupe by user_id
            seen_ids = set()
            unique_matches = []
            for match in all_matches:
                if match[0] not in seen_ids:
                    seen_ids.add(match[0])
                    unique_matches.append(match)

            if len(unique_matches) > 1:
                candidates = []
                for user_id, name, email in unique_matches[:5]:
                    if email:
                        candidates.append(f"{name} ({email})")
                    else:
                        candidates.append(name)
                logger.info(f"⚠️ Multiple matches for '{user_identifier}': {candidates}")
                return f"AMBIGUOUS:{' | '.join(candidates)}"
            elif len(unique_matches) == 1:
                return unique_matches[0][0]

        # Handle partial matches only (no exact)
        if partial_matches:
            # If only one match, return it
            if len(partial_matches) == 1:
                best_match = partial_matches[0]
                logger.info(f"✅ Fuzzy matched '{user_identifier}' to '{best_match[1]}' (user_id: {best_match[0]})")
                return best_match[0]

            # Check if there's a clear first_name match - prefer that over ambiguity
            first_name_matches = [m for m in partial_matches if m[3] == "first_name"]
            if len(first_name_matches) == 1:
                best_match = first_name_matches[0]
                logger.info(f"✅ First name matched '{user_identifier}' to '{best_match[1]}' (user_id: {best_match[0]})")
                return best_match[0]

            # Multiple matches - return special ambiguous marker
            candidates = []
            for match in partial_matches[:5]:
                user_id, name, email, match_type = match
                if email:
                    candidates.append(f"{name} ({email})")
                else:
                    candidates.append(name)

            logger.info(f"⚠️ Ambiguous match for '{user_identifier}': {candidates}")
            return f"AMBIGUOUS:{' | '.join(candidates)}"

        # Fallback to substring matches (less confident, but better than nothing)
        if substring_matches:
            if len(substring_matches) == 1:
                best_match = substring_matches[0]
                logger.info(f"✅ Substring matched '{user_identifier}' to '{best_match[1]}' (user_id: {best_match[0]})")
                return best_match[0]

            # Multiple substring matches - return as ambiguous
            candidates = []
            for match in substring_matches[:5]:
                user_id, name, email, match_type = match
                if email:
                    candidates.append(f"{name} ({email})")
                else:
                    candidates.append(name)

            logger.info(f"⚠️ Multiple substring matches for '{user_identifier}': {candidates}")
            return f"AMBIGUOUS:{' | '.join(candidates)}"

        # No match found - find similar names to suggest
        logger.warning(f"❌ No match found for '{user_identifier}' among {len(all_active_users)} users")

        # Find names that might be similar (start with same letter, contain similar substrings)
        suggestions = []
        search_first_letter = search_lower[0] if search_lower else ""
        search_first_two = search_lower[:2] if len(search_lower) >= 2 else search_lower

        for u in all_active_users:
            name_lower = u["name"].lower()
            # Suggest names starting with same letters
            if name_lower.startswith(search_first_two):
                suggestions.append(u["name"])
            elif name_lower.startswith(search_first_letter) and len(suggestions) < 10:
                suggestions.append(u["name"])

        if suggestions:
            suggestions = suggestions[:5]  # Limit to 5
            return f"NOT_FOUND:{user_identifier}|SUGGESTIONS:{','.join(suggestions)}"

        return f"NOT_FOUND:{user_identifier}|NO_SIMILAR_USERS"

    except SlackApiError as e:
        logger.error(f"Error looking up user: {e}")

    return None


def _check_ambiguous_user(user_id_result: Optional[str], user_query: str) -> tuple[bool, Optional[str], Optional[str]]:
    """Check if user lookup result is ambiguous or not found.

    Returns: (is_ambiguous, user_id_or_none, error_message_or_none)

    Error message formats:
    - For ambiguous: "Multiple users match 'X'. Did you mean: A, B, C?"
    - For not found with suggestions: "User 'X' not found. Similar names: A, B, C"
    - For not found without suggestions: "User 'X' not found in this workspace."
    """
    if user_id_result is None:
        return False, None, f"User '{user_query}' not found in this workspace. Try using their full name or email address."

    if user_id_result.startswith("NOT_FOUND:"):
        # Parse the NOT_FOUND response
        parts = user_id_result.replace("NOT_FOUND:", "")
        if "|SUGGESTIONS:" in parts:
            search_term, suggestions = parts.split("|SUGGESTIONS:")
            return False, None, f"User '{search_term}' not found. Similar names in workspace: {suggestions.replace(',', ', ')}"
        elif "|NO_SIMILAR_USERS" in parts:
            search_term = parts.replace("|NO_SIMILAR_USERS", "")
            return False, None, f"User '{search_term}' not found in this workspace. No similar names found."
        else:
            return False, None, f"User '{user_query}' not found in this workspace."

    if user_id_result.startswith("AMBIGUOUS:"):
        candidates = user_id_result.replace("AMBIGUOUS:", "")
        return True, None, f"Multiple users match '{user_query}'. Did you mean: {candidates}? Please be more specific (use full name or email)."

    return False, user_id_result, None


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
Returns matching messages with context. Defaults to last 30 days for relevance.""",
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
                    "days_ago": {
                        "type": "integer",
                        "description": "Search messages from the last N days (default: 30). Set to 0 for all time.",
                        "default": 30,
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
        Tool(
            name="ask_about_person",
            description="""THE PRIMARY TOOL for ANY question about a person in Slack.

USE THIS FOR ANY QUERY MENTIONING A PERSON'S NAME:
- "What is Chandru doing?"
- "What did Suresh say to me?"
- "When did John last message?"
- "What project is Sarah working on?"
- "Show me Austin's recent activity"
- "What has [anyone] been up to?"

This tool:
1. Uses SMART NAME RESOLUTION - if you ask about "Suresh" and you have a recent DM with a Suresh, it picks THAT Suresh automatically
2. Searches their messages across ALL channels
3. Checks your DM history with them
4. Returns their recent activity and online status

Just pass the person's name - it handles everything else.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "person": {
                        "type": "string",
                        "description": "Person's name (first name, full name, or email)",
                    },
                    "question_type": {
                        "type": "string",
                        "enum": ["activity", "dm_history", "last_message", "profile", "all"],
                        "description": "What to look up: 'activity' (their messages), 'dm_history' (your DMs with them), 'last_message' (most recent), 'profile' (info), 'all' (everything)",
                        "default": "all",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Look back this many days (default: 7)",
                        "default": 7,
                    },
                },
                "required": ["person"],
            },
        ),
        Tool(
            name="get_user_activity",
            description="""Get a user's recent messages across all channels. Consider using ask_about_person instead for more comprehensive results.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "user": {
                        "type": "string",
                        "description": "User name, first name, email, or ID",
                    },
                    "days_ago": {
                        "type": "integer",
                        "description": "Search messages from the last N days (default: 7)",
                        "default": 7,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max messages to return (default: 30)",
                        "default": 30,
                    },
                },
                "required": ["user"],
            },
        ),
        Tool(
            name="get_all_recent_messages",
            description="""Get ALL your recent messages across ALL DMs and channels.

USE THIS TOOL WHEN:
- User asks "what messages did I get yesterday?"
- User asks "summarize my Slack messages"
- User asks "what did I miss?" or "catch me up"
- User wants a comprehensive view of recent activity
- User asks about messages from a specific time period

This is the PRIMARY tool for getting a comprehensive view of recent Slack activity.
Returns messages from all DMs and channels the user is part of, sorted by time.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "hours_ago": {
                        "type": "integer",
                        "description": "Get messages from the last N hours (default: 24)",
                        "default": 24,
                    },
                    "include_channels": {
                        "type": "boolean",
                        "description": "Include channel messages (default: true)",
                        "default": True,
                    },
                    "include_dms": {
                        "type": "boolean",
                        "description": "Include DM messages (default: true)",
                        "default": True,
                    },
                    "max_messages_per_conversation": {
                        "type": "integer",
                        "description": "Max messages per DM/channel (default: 20)",
                        "default": 20,
                    },
                },
                "required": [],
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
        elif name == "ask_about_person":
            return await handle_ask_about_person(arguments)
        elif name == "get_user_activity":
            return await handle_get_user_activity(arguments)
        elif name == "get_all_recent_messages":
            return await handle_get_all_recent_messages(arguments)
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
    """List all channels including private ones the user is a member of."""
    include_private = arguments.get("include_private", True)
    limit = arguments.get("limit", 100)

    types = "public_channel"
    if include_private:
        types += ",private_channel"

    # Use conversations.list which returns num_members (users_conversations doesn't)
    client = _get_client_for_operation("channels")

    all_channels = []
    cursor = None

    # Paginate to get all channels up to the limit
    while len(all_channels) < limit:
        try:
            if cursor:
                result = client.conversations_list(
                    types=types,
                    limit=min(200, limit - len(all_channels)),
                    cursor=cursor,
                    exclude_archived=True
                )
            else:
                result = client.conversations_list(
                    types=types,
                    limit=min(200, limit),
                    exclude_archived=True
                )

            all_channels.extend(result.get("channels", []))
            cursor = result.get("response_metadata", {}).get("next_cursor")

            if not cursor:
                break

        except SlackApiError as e:
            logger.error(f"Error listing channels: {e}")
            break

    channels = []
    for channel in all_channels[:limit]:
        name = channel["name"]
        is_private = channel.get("is_private", False)
        # Format name with lock for private channels
        display_name = f"[private] #{name}" if is_private else f"#{name}"

        channels.append({
            "id": channel["id"],
            "name": display_name,
            "is_private": is_private,
            "topic": channel.get("topic", {}).get("value", "")[:80] if channel.get("topic", {}).get("value") else "",
            "purpose": channel.get("purpose", {}).get("value", "")[:80] if channel.get("purpose", {}).get("value") else "",
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
        return [TextContent(type="text", text=json.dumps({"error": f"Channel not found: {channel}"}))]

    # Use user client which has access to channels user is member of
    client = _get_client_for_operation("dm")

    try:
        result = client.conversations_history(channel=channel_id, limit=limit)
    except SlackApiError as e:
        # If user client fails, try bot client
        if bot_client:
            try:
                result = bot_client.conversations_history(channel=channel_id, limit=limit)
            except SlackApiError as e2:
                return [TextContent(type="text", text=json.dumps({"error": f"Cannot read channel {channel}: {e2.response['error']}"}))]
        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Cannot read channel {channel}: {e.response['error']}"}))]

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
    """Search messages with default time filter for relevance."""
    query = arguments["query"]
    limit = arguments.get("limit", 20)
    days_ago = arguments.get("days_ago", 30)  # Default to last 30 days for relevance

    # Resolve user names in "from:" queries to user IDs
    # Slack search API requires usernames/IDs, not display names
    from_match = re.search(r'from:[@]?([^\s]+(?:\s+[^\s]+)?)', query, re.IGNORECASE)
    if from_match:
        user_query = from_match.group(1).strip()
        # Try to resolve to user ID
        user_id = _get_user_id(user_query)
        if user_id and not user_id.startswith("AMBIGUOUS:") and not user_id.startswith("NOT_FOUND:"):
            # Replace with the user ID in the query
            query = query.replace(from_match.group(0), f"from:<@{user_id}>")
            logger.info(f"🔍 Resolved user '{user_query}' to ID {user_id}")
        else:
            logger.warning(f"⚠️ Could not resolve user '{user_query}' for search")

    # Add date filter to search query for recent results
    # Slack search supports "after:YYYY-MM-DD" syntax
    # days_ago=0 means search all time (no filter)
    if days_ago and days_ago > 0 and "after:" not in query.lower():
        cutoff_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        query = f"{query} after:{cutoff_date}"
        logger.info(f"🔍 Search with date filter: {query}")

    # Use user client for search (better results)
    client = _get_client_for_operation("search")
    result = client.search_messages(query=query, count=limit)

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
        "date_filter": f"Last {days_ago} days" if days_ago and days_ago > 0 else "All time",
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

    user_id_result = _get_user_id(user)
    is_ambiguous, user_id, error_msg = _check_ambiguous_user(user_id_result, user)
    if error_msg:
        return [TextContent(type="text", text=error_msg)]

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
    """List all users with pagination support."""
    limit = arguments.get("limit", 500)  # Higher default limit

    users = []
    cursor = None

    # Paginate through all users
    while True:
        if cursor:
            result = slack_client.users_list(limit=200, cursor=cursor)
        else:
            result = slack_client.users_list(limit=200)

        for user in result.get("members", []):
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

        # Check for more pages
        cursor = result.get("response_metadata", {}).get("next_cursor")
        if not cursor or len(users) >= limit:
            break

    # Trim to requested limit
    users = users[:limit]

    response = {
        "count": len(users),
        "users": users,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_get_user_info(arguments: dict) -> list[TextContent]:
    """Get user details."""
    user = arguments["user"]
    user_id_result = _get_user_id(user)
    is_ambiguous, user_id, error_msg = _check_ambiguous_user(user_id_result, user)

    if error_msg:
        return [TextContent(type="text", text=error_msg)]

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
    user_id_result = _get_user_id(user)
    is_ambiguous, user_id, error_msg = _check_ambiguous_user(user_id_result, user)

    if error_msg:
        return [TextContent(type="text", text=error_msg)]

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


def _find_dm_channel_with_user(client: WebClient, target_user_id: str) -> Optional[str]:
    """Find existing DM channel with a user by listing all DM conversations."""
    try:
        # List all DM conversations
        dms = client.conversations_list(types="im,mpim", limit=200)
        for dm in dms.get("channels", []):
            if dm.get("user") == target_user_id:
                return dm["id"]
    except SlackApiError as e:
        logger.warning(f"Error listing DMs: {e}")
    return None


async def handle_read_dm_with_user(arguments: dict) -> list[TextContent]:
    """Read DM conversation with a specific user."""
    user = arguments["user"]
    limit = min(arguments.get("limit", 50), 200)
    days_ago = arguments.get("days_ago")
    since_date = arguments.get("since_date")

    # Use user client for DM operations (required for reading DMs between users)
    client = _get_client_for_operation("dm")

    user_id_result = _get_user_id(user)
    is_ambiguous, user_id, error_msg = _check_ambiguous_user(user_id_result, user)
    if error_msg:
        # Return JSON error for consistency
        error_response = {"error": error_msg, "query": user}
        if is_ambiguous:
            error_response["type"] = "ambiguous_user"
        return [TextContent(type="text", text=json.dumps(error_response, indent=2))]

    # Find existing DM channel with user (doesn't require im:write scope)
    dm_channel = _find_dm_channel_with_user(client, user_id)

    if not dm_channel:
        # Fallback: try conversations_open (requires im:write scope)
        try:
            dm_result = client.conversations_open(users=[user_id])
            dm_channel = dm_result["channel"]["id"]
        except SlackApiError as e:
            user_name = _get_user_name(user_id)
            if "missing_scope" in str(e):
                return [TextContent(type="text", text=f"No existing DM conversation found with {user_name}. To start a new conversation, the User Token needs 'im:write' scope.")]
            return [TextContent(type="text", text=f"Could not access DM with {user_name}: {e.response['error']}")]

    # Build history query
    kwargs = {"channel": dm_channel, "limit": limit}
    oldest = _parse_date_filter(days_ago, since_date)
    if oldest:
        kwargs["oldest"] = oldest

    try:
        result = client.conversations_history(**kwargs)
    except SlackApiError as e:
        error_hint = ""
        if "missing_scope" in str(e):
            error_hint = "\n\nHint: Reading DM history requires im:history scope on your User Token."
        return [TextContent(type="text", text=f"Could not read DM history: {e.response['error']}{error_hint}")]

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

    user_id_result = _get_user_id(user)
    is_ambiguous, user_id, error_msg = _check_ambiguous_user(user_id_result, user)
    if error_msg:
        return [TextContent(type="text", text=error_msg)]

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

    # Use user client for DM operations
    client = _get_client_for_operation("dm")
    result = client.conversations_list(types="im,mpim", limit=limit)

    dms = []
    for dm in result["channels"]:
        is_mpim = dm.get("is_mpim", False)
        is_im = dm.get("is_im", False)
        user_id = dm.get("user")

        if is_mpim or (not is_im and not user_id):
            # Group DM - get member names from channel name or members list
            dm_name = dm.get("name", "")
            # MPIM names are like "mpdm-user1--user2--user3-1"
            member_names = dm.get("purpose", {}).get("value", dm_name)
            dms.append({
                "channel_id": dm["id"],
                "type": "group_dm",
                "name": member_names or dm_name,
                "is_open": dm.get("is_open", False),
                "num_members": dm.get("num_members", 0),
            })
        elif is_im or user_id:
            # 1-on-1 DM - has is_im=True or has user field
            if user_id:
                user_name = _get_user_name(user_id)
                dms.append({
                    "channel_id": dm["id"],
                    "type": "direct_dm",
                    "user_id": user_id,
                    "user_name": user_name,
                    "is_open": dm.get("is_open", False),
                })

    response = {
        "count": len(dms),
        "direct_dms": [d for d in dms if d.get("type") == "direct_dm"],
        "group_dms": [d for d in dms if d.get("type") == "group_dm"],
        "dms": dms,
    }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_search_in_dms(arguments: dict) -> list[TextContent]:
    """Search for content across DMs."""
    query = arguments["query"]
    limit = arguments.get("limit", 30)

    # Use user client for DM search
    client = _get_client_for_operation("search")

    # Use Slack search with "is:dm" modifier to search only DMs
    search_query = f"{query} is:dm"
    result = client.search_messages(query=search_query, count=limit)

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


async def handle_ask_about_person(arguments: dict) -> list[TextContent]:
    """THE PRIMARY unified handler for any question about a person in Slack.

    Uses context-aware name resolution - if user asks about "Suresh" and they have
    a recent DM with someone named Suresh, it automatically picks THAT Suresh.

    Combines: activity search, DM history, profile info, and presence status.
    """
    person = arguments["person"]
    question_type = arguments.get("question_type", "all")
    days = arguments.get("days", 7)

    logger.info(f"ask_about_person: person='{person}', type='{question_type}', days={days}")

    # Use context-aware resolution (prioritizes recent DM partners)
    user_id_result = _resolve_user_with_context(person)
    is_ambiguous, user_id, error_msg = _check_ambiguous_user(user_id_result, person)

    if error_msg:
        return [TextContent(type="text", text=json.dumps({
            "error": error_msg,
            "query": person,
            "suggestion": "Try using the person's full name or email address.",
            "hint": "If you recently DMed this person, their name should resolve automatically."
        }, indent=2))]

    # Get user info for display
    user_name = _get_user_name(user_id)
    logger.info(f"Resolved '{person}' to '{user_name}' ({user_id})")

    response = {
        "person": user_name,
        "user_id": user_id,
        "query": person,
        "resolved_via": "context" if user_id_result != _get_user_id(person) else "direct",
    }

    # Get presence status (always useful)
    try:
        presence_result = slack_client.users_getPresence(user=user_id)
        response["status"] = {
            "online": presence_result.get("presence") == "active",
            "presence": presence_result.get("presence", "unknown"),
        }
    except SlackApiError:
        response["status"] = {"online": None, "presence": "unknown"}

    # Based on question_type, gather the relevant information
    if question_type in ("profile", "all"):
        try:
            result = slack_client.users_info(user=user_id)
            u = result["user"]
            profile = u.get("profile", {})
            response["profile"] = {
                "real_name": u.get("real_name", ""),
                "email": profile.get("email", ""),
                "title": profile.get("title", ""),
                "status_text": profile.get("status_text", ""),
                "timezone": u.get("tz", ""),
            }
        except SlackApiError as e:
            response["profile"] = {"error": str(e)}

    if question_type in ("activity", "all"):
        # Search for their messages across all channels
        client = _get_client_for_operation("search")
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        search_query = f"from:<@{user_id}> after:{cutoff_date}"

        try:
            logger.info(f"🔍 Searching for activity: query='{search_query}'")
            result = client.search_messages(query=search_query, count=30, sort="timestamp", sort_dir="desc")
            total_matches = result.get("messages", {}).get("total", 0)
            matches = result.get("messages", {}).get("matches", [])
            logger.info(f"🔍 Search results: total={total_matches}, returned={len(matches)}")

            channels_active = set()
            messages = []
            for match in matches:
                channel_name = match.get("channel", {}).get("name", "unknown")
                if channel_name != "unknown":
                    channels_active.add(channel_name)
                messages.append({
                    "channel": f"#{channel_name}" if channel_name != "unknown" else "DM",
                    "text": match.get("text", "")[:300],
                    "time": _format_timestamp(match["ts"]),
                    "permalink": match.get("permalink", ""),
                })

            response["activity"] = {
                "period": f"Last {days} days",
                "total_messages": result.get("messages", {}).get("total", 0),
                "active_in_channels": list(channels_active),
                "recent_messages": messages[:10],
            }
        except SlackApiError as e:
            response["activity"] = {"error": f"Could not search activity: {e.response.get('error', str(e))}"}

    if question_type in ("dm_history", "last_message", "all"):
        # Get DM conversation history with this person
        client = _get_client_for_operation("dm")
        dm_channel = _find_dm_channel_with_user(client, user_id)

        if dm_channel:
            try:
                limit = 1 if question_type == "last_message" else 20
                oldest = _parse_date_filter(days)
                kwargs = {"channel": dm_channel, "limit": limit}
                if oldest and question_type != "last_message":
                    kwargs["oldest"] = oldest

                result = client.conversations_history(**kwargs)
                dm_messages = []
                for msg in result.get("messages", []):
                    sender_name = _get_user_name(msg.get("user", "unknown"))
                    dm_messages.append({
                        "from": sender_name,
                        "text": msg.get("text", "")[:300],
                        "time": _format_timestamp(msg["ts"]),
                        "is_them": msg.get("user") == user_id,
                    })

                if question_type == "last_message":
                    response["last_message"] = dm_messages[0] if dm_messages else None
                else:
                    response["dm_history"] = {
                        "has_dm_conversation": True,
                        "message_count": len(dm_messages),
                        "messages": dm_messages,
                    }
            except SlackApiError as e:
                if question_type == "last_message":
                    response["last_message"] = {"error": str(e)}
                else:
                    response["dm_history"] = {"error": f"Could not read DMs: {e.response.get('error', str(e))}"}
        else:
            if question_type == "last_message":
                response["last_message"] = None
            else:
                response["dm_history"] = {
                    "has_dm_conversation": False,
                    "note": f"No DM conversation found with {user_name}",
                }

    return [TextContent(type="text", text=json.dumps(response, indent=2))]


async def handle_get_user_activity(arguments: dict) -> list[TextContent]:
    """Get a specific user's recent activity across all channels."""
    user_query = arguments["user"]
    days_ago = arguments.get("days_ago", 7)
    limit = arguments.get("limit", 30)

    # Use context-aware resolution (prioritizes users from recent DMs)
    user_id_result = _resolve_user_with_context(user_query)
    is_ambiguous, user_id, error_msg = _check_ambiguous_user(user_id_result, user_query)

    if error_msg:
        return [TextContent(type="text", text=json.dumps({
            "error": error_msg,
            "query": user_query,
            "suggestion": "Try using the person's full name or email address."
        }, indent=2))]

    # Get user info
    user_name = _get_user_name(user_id)

    # Use Slack search API to find all messages from this user
    client = _get_client_for_operation("search")

    # Build search query with date filter
    cutoff_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    search_query = f"from:<@{user_id}> after:{cutoff_date}"

    logger.info(f"🔍 Searching for activity from '{user_name}' ({user_id}): {search_query}")

    try:
        result = client.search_messages(query=search_query, count=limit, sort="timestamp", sort_dir="desc")

        messages = []
        channels_active = set()

        for match in result.get("messages", {}).get("matches", []):
            channel_name = match.get("channel", {}).get("name", "unknown")
            channels_active.add(channel_name)

            messages.append({
                "channel": f"#{channel_name}" if channel_name != "unknown" else "DM",
                "text": match.get("text", "")[:500],
                "time": _format_timestamp(match["ts"]),
                "permalink": match.get("permalink", ""),
            })

        # Also get user presence
        try:
            presence_result = slack_client.users_getPresence(user=user_id)
            presence = presence_result.get("presence", "unknown")
            is_online = presence == "active"
        except SlackApiError:
            presence = "unknown"
            is_online = None

        response = {
            "user": user_name,
            "user_id": user_id,
            "status": {
                "online": is_online,
                "presence": presence,
            },
            "activity_period": f"Last {days_ago} days",
            "total_messages": result.get("messages", {}).get("total", 0),
            "messages_returned": len(messages),
            "active_in_channels": list(channels_active),
            "recent_messages": messages,
        }

        return [TextContent(type="text", text=json.dumps(response, indent=2))]

    except SlackApiError as e:
        logger.error(f"Error searching for user activity: {e}")
        return [TextContent(type="text", text=json.dumps({
            "error": f"Failed to search for user activity: {e.response.get('error', str(e))}",
            "user": user_name,
            "user_id": user_id
        }, indent=2))]


async def handle_get_all_recent_messages(arguments: dict) -> list[TextContent]:
    """Get all recent messages across DMs and channels - OPTIMIZED with parallel fetching."""
    import time
    start_time = time.time()

    hours_ago = arguments.get("hours_ago", 24)
    include_channels = arguments.get("include_channels", True)
    include_dms = arguments.get("include_dms", True)
    max_per_convo = arguments.get("max_messages_per_conversation", 20)

    # Calculate time cutoff
    cutoff_time = datetime.now() - timedelta(hours=hours_ago)
    oldest_ts = str(cutoff_time.timestamp())

    client = _get_client_for_operation("dm")
    all_messages: List[Dict] = []
    errors: List[str] = []
    loop = asyncio.get_event_loop()

    # Step 1: Pre-load all users into cache (single API call)
    logger.info("Pre-loading user cache...")
    await loop.run_in_executor(_executor, _preload_all_users)
    logger.info(f"User cache loaded in {time.time() - start_time:.2f}s")

    # Step 2: Get list of all conversations (DMs + channels) in parallel
    dm_channels: List[Dict] = []
    channels: List[Dict] = []

    async def fetch_dm_list():
        try:
            result = await loop.run_in_executor(
                _executor,
                lambda: client.conversations_list(types="im,mpim", limit=200)
            )
            return result.get("channels", [])
        except SlackApiError as e:
            errors.append(f"Listing DMs: {e.response.get('error', str(e))}")
            return []

    async def fetch_channel_list():
        try:
            result = await loop.run_in_executor(
                _executor,
                lambda: client.users_conversations(
                    types="public_channel,private_channel",
                    limit=100,
                    exclude_archived=True
                )
            )
            return result.get("channels", [])
        except SlackApiError as e:
            errors.append(f"Listing channels: {e.response.get('error', str(e))}")
            return []

    # Fetch both lists in parallel
    list_tasks = []
    if include_dms:
        list_tasks.append(fetch_dm_list())
    if include_channels:
        list_tasks.append(fetch_channel_list())

    list_results = await asyncio.gather(*list_tasks)

    if include_dms and len(list_results) > 0:
        dm_channels = list_results[0]
    if include_channels:
        channels = list_results[-1] if include_dms else list_results[0]

    logger.info(f"Found {len(dm_channels)} DMs and {len(channels)} channels to check")

    # Step 3: Fetch messages from all conversations IN PARALLEL
    # Use semaphore to limit concurrent requests (avoid rate limiting)
    semaphore = asyncio.Semaphore(15)  # Max 15 concurrent API calls

    async def fetch_dm_history(dm: Dict) -> List[Dict]:
        """Fetch history for a single DM or group DM conversation."""
        async with semaphore:
            dm_id = dm["id"]
            is_mpim = dm.get("is_mpim", False)

            # Get conversation name
            if is_mpim:
                # Group DM - use name or purpose
                convo_name = dm.get("purpose", {}).get("value") or dm.get("name", "Group DM")
            else:
                # 1-on-1 DM
                user_id = dm.get("user", "")
                convo_name = _get_user_name_fast(user_id)

            try:
                history = await loop.run_in_executor(
                    _executor,
                    lambda: client.conversations_history(
                        channel=dm_id,
                        oldest=oldest_ts,
                        limit=max_per_convo
                    )
                )
                messages = []
                for msg in history.get("messages", []):
                    sender_id = msg.get("user", "")
                    messages.append({
                        "type": "group_dm" if is_mpim else "dm",
                        "conversation_with": convo_name,
                        "from": _get_user_name_fast(sender_id),
                        "text": msg.get("text", ""),
                        "timestamp": msg["ts"],
                        "time": _format_timestamp(msg["ts"]),
                    })
                return messages
            except SlackApiError as e:
                if "channel_not_found" not in str(e) and "not_in_channel" not in str(e):
                    errors.append(f"DM with {convo_name}: {e.response.get('error', str(e))}")
                return []
            except Exception as e:
                return []

    async def fetch_channel_history(channel: Dict) -> List[Dict]:
        """Fetch history for a single channel."""
        async with semaphore:
            ch_id = channel["id"]
            ch_name = channel.get("name", "unknown")

            try:
                history = await loop.run_in_executor(
                    _executor,
                    lambda: client.conversations_history(
                        channel=ch_id,
                        oldest=oldest_ts,
                        limit=max_per_convo
                    )
                )
                messages = []
                for msg in history.get("messages", []):
                    sender_id = msg.get("user", "")
                    messages.append({
                        "type": "channel",
                        "channel": f"#{ch_name}",
                        "from": _get_user_name_fast(sender_id),
                        "text": msg.get("text", "")[:500],
                        "timestamp": msg["ts"],
                        "time": _format_timestamp(msg["ts"]),
                        "has_thread": msg.get("reply_count", 0) > 0,
                    })
                return messages
            except SlackApiError as e:
                if "channel_not_found" not in str(e) and "not_in_channel" not in str(e):
                    errors.append(f"#{ch_name}: {e.response.get('error', str(e))}")
                return []
            except Exception as e:
                return []

    # Create all fetch tasks
    fetch_tasks = []
    if include_dms:
        fetch_tasks.extend([fetch_dm_history(dm) for dm in dm_channels])
    if include_channels:
        fetch_tasks.extend([fetch_channel_history(ch) for ch in channels])

    # Execute all fetches in parallel
    logger.info(f"Fetching messages from {len(fetch_tasks)} conversations in parallel...")
    fetch_start = time.time()
    results = await asyncio.gather(*fetch_tasks)
    logger.info(f"Parallel fetch completed in {time.time() - fetch_start:.2f}s")

    # Flatten results
    for msg_list in results:
        all_messages.extend(msg_list)

    # Sort all messages by timestamp (most recent first)
    all_messages.sort(key=lambda x: float(x["timestamp"]), reverse=True)

    # Group messages by type
    dm_messages = [m for m in all_messages if m["type"] == "dm"]
    group_dm_messages = [m for m in all_messages if m["type"] == "group_dm"]
    channel_messages = [m for m in all_messages if m["type"] == "channel"]

    total_time = time.time() - start_time
    logger.info(f"Total time: {total_time:.2f}s for {len(all_messages)} messages from {len(fetch_tasks)} conversations")

    # Build response
    response = {
        "time_period": f"Last {hours_ago} hours",
        "conversations_checked": len(fetch_tasks),
        "total_messages": len(all_messages),
        "dm_messages_count": len(dm_messages),
        "group_dm_messages_count": len(group_dm_messages),
        "channel_messages_count": len(channel_messages),
        "fetch_time_seconds": round(total_time, 2),
        "dm_messages": dm_messages[:100],
        "group_dm_messages": group_dm_messages[:50],
        "channel_messages": channel_messages[:100],
    }

    if errors:
        response["errors"] = errors[:10]
        response["error_count"] = len(errors)

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
