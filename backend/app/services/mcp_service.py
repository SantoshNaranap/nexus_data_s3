"""MCP service for managing connector clients."""

import os
import asyncio
import time
import hashlib
import json
import sys
from datetime import datetime, timezone, timedelta
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
    get_connector_env,
    get_cacheable_tools,
    get_credential_env_mapping,
)

logger = logging.getLogger(__name__)

# Cache for tools to avoid repeated list_tools calls
TOOLS_CACHE: Dict[str, Dict[str, Any]] = {}  # {datasource: {"tools": [...], "timestamp": float}}
TOOLS_CACHE_TTL = 300  # 5 minutes TTL for tool cache
TOOLS_CACHE_MAX_SIZE = 50  # Max datasources to cache (prevents unbounded growth)
TOOLS_CACHE_LOCK = asyncio.Lock()  # Thread-safe access to tools cache

# Result cache for repeated queries (short TTL for freshness)
RESULT_CACHE: Dict[str, Dict[str, Any]] = {}  # {cache_key: {"result": [...], "timestamp": float}}
RESULT_CACHE_TTL = 30  # 30 seconds - short TTL for fresh data
RESULT_CACHE_MAX_SIZE = 100  # Max cached results
RESULT_CACHE_LOCK = asyncio.Lock()  # Thread-safe access to result cache

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
            logger.error(f"Invalid datasource configuration for {datasource}: {e}")
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
    OAUTH_REQUIRED_DATASOURCES = {"slack", "github", "jira"}

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

        # For OAuth-required datasources, user MUST have their own credentials
        if is_oauth_required:
            if not user_credentials:
                raise ValueError(
                    f"{datasource} requires you to connect your account via OAuth. "
                    f"Please go to Settings and click 'Connect with {datasource}'."
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

        # Create server parameters
        server = StdioServerParameters(
            command=command,
            args=args,
            env={**os.environ.copy(), **connector_env},
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

    def _get_cache_key(self, datasource: str, tool_name: str, arguments: dict) -> str:
        """Generate a cache key for result caching."""
        args_str = json.dumps(arguments, sort_keys=True)
        key_str = f"{datasource}:{tool_name}:{args_str}"
        return hashlib.md5(key_str.encode()).hexdigest()

    async def _check_result_cache(self, cache_key: str, force_refresh: bool = False) -> Optional[List[Any]]:
        """Check if we have a cached result (thread-safe)."""
        async with RESULT_CACHE_LOCK:
            if force_refresh:
                # User requested fresh data, skip cache
                if cache_key in RESULT_CACHE:
                    del RESULT_CACHE[cache_key]
                return None

            if cache_key in RESULT_CACHE:
                cached = RESULT_CACHE[cache_key]
                if time.time() - cached["timestamp"] < RESULT_CACHE_TTL:
                    return cached["result"]
                else:
                    # Expired, remove it
                    del RESULT_CACHE[cache_key]
            return None

    def should_force_refresh(self, message: str) -> bool:
        """
        Check if user is requesting fresh/updated data.
        Detects keywords like 'refresh', 'update', 'latest', 'new', 'current', etc.
        """
        refresh_keywords = [
            "refresh", "update", "reload", "fetch",
            "latest", "newest", "current", "now",
            "fresh", "new data", "sync", "resync",
            "check again", "look again", "re-check",
        ]
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in refresh_keywords)

    async def _store_result_cache(self, cache_key: str, result: List[Any]):
        """Store a result in the cache (thread-safe)."""
        async with RESULT_CACHE_LOCK:
            # Prune cache if too large
            if len(RESULT_CACHE) >= RESULT_CACHE_MAX_SIZE:
                # Remove oldest entries
                sorted_keys = sorted(RESULT_CACHE.keys(), key=lambda k: RESULT_CACHE[k]["timestamp"])
                for key in sorted_keys[:20]:  # Remove 20 oldest
                    del RESULT_CACHE[key]

            RESULT_CACHE[cache_key] = {
                "result": result,
                "timestamp": time.time(),
            }

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
        FAST tool call with result caching.
        Caches results for repeated queries (30s TTL).
        Uses fresh connections per call (MCP stdio doesn't support persistent connections well).

        Args:
            force_refresh: If True, bypasses cache and fetches fresh data
        """
        start_time = time.time()

        # PROACTIVE TOKEN REFRESH - check if token is about to expire BEFORE making request
        # This avoids the error-then-retry pattern and provides smoother UX
        if user_id and db:
            await self._check_and_refresh_token_if_expiring(datasource, user_id, db)

        # CHECK CACHE FIRST (instant return if cached)
        # Get cacheable tools from connector registry
        cacheable_tools = get_cacheable_tools(datasource)

        cache_key = None
        if tool_name in cacheable_tools:
            cache_key = self._get_cache_key(datasource, tool_name, arguments)
            cached_result = await self._check_result_cache(cache_key, force_refresh=force_refresh)
            if cached_result is not None:
                elapsed = time.time() - start_time
                logger.info(f"CACHED result ({datasource}/{tool_name}) in {elapsed*1000:.0f}ms")
                return cached_result
            elif force_refresh:
                logger.info(f"Force refresh requested for {datasource}/{tool_name}")

        # Use standard connection (MCP stdio doesn't support reuse well across tasks)
        try:
            async with self.get_client(datasource, user_id, session_id, db=db) as session:
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments),
                    timeout=MCP_TOOL_CALL_TIMEOUT
                )
                result_content = result.content if result else []
                elapsed = time.time() - start_time
                logger.info(f"⚡ FAST call_tool ({datasource}/{tool_name}) in {elapsed*1000:.0f}ms")

                # Check for OAuth token expiration and retry with refreshed token
                if user_id and db and self._is_auth_error(result_content):
                    logger.warning(f"Detected auth error in result for {datasource}, attempting token refresh...")
                    refreshed = await self._try_refresh_oauth_token(datasource, user_id, db)
                    if refreshed:
                        # Retry the call with refreshed credentials
                        logger.info(f"Retrying {datasource}/{tool_name} with refreshed token...")
                        async with self.get_client(datasource, user_id, session_id, db=db) as retry_session:
                            result = await asyncio.wait_for(
                                retry_session.call_tool(tool_name, arguments),
                                timeout=MCP_TOOL_CALL_TIMEOUT
                            )
                            result_content = result.content if result else []
                            logger.info(f"⚡ RETRY call_tool ({datasource}/{tool_name}) succeeded after token refresh")

                # Store in cache for future requests
                if cache_key:
                    await self._store_result_cache(cache_key, result_content)

                return result_content

        except Exception as e:
            # Check if exception is an auth error (e.g., 401, token expired)
            # Use _is_auth_error_exception to handle TaskGroup/ExceptionGroup with nested exceptions
            if user_id and db and self._is_auth_error_exception(e):
                logger.warning(f"Detected auth error exception for {datasource}: {str(e)[:100]}...")
                logger.info(f"Attempting token refresh for {datasource}...")
                refreshed = await self._try_refresh_oauth_token(datasource, user_id, db)
                if refreshed:
                    # Retry the call with refreshed credentials
                    logger.info(f"Retrying {datasource}/{tool_name} with refreshed token after exception...")
                    try:
                        async with self.get_client(datasource, user_id, session_id, db=db) as retry_session:
                            result = await asyncio.wait_for(
                                retry_session.call_tool(tool_name, arguments),
                                timeout=MCP_TOOL_CALL_TIMEOUT
                            )
                            result_content = result.content if result else []
                            elapsed = time.time() - start_time
                            logger.info(f"⚡ RETRY call_tool ({datasource}/{tool_name}) succeeded after token refresh in {elapsed*1000:.0f}ms")

                            # Store in cache for future requests
                            if cache_key:
                                await self._store_result_cache(cache_key, result_content)

                            return result_content
                    except Exception as retry_error:
                        logger.error(f"Retry after token refresh also failed: {retry_error}")
                        raise retry_error
                else:
                    logger.error(f"Token refresh failed for {datasource}, re-raising original error")
            # Re-raise the original exception if not an auth error or refresh failed
            raise

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
