"""MCP service for managing connector clients."""

import os
import asyncio
import time
import hashlib
import json
import sys
from typing import Dict, Optional, Any, List
import logging
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.core.config import settings
from app.services.credential_service import credential_service
from app.services.oauth_providers import is_oauth_provider
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

# Result cache for repeated queries (short TTL for freshness)
RESULT_CACHE: Dict[str, Dict[str, Any]] = {}  # {cache_key: {"result": [...], "timestamp": float}}
RESULT_CACHE_TTL = 30  # 30 seconds - short TTL for fresh data
RESULT_CACHE_MAX_SIZE = 100  # Max cached results

# Schema cache for MySQL tables (longer TTL - schemas don't change often)
SCHEMA_CACHE: Dict[str, Dict[str, Any]] = {}  # {table_name: {"columns": [...], "timestamp": float}}
SCHEMA_CACHE_TTL = 600  # 10 minutes TTL for schema cache


class MCPService:
    """Service for managing MCP connector clients."""

    def __init__(self):
        """Initialize MCP service using connector registry."""
        self._active_clients: Dict[str, tuple] = {}
        self._connection_locks: Dict[str, asyncio.Lock] = {}  # Per-datasource locks
        self._persistent_sessions: Dict[str, Dict[str, Any]] = {}  # Persistent connections
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

    async def get_cached_tools(self, datasource: str) -> List[dict]:
        """
        Get tools for a datasource with caching.
        This significantly reduces latency for repeated tool lookups.
        """
        now = time.time()

        # Check cache
        if datasource in TOOLS_CACHE:
            cached = TOOLS_CACHE[datasource]
            if now - cached["timestamp"] < TOOLS_CACHE_TTL:
                logger.info(f"⚡ Using cached tools for {datasource} (age: {now - cached['timestamp']:.0f}s)")
                return cached["tools"]

        # Cache miss - fetch tools
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

                # Update cache
                TOOLS_CACHE[datasource] = {
                    "tools": tools,
                    "timestamp": now,
                }

                elapsed = time.time() - start
                logger.info(f"⚡ Fetched and cached {len(tools)} tools for {datasource} in {elapsed:.2f}s")
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

        For OAuth providers (Google, Slack, GitHub): Fetches tokens from OAuthConnection table.
        For other providers: Uses the credential registry to map credential fields to env vars.
        Prioritizes user_id credentials over session_id credentials.
        """
        # Get connector from registry
        connector = get_connector(datasource)
        if not connector:
            raise ValueError(f"Unknown data source: {datasource}")

        # Start with defaults from settings
        env = connector.get_default_env_from_settings(settings)

        # Add additional env from connector
        env.update(connector.additional_env)

        # Check if this is an OAuth provider
        logger.info(f"Checking OAuth for {datasource}: is_oauth={is_oauth_provider(datasource)}, user_id={user_id is not None}, db={db is not None}")
        if is_oauth_provider(datasource) and user_id and db:
            # Use OAuth service for token retrieval
            from app.services.oauth_service import oauth_service

            try:
                logger.info(f"Fetching OAuth tokens for {datasource}, user_id={user_id[:8]}...")
                tokens = await oauth_service.get_decrypted_tokens(
                    db=db,
                    user_id=user_id,
                    provider=datasource,
                    auto_refresh=True,  # Auto-refresh if expired
                )

                if tokens:
                    # Use connector's method to convert OAuth tokens to env vars
                    oauth_env = connector.get_env_from_oauth_tokens(tokens)
                    env.update(oauth_env)
                    logger.info(f"Using OAuth tokens for {datasource} (email: {tokens.get('provider_email', 'unknown')})")
                    logger.info(f"OAuth env vars set: {list(oauth_env.keys())}")
                else:
                    logger.warning(f"No OAuth connection found for {datasource}, using defaults")
            except Exception as e:
                logger.error(f"Error fetching OAuth tokens for {datasource}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Fall through to try regular credentials as fallback

        else:
            # Use traditional credential service for non-OAuth providers
            # Prioritize user_id over session_id
            if user_id:
                user_credentials = await credential_service.get_credentials(
                    datasource=datasource,
                    db=db,
                    user_id=user_id,
                )
            elif session_id:
                user_credentials = await credential_service.get_credentials(
                    datasource=datasource,
                    session_id=session_id,
                )
            else:
                user_credentials = None

            if user_credentials:
                # Use connector's method to convert credentials to env vars
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
        # Inject user email for Google Workspace tools that require it
        if datasource == "google_workspace" and user_id and db:
            if "user_google_email" not in arguments or not arguments.get("user_google_email"):
                try:
                    from app.services.oauth_service import oauth_service
                    oauth_conn = await oauth_service.get_connection(db, user_id, datasource)
                    if oauth_conn and oauth_conn.provider_email:
                        arguments = {**arguments, "user_google_email": oauth_conn.provider_email}
                        logger.info(f"Injected user email for Google Workspace tool {tool_name}: {oauth_conn.provider_email}")
                except Exception as e:
                    logger.warning(f"Could not inject user email for {tool_name}: {e}")

        # Try to use fast path with caching
        try:
            return await self.call_tool_fast(
                datasource, tool_name, arguments, user_id, session_id, db, force_refresh
            )
        except (asyncio.TimeoutError, ConnectionError, OSError) as e:
            logger.warning(f"Fast path failed for {datasource}, falling back to standard: {e}")
            # Fallback to standard connection
            async with self.get_client(datasource, user_id, session_id, db=db) as session:
                result = await session.call_tool(tool_name, arguments)
                return result.content if result else []

    def _get_cache_key(self, datasource: str, tool_name: str, arguments: dict, user_id: Optional[str] = None) -> str:
        """Generate a cache key for result caching. Includes user_id to separate authenticated vs unauthenticated caches."""
        args_str = json.dumps(arguments, sort_keys=True)
        user_part = user_id[:8] if user_id else "anon"
        key_str = f"{datasource}:{tool_name}:{user_part}:{args_str}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _check_result_cache(self, cache_key: str, force_refresh: bool = False) -> Optional[List[Any]]:
        """Check if we have a cached result."""
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

    def _store_result_cache(self, cache_key: str, result: List[Any]):
        """Store a result in the cache."""
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
        logger.info(f"call_tool_fast: {datasource}/{tool_name} user_id={user_id is not None}, db={db is not None}")

        # CHECK CACHE FIRST (instant return if cached)
        # Get cacheable tools from connector registry
        cacheable_tools = get_cacheable_tools(datasource)

        cache_key = None
        if tool_name in cacheable_tools:
            cache_key = self._get_cache_key(datasource, tool_name, arguments, user_id)
            cached_result = self._check_result_cache(cache_key, force_refresh=force_refresh)
            if cached_result is not None:
                elapsed = time.time() - start_time
                logger.info(f"⚡⚡⚡ CACHED result ({datasource}/{tool_name}) in {elapsed*1000:.0f}ms")
                return cached_result
            elif force_refresh:
                logger.info(f"🔄 Force refresh requested for {datasource}/{tool_name}")

        # Use standard connection (MCP stdio doesn't support reuse well across tasks)
        async with self.get_client(datasource, user_id, session_id, db=db) as session:
            result = await session.call_tool(tool_name, arguments)
            result_content = result.content if result else []
            elapsed = time.time() - start_time
            logger.info(f"⚡ FAST call_tool ({datasource}/{tool_name}) in {elapsed*1000:.0f}ms")

            # Store in cache for future requests (but don't cache errors)
            if cache_key and result_content:
                # Don't cache error results
                is_error = any(
                    hasattr(c, 'text') and ('ACTION REQUIRED' in str(c.text) or 'Error' in str(c.text)[:50])
                    for c in result_content
                )
                if not is_error:
                    self._store_result_cache(cache_key, result_content)
                else:
                    logger.info(f"Not caching error result for {datasource}/{tool_name}")

            return result_content

    async def _create_persistent_session(
        self,
        datasource: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        db: Optional[any] = None,
    ):
        """Create and store a persistent MCP session."""
        # Get connector from registry
        connector = get_connector(datasource)
        if not connector:
            raise ValueError(f"Unknown data source: {datasource}")

        # Get server command from connector
        command, args = connector.get_server_command()
        connector_env = await self._get_connector_env(datasource, user_id, session_id, db=db)

        # Create server parameters
        server = StdioServerParameters(
            command=command,
            args=args,
            env={**os.environ.copy(), **connector_env},
        )

        # Start the stdio client and keep it alive
        # We need to manage the context manually to keep it persistent
        import subprocess

        # Start subprocess directly
        process = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ.copy(), **connector_env},
        )

        # Create MCP session using the process streams
        from mcp.client.stdio import stdio_client

        # Use the standard stdio_client context manager but store the session
        # This is a workaround - we'll use the context manager but not exit it
        client_cm = stdio_client(server)
        read_write = await client_cm.__aenter__()
        read, write = read_write

        session = ClientSession(read, write)
        await session.__aenter__()
        await session.initialize()

        # Store everything for cleanup later
        self._persistent_sessions[datasource] = {
            "session": session,
            "client_cm": client_cm,
            "process": process,
            "last_used": time.time(),
            "created_at": time.time(),
        }

        logger.info(f"✅ Persistent session created for {datasource}")

    async def _close_persistent_session(self, datasource: str):
        """Close a persistent session and clean up resources."""
        if datasource in self._persistent_sessions:
            session_data = self._persistent_sessions[datasource]
            try:
                session = session_data.get("session")
                if session:
                    await session.__aexit__(None, None, None)

                client_cm = session_data.get("client_cm")
                if client_cm:
                    await client_cm.__aexit__(None, None, None)

                process = session_data.get("process")
                if process:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        process.kill()

                logger.info(f"🔌 Closed persistent session for {datasource}")
            except (asyncio.TimeoutError, ConnectionError, OSError) as e:
                logger.warning(f"Error closing persistent session for {datasource}: {e}")
            finally:
                del self._persistent_sessions[datasource]

    async def close_all_persistent_sessions(self):
        """Close all persistent sessions. Call this on app shutdown."""
        datasources = list(self._persistent_sessions.keys())
        for datasource in datasources:
            await self._close_persistent_session(datasource)
        logger.info(f"🔌 Closed all {len(datasources)} persistent sessions")

    async def cleanup_idle_connections(self):
        """Close connections that have been idle too long."""
        now = time.time()
        to_close = []
        for datasource, data in self._persistent_sessions.items():
            if now - data.get("last_used", 0) > CONNECTION_IDLE_TIMEOUT:
                to_close.append(datasource)

        for datasource in to_close:
            logger.info(f"🧹 Closing idle connection for {datasource}")
            await self._close_persistent_session(datasource)

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
        logger.info(f"📋 Cached schema for {table_name}")

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
