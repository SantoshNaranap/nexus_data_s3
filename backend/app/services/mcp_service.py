"""MCP service for managing connector clients."""

import os
import asyncio
import time
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Any, List
import logging
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.core.config import settings
from app.services.credential_service import credential_service
from app.services.circuit_breaker import get_mcp_breaker, CircuitOpenError
from app.connectors import (
    get_connector,
    get_all_connectors,
    get_available_datasources as registry_get_available_datasources,
    get_credential_env_mapping,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONNECTION POOLING - Reuse MCP subprocess connections to save 200-500ms/call
# =============================================================================

@dataclass
class PooledConnection:
    """A reusable MCP connection backed by a subprocess."""
    session: ClientSession
    stdio_context: Any  # The stdio_client context manager
    session_context: Any  # The ClientSession context manager
    read_stream: Any
    write_stream: Any
    created_at: float
    last_used: float
    datasource: str
    pool_key: str
    in_use: bool = False


class MCPConnectionPool:
    """
    Reuses MCP subprocess connections instead of creating new ones.
    Saves 200-500ms per tool call by avoiding subprocess spawn overhead.
    """

    def __init__(self, max_per_key: int = 3, idle_timeout: float = 300.0):
        self._pools: Dict[str, List[PooledConnection]] = defaultdict(list)
        self._locks: Dict[str, asyncio.Lock] = {}
        self._max_per_key = max_per_key
        self._idle_timeout = idle_timeout
        self._cleanup_task: Optional[asyncio.Task] = None

    def _get_lock(self, key: str) -> asyncio.Lock:
        """Get or create a lock for a pool key."""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def acquire(
        self,
        datasource: str,
        pool_key: str,
        server_params: StdioServerParameters,
    ) -> PooledConnection:
        """Get a connection from pool, or create a new one."""
        lock = self._get_lock(pool_key)

        async with lock:
            pool = self._pools[pool_key]
            now = time.time()

            # Try to reuse an idle connection
            for conn in pool:
                if not conn.in_use and (now - conn.last_used) < self._idle_timeout:
                    conn.in_use = True
                    conn.last_used = now
                    logger.info(f"♻️ Reusing pooled connection for {pool_key}")
                    return conn

            # Evict stale connections
            stale = [c for c in pool if not c.in_use and (now - c.last_used) >= self._idle_timeout]
            for conn in stale:
                pool.remove(conn)
                await self._close_connection(conn)

            # Create new connection
            logger.info(f"🆕 Creating new pooled connection for {pool_key}")
            conn = await self._create_connection(datasource, pool_key, server_params)
            pool.append(conn)
            return conn

    async def release(self, conn: PooledConnection):
        """Return a connection to the pool for reuse."""
        lock = self._get_lock(conn.pool_key)
        async with lock:
            conn.in_use = False
            conn.last_used = time.time()

            # If pool is over capacity, close this connection
            pool = self._pools[conn.pool_key]
            idle_count = sum(1 for c in pool if not c.in_use)
            if idle_count > self._max_per_key:
                pool.remove(conn)
                await self._close_connection(conn)

    async def discard(self, conn: PooledConnection):
        """Remove a broken connection from the pool and close it."""
        lock = self._get_lock(conn.pool_key)
        async with lock:
            pool = self._pools[conn.pool_key]
            if conn in pool:
                pool.remove(conn)
        await self._close_connection(conn)

    async def _create_connection(
        self,
        datasource: str,
        pool_key: str,
        server_params: StdioServerParameters,
    ) -> PooledConnection:
        """Create a new MCP connection by spawning a subprocess."""
        # Manually enter context managers so we can keep them alive
        stdio_ctx = stdio_client(server_params)
        read_stream, write_stream = await stdio_ctx.__aenter__()

        session_ctx = ClientSession(read_stream, write_stream)
        session = await session_ctx.__aenter__()
        await session.initialize()

        now = time.time()
        return PooledConnection(
            session=session,
            stdio_context=stdio_ctx,
            session_context=session_ctx,
            read_stream=read_stream,
            write_stream=write_stream,
            created_at=now,
            last_used=now,
            datasource=datasource,
            pool_key=pool_key,
            in_use=True,
        )

    async def _close_connection(self, conn: PooledConnection):
        """Close a connection and its subprocess."""
        try:
            await conn.session_context.__aexit__(None, None, None)
        except Exception as e:
            logger.debug(f"Error closing session for {conn.pool_key}: {e}")
        try:
            await conn.stdio_context.__aexit__(None, None, None)
        except Exception as e:
            logger.debug(f"Error closing stdio for {conn.pool_key}: {e}")

    async def close_all(self):
        """Close all pooled connections. Call on shutdown."""
        for pool_key, pool in self._pools.items():
            for conn in pool:
                await self._close_connection(conn)
            pool.clear()
        self._pools.clear()
        logger.info("Closed all pooled MCP connections")

    def stats(self) -> dict:
        """Get pool statistics."""
        total = sum(len(p) for p in self._pools.values())
        in_use = sum(sum(1 for c in p if c.in_use) for p in self._pools.values())
        return {"total": total, "in_use": in_use, "idle": total - in_use, "keys": len(self._pools)}


# Global connection pool instance
_connection_pool = MCPConnectionPool(max_per_key=3, idle_timeout=300.0)


def _write_google_workspace_credentials(credentials: Dict[str, Any]) -> Optional[str]:
    """
    Write Google OAuth credentials to workspace-mcp's expected location.

    The workspace-mcp connector expects credentials at:
    ~/.google_workspace_mcp/credentials/{email}.json

    Returns the email if successful, None if failed.
    """
    try:
        email = credentials.get("google_email")
        if not email:
            logger.warning("No google_email in credentials, cannot write to workspace-mcp location")
            return None

        # Build the credential file path
        home_dir = os.path.expanduser("~")
        creds_dir = os.path.join(home_dir, ".google_workspace_mcp", "credentials")
        os.makedirs(creds_dir, exist_ok=True)

        creds_file = os.path.join(creds_dir, f"{email}.json")

        # Build the credentials in workspace-mcp expected format
        workspace_creds = {
            "token": credentials.get("google_access_token"),
            "refresh_token": credentials.get("google_refresh_token"),
            "token_uri": credentials.get("token_uri", "https://oauth2.googleapis.com/token"),
            "client_id": credentials.get("client_id"),
            "client_secret": credentials.get("client_secret"),
            "scopes": credentials.get("scopes", []),
            "expiry": credentials.get("expires_at"),
        }

        # Write to file
        with open(creds_file, "w") as f:
            json.dump(workspace_creds, f, indent=2)

        logger.info(f"Wrote Google Workspace credentials for {email} to {creds_file}")
        return email

    except Exception as e:
        logger.error(f"Failed to write Google Workspace credentials: {e}")
        return None


async def _get_google_email_for_user(
    user_id: Optional[str],
    session_id: Optional[str],
    db: Optional[Any],
) -> Optional[str]:
    """
    Get the Google email for a user from their stored OAuth credentials.

    This is needed because Google Workspace tools require user_google_email parameter,
    and we need to inject it from the user's OAuth credentials, not from global config.

    Priority:
    1. User's OAuth credentials (from database)
    2. settings.user_google_email (only if no user context)

    Returns the email if found, None otherwise.
    """
    try:
        # Get user credentials from database
        credentials = None
        if user_id and db:
            credentials = await credential_service.get_credentials(
                datasource="google_workspace",
                db=db,
                user_id=user_id,
            )
            if credentials:
                email = credentials.get("google_email")
                if email:
                    logger.info(f"Using OAuth email for user {user_id[:8]}...: {email}")
                    return email
                else:
                    logger.warning(f"User {user_id[:8]}... has Google credentials but no google_email field")
        elif session_id:
            credentials = await credential_service.get_credentials(
                datasource="google_workspace",
                session_id=session_id,
            )
            if credentials:
                email = credentials.get("google_email")
                if email:
                    logger.info(f"Using OAuth email for session {session_id[:8]}...: {email}")
                    return email

        # Only fallback to settings if NO user credentials exist
        # (i.e., user hasn't connected Google yet, dev/test mode)
        if not credentials and settings.user_google_email:
            logger.info(f"No user OAuth credentials, using settings.user_google_email: {settings.user_google_email}")
            return settings.user_google_email

        return None
    except Exception as e:
        logger.warning(f"Failed to get Google email for user: {e}")
        # Don't fall back to settings on error - that could cause wrong email to be used
        return None


# Cache for tools to avoid repeated list_tools calls
TOOLS_CACHE: Dict[str, Dict[str, Any]] = {}  # {datasource: {"tools": [...], "timestamp": float}}
TOOLS_CACHE_TTL = 300  # 5 minutes TTL for tool cache
TOOLS_CACHE_MAX_SIZE = 50  # Max datasources to cache (prevents unbounded growth)
TOOLS_CACHE_LOCK = asyncio.Lock()  # Thread-safe access to tools cache

# Schema cache for MySQL tables (longer TTL - schemas don't change often)
SCHEMA_CACHE: Dict[str, Dict[str, Any]] = {}  # {table_name: {"columns": [...], "timestamp": float}}
SCHEMA_CACHE_TTL = 600  # 10 minutes TTL for schema cache
SCHEMA_CACHE_MAX_SIZE = 200  # Max tables to cache (prevents unbounded growth)
SCHEMA_CACHE_LOCK = asyncio.Lock()  # Thread-safe access to schema cache


def _evict_oldest_from_cache(cache: Dict[str, Dict[str, Any]], max_size: int) -> None:
    """Evict oldest entries from cache to stay under max size."""
    if len(cache) <= max_size:
        return
    # Sort by timestamp and remove oldest entries
    sorted_keys = sorted(cache.keys(), key=lambda k: cache[k].get("timestamp", 0))
    num_to_remove = len(cache) - max_size
    for key in sorted_keys[:num_to_remove]:
        del cache[key]
    logger.debug(f"Evicted {num_to_remove} old entries from cache")

# Connection idle timeout for persistent sessions
CONNECTION_IDLE_TIMEOUT = 300  # 5 minutes - close idle connections to free resources

# MCP tool call timeout - prevents indefinite hangs on unresponsive connectors
MCP_TOOL_CALL_TIMEOUT = 30.0  # 30 seconds


class MCPService:
    """Service for managing MCP connector clients."""

    def __init__(self):
        """Initialize MCP service using connector registry."""
        self._active_clients: Dict[str, tuple] = {}
        self._connection_locks: Dict[str, asyncio.Lock] = {}  # Per-datasource locks
        self._python_cmd = sys.executable

    def _get_connector_config(self, connector_id: str) -> Optional[Dict[str, Any]]:
        """
        Get connector configuration from registry.

        Returns dict with: command, args, env (default env from settings)
        """
        connector = get_connector(connector_id)
        if not connector:
            return None

        command, args = connector.get_server_command()

        # Get default environment from settings
        default_env = connector.get_default_env_from_settings(settings)

        # Merge with additional env from connector
        env = {**default_env, **connector.additional_env}

        return {
            "command": command,
            "args": args,
            "env": env,
        }

    def get_connector_ids(self) -> List[str]:
        """Get list of all available connector IDs."""
        return list(get_all_connectors().keys())

    def get_available_datasources(self) -> List[dict]:
        """Get list of available data sources from registry."""
        return registry_get_available_datasources()

    def _is_auth_error(self, result_content: List[Any]) -> bool:
        """Check if the result contains an authentication error (e.g., expired token)."""
        if not result_content:
            return False

        for content in result_content:
            if hasattr(content, 'text'):
                text = content.text
                # Check for structured JSON error response from connector
                if 'AUTH_ERROR_401' in text or '"requires_reauth": true' in text:
                    return True
                # Check for common error patterns
                if self._is_auth_error_message(text):
                    return True
        return False

    def _is_auth_error_message(self, text: str) -> bool:
        """Check if a text message indicates an auth error."""
        text_lower = text.lower()
        auth_error_patterns = [
            '401',
            'unauthorized',
            'authentication failed',
            'token expired',
            'invalid token',
            'access denied',
            'jira error: 401',
            'failure_client_auth',
            'http 401',
            'auth_error_401',
            'requires_reauth',
        ]
        return any(pattern in text_lower for pattern in auth_error_patterns)

    def _is_auth_error_exception(self, exc: Exception) -> bool:
        """Check if an exception (including nested ones) indicates an auth error."""
        # Check the main exception message
        if self._is_auth_error_message(str(exc)):
            return True

        # Check for ExceptionGroup/TaskGroup with nested exceptions
        if hasattr(exc, 'exceptions'):
            for nested_exc in exc.exceptions:
                if self._is_auth_error_message(str(nested_exc)):
                    return True
                # Recursively check nested groups
                if self._is_auth_error_exception(nested_exc):
                    return True

        # Check the __cause__ chain
        if exc.__cause__ and self._is_auth_error_message(str(exc.__cause__)):
            return True

        return False

    async def _try_refresh_oauth_token(
        self,
        datasource: str,
        user_id: str,
        db: any,
    ) -> bool:
        """
        Try to refresh OAuth token for a datasource.

        Returns True if token was successfully refreshed.
        """
        from app.services.user_oauth_service import user_oauth_service

        try:
            # Get current credentials
            current_creds = await credential_service.get_credentials(
                datasource=datasource,
                db=db,
                user_id=user_id,
            )

            if not current_creds:
                logger.warning(f"No credentials found for {datasource} to refresh")
                return False

            # Check if this is an OAuth credential with refresh token
            if current_creds.get("oauth_type") != "user":
                logger.info(f"Credentials for {datasource} are not OAuth, skipping refresh")
                return False

            # Refresh based on datasource
            if datasource.lower() == "jira":
                refreshed_creds = await user_oauth_service.refresh_jira_credentials(current_creds)
            else:
                logger.warning(f"Token refresh not implemented for {datasource}")
                return False

            if not refreshed_creds:
                logger.warning(f"Failed to refresh token for {datasource}")
                return False

            # Save the refreshed credentials
            await credential_service.save_credentials(
                datasource=datasource,
                credentials=refreshed_creds,
                db=db,
                user_id=user_id,
            )

            logger.info(f"Successfully refreshed and saved new token for {datasource}")
            return True

        except Exception as e:
            logger.error(f"Error refreshing OAuth token for {datasource}: {e}")
            return False

    async def _check_and_refresh_token_if_expiring(
        self,
        datasource: str,
        user_id: str,
        db: any,
        minutes_threshold: int = 5,
    ) -> bool:
        """
        PROACTIVE token refresh - check if token is about to expire and refresh BEFORE it does.

        This provides a smoother UX by avoiding the error-then-retry pattern.

        Args:
            datasource: The datasource to check
            user_id: The user's ID
            db: Database session
            minutes_threshold: Refresh if token expires within this many minutes (default 5)

        Returns:
            True if token was refreshed, False otherwise (including if no refresh needed)
        """
        try:
            # Only check OAuth-required datasources
            if datasource.lower() not in self.OAUTH_REQUIRED_DATASOURCES:
                return False

            # Get current credentials
            current_creds = await credential_service.get_credentials(
                datasource=datasource,
                db=db,
                user_id=user_id,
            )

            if not current_creds:
                return False

            # Check if this is an OAuth credential
            if current_creds.get("oauth_type") != "user":
                return False

            # Check for expires_at field
            expires_at_str = current_creds.get("expires_at")
            if not expires_at_str:
                logger.debug(f"No expires_at field for {datasource}, skipping proactive refresh")
                return False

            # Parse expiry time
            try:
                # Handle both formats: with and without timezone
                if expires_at_str.endswith('Z'):
                    expires_at_str = expires_at_str[:-1] + '+00:00'
                expires_at = datetime.fromisoformat(expires_at_str)

                # Ensure timezone-aware
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse expires_at '{expires_at_str}': {e}")
                return False

            # Calculate time until expiry
            now = datetime.now(timezone.utc)
            time_until_expiry = expires_at - now
            minutes_until_expiry = time_until_expiry.total_seconds() / 60

            # Check if token is expiring soon
            if minutes_until_expiry > minutes_threshold:
                logger.debug(
                    f"{datasource} token valid for {minutes_until_expiry:.1f} more minutes, no refresh needed"
                )
                return False

            # Token is expiring soon - proactively refresh
            if minutes_until_expiry > 0:
                logger.info(
                    f"🔄 PROACTIVE REFRESH: {datasource} token expires in {minutes_until_expiry:.1f} minutes, refreshing now..."
                )
            else:
                logger.warning(
                    f"⚠️ {datasource} token already expired {abs(minutes_until_expiry):.1f} minutes ago, attempting refresh..."
                )

            # Attempt refresh
            refreshed = await self._try_refresh_oauth_token(datasource, user_id, db)

            if refreshed:
                logger.info(f"✅ Proactive token refresh successful for {datasource}")
            else:
                logger.warning(f"❌ Proactive token refresh failed for {datasource}")

            return refreshed

        except Exception as e:
            logger.error(f"Error in proactive token check for {datasource}: {e}")
            return False

    async def get_cached_tools(self, datasource: str) -> List[dict]:
        """
        Get tools for a datasource with caching (thread-safe).
        This significantly reduces latency for repeated tool lookups.
        """
        now = time.time()

        # Check cache first (with lock for thread-safety)
        async with TOOLS_CACHE_LOCK:
            if datasource in TOOLS_CACHE:
                cached = TOOLS_CACHE[datasource]
                if now - cached["timestamp"] < TOOLS_CACHE_TTL:
                    logger.info(f"Using cached tools for {datasource} (age: {now - cached['timestamp']:.0f}s)")
                    return cached["tools"]

        # Cache miss - fetch tools (outside lock to avoid blocking)
        start = time.time()
        try:
            async with self.get_client(datasource) as session:
                tools_result = await session.list_tools()
                tools = [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema,
                    }
                    for tool in tools_result.tools
                ]

                # Update cache (with lock)
                async with TOOLS_CACHE_LOCK:
                    TOOLS_CACHE[datasource] = {
                        "tools": tools,
                        "timestamp": now,
                    }
                    # Evict old entries if cache is too large
                    _evict_oldest_from_cache(TOOLS_CACHE, TOOLS_CACHE_MAX_SIZE)

                elapsed = time.time() - start
                logger.info(f"Fetched and cached {len(tools)} tools for {datasource} in {elapsed:.2f}s")
                return tools

        except asyncio.TimeoutError:
            logger.error(f"Timeout getting tools for {datasource}")
            return []
        except (ConnectionError, OSError) as e:
            logger.error(f"Connection error getting tools for {datasource}: {e}")
            return []
        except ValueError as e:
            # For OAuth-required datasources, return static tool definitions
            # so Claude knows what tools are available even without credentials
            logger.warning(f"Cannot connect to {datasource} for tools (OAuth required): {e}")
            static_tools = self._get_static_tools_for_oauth_datasource(datasource)
            if static_tools:
                logger.info(f"Using {len(static_tools)} static tools for {datasource}")
                return static_tools
            return []

    async def prewarm_connections(self, datasources: List[str] = None):
        """
        Pre-warm connections and cache tools for faster first requests.
        Call this at startup to reduce latency.
        """
        if datasources is None:
            datasources = self.get_connector_ids()

        logger.info(f"🔥 Pre-warming connections for: {datasources}")
        start = time.time()

        async def prewarm_single(ds: str):
            try:
                await self.get_cached_tools(ds)
                logger.info(f"✅ Pre-warmed {ds}")
            except (asyncio.TimeoutError, ConnectionError, OSError) as e:
                logger.warning(f"⚠️ Failed to pre-warm {ds}: {e}")

        # Pre-warm all in parallel
        await asyncio.gather(*[prewarm_single(ds) for ds in datasources], return_exceptions=True)

        elapsed = time.time() - start
        logger.info(f"🔥 Pre-warming completed in {elapsed:.2f}s")

    # Datasources that require per-user OAuth (no fallback to default credentials)
    OAUTH_REQUIRED_DATASOURCES = {"slack", "github", "jira", "google_workspace"}

    def _get_static_tools_for_oauth_datasource(self, datasource: str) -> List[dict]:
        """
        Return static tool definitions for OAuth-required datasources.
        This allows Claude to know what tools are available even when
        credentials aren't available for connecting to the server.
        """
        # GitHub tools (Official GitHub MCP Server v0.29.0)
        if datasource.lower() == "github":
            return [
                {"name": "get_me", "description": "Get the authenticated user's profile information", "input_schema": {"type": "object", "properties": {}}},
                {"name": "search_repositories", "description": "Search for repositories. Use 'user:USERNAME' to find a user's repos", "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "Search query"}}, "required": ["query"]}},
                {"name": "get_file_contents", "description": "Get contents of a file from a repository", "input_schema": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}}, "required": ["owner", "repo", "path"]}},
                {"name": "list_issues", "description": "List issues in a repository", "input_schema": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "state": {"type": "string", "enum": ["open", "closed", "all"]}}, "required": ["owner", "repo"]}},
                {"name": "list_pull_requests", "description": "List pull requests in a repository", "input_schema": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "state": {"type": "string", "enum": ["open", "closed", "all"]}}, "required": ["owner", "repo"]}},
                {"name": "search_issues", "description": "Search for issues across repositories", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
                {"name": "search_code", "description": "Search for code across repositories", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
                {"name": "list_branches", "description": "List branches in a repository", "input_schema": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}},
                {"name": "list_commits", "description": "List commits in a repository", "input_schema": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}},
            ]

        # Slack tools (consolidated)
        if datasource.lower() == "slack":
            return [
                {"name": "find_messages", "description": "Find Slack messages. Provide user, channel, query, or combination. Smart routing picks the best strategy.", "input_schema": {"type": "object", "properties": {"user": {"type": "string", "description": "Person's name"}, "channel": {"type": "string", "description": "Channel name"}, "query": {"type": "string", "description": "Search keyword"}, "dm_with": {"type": "boolean", "description": "Read DM conversation with user"}, "hours_ago": {"type": "integer", "default": 48}, "limit": {"type": "integer", "default": 50}}}},
                {"name": "get_slack_summary", "description": "Get summary of ALL recent Slack activity across DMs and channels. Use for 'catch me up', 'what did I miss'.", "input_schema": {"type": "object", "properties": {"hours_ago": {"type": "integer", "default": 24}}}},
                {"name": "list_channels", "description": "List all Slack channels", "input_schema": {"type": "object", "properties": {}}},
                {"name": "list_users", "description": "List all Slack users in the workspace", "input_schema": {"type": "object", "properties": {}}},
                {"name": "send_message", "description": "Send a message to a channel", "input_schema": {"type": "object", "properties": {"channel": {"type": "string"}, "text": {"type": "string"}}, "required": ["channel", "text"]}},
                {"name": "send_dm", "description": "Send a direct message to a user", "input_schema": {"type": "object", "properties": {"user": {"type": "string"}, "text": {"type": "string"}}, "required": ["user", "text"]}},
            ]

        # JIRA tools
        if datasource.lower() == "jira":
            return [
                {"name": "list_projects", "description": "List all JIRA projects", "input_schema": {"type": "object", "properties": {}}},
                {"name": "query_jira", "description": "Natural language query for JIRA issues", "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "Natural language query"}}, "required": ["query"]}},
                {"name": "get_issue", "description": "Get details of a specific issue", "input_schema": {"type": "object", "properties": {"issue_key": {"type": "string"}}, "required": ["issue_key"]}},
                {"name": "search_issues", "description": "Search issues with JQL", "input_schema": {"type": "object", "properties": {"jql": {"type": "string"}}, "required": ["jql"]}},
            ]

        # Google Workspace tools (must match actual MCP server tool names)
        if datasource.lower() == "google_workspace":
            return [
                {"name": "list_calendars", "description": "List calendars accessible to the user", "input_schema": {"type": "object", "properties": {"user_google_email": {"type": "string"}}, "required": ["user_google_email"]}},
                {"name": "get_events", "description": "Get calendar events from a specified calendar", "input_schema": {"type": "object", "properties": {"user_google_email": {"type": "string"}, "calendar_id": {"type": "string"}, "time_min": {"type": "string"}, "time_max": {"type": "string"}}, "required": ["user_google_email"]}},
                {"name": "create_event", "description": "Create a new calendar event", "input_schema": {"type": "object", "properties": {"user_google_email": {"type": "string"}, "summary": {"type": "string"}, "start_time": {"type": "string"}, "end_time": {"type": "string"}}, "required": ["user_google_email", "summary", "start_time", "end_time"]}},
                {"name": "search_drive_files", "description": "Search for files in Google Drive", "input_schema": {"type": "object", "properties": {"user_google_email": {"type": "string"}, "query": {"type": "string"}}, "required": ["user_google_email"]}},
                {"name": "get_drive_file_content", "description": "Get content of a Google Drive file by ID", "input_schema": {"type": "object", "properties": {"user_google_email": {"type": "string"}, "file_id": {"type": "string"}}, "required": ["user_google_email", "file_id"]}},
                {"name": "search_gmail_messages", "description": "Search messages in Gmail based on a query. Returns message IDs, subjects, senders, and snippets. The query parameter uses Gmail search syntax (e.g. 'from:person', 'subject:topic', 'newer_than:7d').", "input_schema": {"type": "object", "properties": {"user_google_email": {"type": "string"}, "query": {"type": "string", "description": "Gmail search query. Examples: 'from:krishnan', 'newer_than:7d', 'subject:meeting'. Required."}, "max_results": {"type": "integer"}}, "required": ["user_google_email", "query"]}},
                {"name": "get_gmail_message_content", "description": "Get full content (subject, sender, recipients, body) of a specific Gmail message by ID", "input_schema": {"type": "object", "properties": {"user_google_email": {"type": "string"}, "message_id": {"type": "string"}}, "required": ["user_google_email", "message_id"]}},
                {"name": "get_gmail_messages_content_batch", "description": "Get content of multiple Gmail messages in a single batch request", "input_schema": {"type": "object", "properties": {"user_google_email": {"type": "string"}, "message_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["user_google_email", "message_ids"]}},
                {"name": "send_gmail_message", "description": "Send an email using Gmail. Supports new emails and replies.", "input_schema": {"type": "object", "properties": {"user_google_email": {"type": "string"}, "to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["user_google_email", "to", "subject", "body"]}},
                {"name": "get_doc_content", "description": "Get content of a Google Doc by document ID", "input_schema": {"type": "object", "properties": {"user_google_email": {"type": "string"}, "document_id": {"type": "string"}}, "required": ["user_google_email", "document_id"]}},
                {"name": "read_sheet_values", "description": "Read values from a Google Sheet range", "input_schema": {"type": "object", "properties": {"user_google_email": {"type": "string"}, "spreadsheet_id": {"type": "string"}, "range": {"type": "string"}}, "required": ["user_google_email", "spreadsheet_id", "range"]}},
                {"name": "list_tasks", "description": "List all tasks in a specific task list", "input_schema": {"type": "object", "properties": {"user_google_email": {"type": "string"}}, "required": ["user_google_email"]}},
                {"name": "create_task", "description": "Create a new task in a task list", "input_schema": {"type": "object", "properties": {"user_google_email": {"type": "string"}, "title": {"type": "string"}}, "required": ["user_google_email", "title"]}},
            ]

        return []

    async def _get_connector_env(
        self,
        datasource: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        db: Optional[any] = None,
    ) -> dict:
        """
        Get environment variables for a connector, merging user credentials
        with defaults from settings.

        Uses the connector registry to map credential fields to env vars.
        Prioritizes user_id credentials over session_id credentials.

        For OAuth-required datasources (slack, github, jira), user must have
        connected their own account - no fallback to default credentials.
        """
        # Get connector from registry
        connector = get_connector(datasource)
        if not connector:
            raise ValueError(f"Unknown data source: {datasource}")

        # Check if this datasource requires OAuth (no fallback to defaults)
        is_oauth_required = datasource.lower() in self.OAUTH_REQUIRED_DATASOURCES

        # Debug logging
        logger.info(f"_get_connector_env: datasource={datasource}, user_id={user_id[:8] if user_id else None}..., session_id={session_id[:8] if session_id else None}..., db={db is not None}")

        # Prioritize user_id over session_id
        if user_id:
            user_credentials = await credential_service.get_credentials(
                datasource=datasource,
                db=db,
                user_id=user_id,
            )
            logger.info(f"_get_connector_env: user_id path, got credentials: {user_credentials is not None}")
        elif session_id:
            user_credentials = await credential_service.get_credentials(
                datasource=datasource,
                session_id=session_id,
            )
            logger.info(f"_get_connector_env: session_id path, got credentials: {user_credentials is not None}")
        else:
            user_credentials = None
            logger.info(f"_get_connector_env: no user_id or session_id, credentials=None")

        # For OAuth-required datasources, user should have their own credentials,
        # but we can fall back to default env credentials if they exist (dev/test mode)
        if is_oauth_required:
            if not user_credentials:
                # Check if default credentials exist in environment
                default_env = connector.get_default_env_from_settings(settings)
                has_default_credentials = default_env and any(v for v in default_env.values() if v)

                if has_default_credentials:
                    logger.info(f"Using default env credentials for {datasource} (no user OAuth, fallback mode)")
                    default_env.update(connector.additional_env)
                    return default_env
                else:
                    raise ValueError(
                        f"{datasource} requires you to connect your account via OAuth. "
                        f"Please go to Settings and click 'Connect with {datasource}'."
                    )

            # Special handling for Google Workspace: write credentials to workspace-mcp location
            if datasource.lower() == "google_workspace":
                email = _write_google_workspace_credentials(user_credentials)
                if email:
                    # Start with default settings (contains GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET)
                    # These are needed by the MCP connector even when using user OAuth tokens
                    env = connector.get_default_env_from_settings(settings)

                    # Override with user-specific settings
                    env["USER_GOOGLE_EMAIL"] = email

                    # Also pass client_id/client_secret from user credentials if available
                    # (they're stored with different key names in the database)
                    if user_credentials.get("client_id"):
                        env["GOOGLE_OAUTH_CLIENT_ID"] = user_credentials["client_id"]
                    if user_credentials.get("client_secret"):
                        env["GOOGLE_OAUTH_CLIENT_SECRET"] = user_credentials["client_secret"]

                    env.update(connector.additional_env)
                    logger.info(f"Using Google OAuth credentials for {email} (client_id present: {bool(env.get('GOOGLE_OAUTH_CLIENT_ID'))})")
                    return env
                else:
                    raise ValueError(
                        "Google Workspace OAuth credentials missing email. "
                        "Please reconnect via Settings."
                    )

            # Only use user credentials (no defaults)
            env = connector.get_env_from_credentials(user_credentials)
            env.update(connector.additional_env)
            logger.info(f"Using OAuth credentials for {datasource}")
            return env

        # For non-OAuth datasources, start with defaults and override with user creds
        env = connector.get_default_env_from_settings(settings)
        env.update(connector.additional_env)

        if user_credentials:
            user_env = connector.get_env_from_credentials(user_credentials)
            env.update(user_env)
            credential_type = "user" if user_id else "session"
            logger.info(f"Using {credential_type} credentials for {datasource}")

        return env

    def _inject_docker_env_vars(self, args: List[str], env_vars: dict) -> List[str]:
        """
        Inject environment variables as -e KEY=VALUE flags into Docker run args.

        Docker containers don't inherit environment variables from the parent process,
        so we need to explicitly pass them via -e flags.

        Args:
            args: Original docker run arguments
            env_vars: Environment variables to inject

        Returns:
            Modified args list with -e flags inserted before the image name
        """
        if not env_vars:
            return args

        # Find the image name (last arg that doesn't start with -)
        # Insert -e flags right before the image name
        new_args = []
        image_index = -1

        # Find where the image name is (typically after all flags)
        for i, arg in enumerate(args):
            if arg == "run":
                continue
            # Skip flag values
            if i > 0 and args[i-1] in ["-e", "--env", "-v", "--volume", "-p", "--publish", "--name"]:
                continue
            # If it doesn't start with - and isn't a flag value, it's likely the image
            if not arg.startswith("-") and "/" in arg or ":" in arg or "." in arg:
                image_index = i
                break
            # Also check for image names without special chars (like 'postgres')
            if not arg.startswith("-") and i > 0 and not args[i-1].startswith("-"):
                image_index = i
                break

        if image_index == -1:
            # Couldn't find image, just append to end before last element
            image_index = len(args) - 1

        # Build new args: everything before image, then -e flags, then image and rest
        new_args = list(args[:image_index])

        # Add -e flags for each env var
        for key, value in env_vars.items():
            new_args.extend(["-e", f"{key}={value}"])

        # Add the rest (image name and any commands after)
        new_args.extend(args[image_index:])

        logger.info(f"Docker args with env vars: {' '.join(new_args[:10])}...")
        return new_args

    @asynccontextmanager
    async def get_client(
        self,
        datasource: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        db: Optional[any] = None,
    ):
        """
        Get or create an MCP client for the specified data source.

        Args:
            datasource: The data source to connect to
            user_id: Optional user ID for authenticated users
            session_id: Optional session ID for anonymous users
            db: Optional database session for retrieving user credentials
        """
        # Get connector from registry
        connector = get_connector(datasource)
        if not connector:
            raise ValueError(f"Unknown data source: {datasource}")

        # Get server command from connector
        command, args = connector.get_server_command()

        # Get environment variables (with user credentials if available)
        # Prioritizes user_id over session_id
        connector_env = await self._get_connector_env(datasource, user_id, session_id, db=db)

        # For Docker-based connectors, inject env vars as -e flags
        # Docker doesn't inherit subprocess env vars into the container
        if command == "docker" and "run" in args:
            args = self._inject_docker_env_vars(args, connector_env)
            # Don't pass connector_env to subprocess since it's now in docker args
            final_env = os.environ.copy()
        else:
            final_env = {**os.environ.copy(), **connector_env}

        # Create server parameters
        server = StdioServerParameters(
            command=command,
            args=args,
            env=final_env,
        )

        # Create client session
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize the connection
                await session.initialize()
                logger.info(f"Connected to {datasource} MCP server")

                try:
                    yield session
                finally:
                    logger.info(f"Disconnected from {datasource} MCP server")

    async def test_connection(
        self,
        datasource: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        db: Optional[any] = None,
    ) -> dict:
        """
        Test connection to a data source.

        Args:
            datasource: The data source to test
            user_id: Optional user ID for authenticated users
            session_id: Optional session ID for anonymous users
            db: Optional database session for retrieving user credentials
        """
        try:
            async with self.get_client(datasource, user_id, session_id, db=db) as session:
                # Try to list available tools as a connection test
                tools_result = await session.list_tools()

                return {
                    "datasource": datasource,
                    "connected": True,
                    "message": "Connection successful",
                    "details": {
                        "tools_count": len(tools_result.tools) if tools_result else 0,
                    },
                }
        except asyncio.TimeoutError:
            logger.error(f"Connection test timed out for {datasource}")
            return {
                "datasource": datasource,
                "connected": False,
                "message": "Connection timed out",
                "details": {},
            }
        except (ConnectionError, OSError) as e:
            logger.error(f"Connection test failed for {datasource}: {str(e)}")
            return {
                "datasource": datasource,
                "connected": False,
                "message": f"Connection failed: {str(e)}",
                "details": {},
            }
        except ValueError as e:
            logger.error(f"Invalid configuration for {datasource}: {str(e)}")
            return {
                "datasource": datasource,
                "connected": False,
                "message": f"Configuration error: {str(e)}",
                "details": {},
            }

    async def call_tool(
        self,
        datasource: str,
        tool_name: str,
        arguments: dict,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        db: Optional[any] = None,
        force_refresh: bool = False,
    ) -> List[Any]:
        """
        Call a tool on the specified data source.
        Uses caching for speed with optional force refresh.

        Args:
            datasource: The data source to call the tool on
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool
            user_id: Optional user ID for authenticated users
            session_id: Optional session ID for anonymous users
            db: Optional database session for retrieving user credentials
            force_refresh: If True, bypasses cache and fetches fresh data
        """
        # Get circuit breaker for this datasource
        breaker = get_mcp_breaker(datasource)

        # Check if circuit is open before attempting call
        if not breaker.is_available():
            stats = breaker.get_stats()
            raise CircuitOpenError(
                f"Service {datasource} is temporarily unavailable. "
                f"Retry in {stats['seconds_until_retry']:.0f}s"
            )

        # Try to use fast path with caching
        try:
            result = await self.call_tool_fast(
                datasource, tool_name, arguments, user_id, session_id, db, force_refresh
            )
            await breaker.record_success()
            return result
        except CircuitOpenError:
            raise  # Don't record circuit errors as failures
        except (asyncio.TimeoutError, ConnectionError, OSError) as e:
            await breaker.record_failure(e)
            logger.warning(f"Fast path failed for {datasource}, falling back to standard: {e}")

            # Check if circuit is still available after recording failure
            if not breaker.is_available():
                stats = breaker.get_stats()
                raise CircuitOpenError(
                    f"Service {datasource} is temporarily unavailable after failure. "
                    f"Retry in {stats['seconds_until_retry']:.0f}s"
                )

            # Fallback to standard connection with circuit breaker protection
            try:
                async with self.get_client(datasource, user_id, session_id, db=db) as session:
                    result = await asyncio.wait_for(
                        session.call_tool(tool_name, arguments),
                        timeout=MCP_TOOL_CALL_TIMEOUT
                    )
                    await breaker.record_success()
                    return result.content if result else []
            except (asyncio.TimeoutError, ConnectionError, OSError) as fallback_error:
                await breaker.record_failure(fallback_error)
                raise

    def _build_server_params(self, datasource: str, connector_env: dict) -> StdioServerParameters:
        """Build StdioServerParameters for a datasource with the given env."""
        connector = get_connector(datasource)
        if not connector:
            raise ValueError(f"Unknown data source: {datasource}")

        command, args = connector.get_server_command()

        # For Docker-based connectors, inject env vars as -e flags
        if command == "docker" and "run" in args:
            args = self._inject_docker_env_vars(args, connector_env)
            final_env = os.environ.copy()
        else:
            final_env = {**os.environ.copy(), **connector_env}

        return StdioServerParameters(command=command, args=args, env=final_env)

    async def call_tool_fast(
        self,
        datasource: str,
        tool_name: str,
        arguments: dict,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        db: Optional[any] = None,
        force_refresh: bool = False,
    ) -> List[Any]:
        """
        Tool call using connection pooling for speed.
        Reuses MCP subprocess connections to save 200-500ms per call.
        """
        start_time = time.time()

        # PROACTIVE TOKEN REFRESH - check if token is about to expire BEFORE making request
        if user_id and db:
            await self._check_and_refresh_token_if_expiring(datasource, user_id, db)

        # ALWAYS inject user_google_email FOR GOOGLE WORKSPACE TOOLS from OAuth credentials
        if datasource.lower() == "google_workspace":
            email = await _get_google_email_for_user(user_id, session_id, db)
            if email:
                arguments = arguments.copy()
                old_email = arguments.get("user_google_email", "(none)")
                arguments["user_google_email"] = email
                if old_email != email:
                    logger.info(f"✅ Overriding user_google_email: '{old_email}' → '{email}' for {tool_name}")
                else:
                    logger.info(f"✅ Confirmed user_google_email: {email} for {tool_name}")
            else:
                logger.warning(f"⚠️ Could not find Google email for user, tool {tool_name} may fail")

        # Build pool key and server params
        connector_env = await self._get_connector_env(datasource, user_id, session_id, db=db)
        pool_key = f"{datasource}:{user_id or session_id or 'default'}"
        server_params = self._build_server_params(datasource, connector_env)

        # Acquire pooled connection
        conn = await _connection_pool.acquire(datasource, pool_key, server_params)

        try:
            result = await asyncio.wait_for(
                conn.session.call_tool(tool_name, arguments),
                timeout=MCP_TOOL_CALL_TIMEOUT,
            )
            result_content = result.content if result else []
            elapsed = time.time() - start_time
            logger.info(f"⚡ call_tool ({datasource}/{tool_name}) in {elapsed*1000:.0f}ms [pooled]")

            # Check for OAuth token expiration and retry with refreshed token
            if user_id and db and self._is_auth_error(result_content):
                logger.warning(f"Detected auth error in result for {datasource}, attempting token refresh...")
                # Discard old connection (has stale credentials) and retry with fresh one
                await _connection_pool.discard(conn)
                conn = None

                refreshed = await self._try_refresh_oauth_token(datasource, user_id, db)
                if refreshed:
                    logger.info(f"Retrying {datasource}/{tool_name} with refreshed token...")
                    # Get fresh env and new connection
                    connector_env = await self._get_connector_env(datasource, user_id, session_id, db=db)
                    server_params = self._build_server_params(datasource, connector_env)
                    conn = await _connection_pool.acquire(datasource, pool_key, server_params)
                    result = await asyncio.wait_for(
                        conn.session.call_tool(tool_name, arguments),
                        timeout=MCP_TOOL_CALL_TIMEOUT,
                    )
                    result_content = result.content if result else []
                    logger.info(f"⚡ RETRY call_tool ({datasource}/{tool_name}) succeeded after token refresh [pooled]")

            return result_content

        except Exception as e:
            # Connection is likely broken — discard it
            if conn:
                await _connection_pool.discard(conn)
                conn = None

            error_msg = str(e)
            if hasattr(e, 'exceptions'):
                nested_errors = [str(nested) for nested in e.exceptions]
                error_msg = "; ".join(nested_errors[:3])
                logger.warning(f"ExceptionGroup for {datasource}/{tool_name}: {error_msg}")

            # Check if exception is an auth error — try refresh and retry
            if user_id and db and self._is_auth_error_exception(e):
                logger.warning(f"Detected auth error exception for {datasource}: {error_msg[:100]}...")
                refreshed = await self._try_refresh_oauth_token(datasource, user_id, db)
                if refreshed:
                    logger.info(f"Retrying {datasource}/{tool_name} with refreshed token after exception...")
                    try:
                        connector_env = await self._get_connector_env(datasource, user_id, session_id, db=db)
                        server_params = self._build_server_params(datasource, connector_env)
                        conn = await _connection_pool.acquire(datasource, pool_key, server_params)
                        result = await asyncio.wait_for(
                            conn.session.call_tool(tool_name, arguments),
                            timeout=MCP_TOOL_CALL_TIMEOUT,
                        )
                        result_content = result.content if result else []
                        elapsed = time.time() - start_time
                        logger.info(f"⚡ RETRY call_tool ({datasource}/{tool_name}) succeeded in {elapsed*1000:.0f}ms [pooled]")
                        await _connection_pool.release(conn)
                        return result_content
                    except Exception as retry_error:
                        if conn:
                            await _connection_pool.discard(conn)
                        logger.error(f"Retry after token refresh also failed: {retry_error}")
                        raise retry_error
                else:
                    logger.error(f"Token refresh failed for {datasource}, re-raising original error")
            raise

        finally:
            # Release connection back to pool (if not already discarded)
            if conn:
                await _connection_pool.release(conn)

    async def shutdown(self):
        """Shutdown the service and close all pooled connections."""
        await _connection_pool.close_all()
        logger.info("MCP service shut down")

    # ==================== Schema Caching for MySQL ====================

    def get_cached_schema(self, table_name: str) -> Optional[str]:
        """Get cached schema for a table if available."""
        if table_name in SCHEMA_CACHE:
            cached = SCHEMA_CACHE[table_name]
            if time.time() - cached["timestamp"] < SCHEMA_CACHE_TTL:
                return cached["columns"]
        return None

    def cache_schema(self, table_name: str, columns: str):
        """Cache a table schema."""
        SCHEMA_CACHE[table_name] = {
            "columns": columns,
            "timestamp": time.time(),
        }
        # Evict old entries if cache is too large
        _evict_oldest_from_cache(SCHEMA_CACHE, SCHEMA_CACHE_MAX_SIZE)
        logger.info(f"Cached schema for {table_name}")

    def get_all_cached_schemas(self) -> Dict[str, str]:
        """Get all cached schemas that are still valid."""
        now = time.time()
        valid_schemas = {}
        for table_name, cached in SCHEMA_CACHE.items():
            if now - cached["timestamp"] < SCHEMA_CACHE_TTL:
                valid_schemas[table_name] = cached["columns"]
        return valid_schemas

    async def prefetch_mysql_schemas(
        self,
        tables: List[str],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        db: Optional[any] = None,
    ) -> Dict[str, str]:
        """
        Pre-fetch schemas for commonly used tables.
        This eliminates the need for Claude to call describe_table.
        """
        schemas = {}
        tables_to_fetch = []

        # Check which tables need fetching
        for table in tables:
            cached = self.get_cached_schema(table)
            if cached:
                schemas[table] = cached
            else:
                tables_to_fetch.append(table)

        if not tables_to_fetch:
            logger.info(f"📋 All {len(tables)} schemas from cache")
            return schemas

        # Fetch missing schemas
        logger.info(f"📋 Fetching schemas for {len(tables_to_fetch)} tables...")
        start = time.time()

        async with self.get_client("mysql", user_id, session_id, db=db) as session:
            for table in tables_to_fetch:
                try:
                    result = await session.call_tool("describe_table", {"table": table})
                    if result and result.content:
                        schema_text = ""
                        for content in result.content:
                            if hasattr(content, "text"):
                                schema_text += content.text
                        schemas[table] = schema_text
                        self.cache_schema(table, schema_text)
                except Exception as e:
                    logger.warning(f"Failed to fetch schema for {table}: {e}")

        elapsed = time.time() - start
        logger.info(f"📋 Fetched {len(tables_to_fetch)} schemas in {elapsed:.2f}s")
        return schemas

    def format_schemas_for_prompt(self, schemas: Dict[str, str]) -> str:
        """Format cached schemas for inclusion in system prompt."""
        if not schemas:
            return ""

        lines = ["\n\n**CACHED TABLE SCHEMAS (use these exact column names):**\n"]
        for table_name, columns in schemas.items():
            # Parse the columns to extract just the column names
            lines.append(f"\n`{table_name}` columns:")
            # Only include first 500 chars of each schema to keep prompt short
            lines.append(columns[:500] if len(columns) > 500 else columns)

        return "\n".join(lines)


# Global MCP service instance
mcp_service = MCPService()
