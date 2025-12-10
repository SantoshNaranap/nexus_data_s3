"""MCP service for managing connector clients."""

import os
import asyncio
import time
import hashlib
import json
from typing import Dict, Optional, Any, List
import logging
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.core.config import settings
from app.services.credential_service import credential_service

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
        # Use the venv's Python if available
        import sys
        python_cmd = sys.executable

        self.connectors: Dict[str, dict] = {
            "s3": {
                "name": "Amazon S3",
                "description": "Query and manage S3 buckets and objects",
                "command": python_cmd,
                "args": [os.path.abspath("../connectors/s3/src/s3_server.py")],
                "env": {
                    "AWS_ACCESS_KEY_ID": settings.aws_access_key_id,
                    "AWS_SECRET_ACCESS_KEY": settings.aws_secret_access_key,
                    "AWS_DEFAULT_REGION": settings.aws_default_region,
                },
            },
            "mysql": {
                "name": "MySQL",
                "description": "Query MySQL databases",
                "command": python_cmd,
                "args": [os.path.abspath("../connectors/mysql/src/mysql_server.py")],
                "env": {
                    "MYSQL_HOST": settings.mysql_host,
                    "MYSQL_PORT": str(settings.mysql_port),
                    "MYSQL_USER": settings.mysql_user,
                    "MYSQL_PASSWORD": settings.mysql_password,
                    "MYSQL_DATABASE": settings.mysql_database,
                },
            },
            "jira": {
                "name": "JIRA",
                "description": "Manage JIRA issues and projects",
                "command": python_cmd,
                "args": [os.path.abspath("../connectors/jira/src/jira_server.py")],
                "env": {
                    "JIRA_URL": settings.jira_url,
                    "JIRA_EMAIL": settings.jira_email,
                    "JIRA_API_TOKEN": settings.jira_api_token,
                },
            },
            "shopify": {
                "name": "Shopify",
                "description": "Query Shopify products, orders, and customers",
                "command": python_cmd,
                "args": [os.path.abspath("../connectors/shopify/src/shopify_server.py")],
                "env": {
                    "SHOPIFY_SHOP_URL": settings.shopify_shop_url,
                    "SHOPIFY_ACCESS_TOKEN": settings.shopify_access_token,
                    "SHOPIFY_API_VERSION": settings.shopify_api_version,
                },
            },
            "google_workspace": {
                "name": "Google Workspace",
                "description": "Access Google Docs, Sheets, Drive, Gmail, Calendar, and more",
                "command": python_cmd,
                "args": [
                    os.path.abspath("../connectors/google_workspace/main.py"),
                    "--tool-tier", "core",  # Use core tools (Docs, Sheets, Drive, Calendar, Gmail)
                    "--single-user"  # Simplified authentication for single user
                ],
                "env": {
                    "GOOGLE_OAUTH_CLIENT_ID": settings.google_oauth_client_id,
                    "GOOGLE_OAUTH_CLIENT_SECRET": settings.google_oauth_client_secret,
                    "USER_GOOGLE_EMAIL": settings.user_google_email,
                    "WORKSPACE_MCP_PORT": "8001",  # Use port 8001 to avoid conflict with FastAPI on 8000
                    "OAUTHLIB_INSECURE_TRANSPORT": "1",  # For development
                },
            },
            "slack": {
                "name": "Slack",
                "description": "Chat with your Slack workspace - read messages, search, send messages, and more",
                "command": python_cmd,
                "args": [os.path.abspath("../connectors/slack/src/slack_server.py")],
                "env": {
                    "SLACK_BOT_TOKEN": settings.slack_bot_token,
                    "SLACK_APP_TOKEN": settings.slack_app_token,
                },
            },
            "github": {
                "name": "GitHub",
                "description": "Manage GitHub repositories, issues, pull requests, and code",
                "command": python_cmd,
                "args": [os.path.abspath("../connectors/github/src/github_server.py")],
                "env": {
                    "GITHUB_TOKEN": settings.github_token,
                },
            },
        }
        self._active_clients: Dict[str, tuple] = {}
        self._connection_locks: Dict[str, asyncio.Lock] = {}  # Per-datasource locks
        self._persistent_sessions: Dict[str, Dict[str, Any]] = {}  # Persistent connections

    def get_available_datasources(self) -> List[dict]:
        """Get list of available data sources."""
        return [
            {
                "id": key,
                "name": connector["name"],
                "description": connector["description"],
                "icon": key,
                "enabled": True,
            }
            for key, connector in self.connectors.items()
        ]

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
            datasources = list(self.connectors.keys())

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

        Prioritizes user_id credentials over session_id credentials.
        """
        connector = self.connectors[datasource]
        env = connector["env"].copy()

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
            # Map frontend field names to environment variable names
            # This handles the naming differences between frontend and backend
            env_mapping = {
                # S3
                "aws_access_key_id": "AWS_ACCESS_KEY_ID",
                "aws_secret_access_key": "AWS_SECRET_ACCESS_KEY",
                "aws_default_region": "AWS_DEFAULT_REGION",
                # MySQL
                "mysql_host": "MYSQL_HOST",
                "mysql_port": "MYSQL_PORT",
                "mysql_user": "MYSQL_USER",
                "mysql_password": "MYSQL_PASSWORD",
                "mysql_database": "MYSQL_DATABASE",
                # JIRA
                "jira_url": "JIRA_URL",
                "jira_email": "JIRA_EMAIL",
                "jira_api_token": "JIRA_API_TOKEN",
                # Shopify
                "shopify_shop_url": "SHOPIFY_SHOP_URL",
                "shopify_access_token": "SHOPIFY_ACCESS_TOKEN",
                "shopify_api_version": "SHOPIFY_API_VERSION",
                # Google Workspace
                "google_oauth_client_id": "GOOGLE_OAUTH_CLIENT_ID",
                "google_oauth_client_secret": "GOOGLE_OAUTH_CLIENT_SECRET",
                "user_google_email": "USER_GOOGLE_EMAIL",
            }

            # Update env with user credentials
            for field_name, env_name in env_mapping.items():
                if field_name in user_credentials and user_credentials[field_name]:
                    env[env_name] = user_credentials[field_name]

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
        if datasource not in self.connectors:
            raise ValueError(f"Unknown data source: {datasource}")

        connector = self.connectors[datasource]

        # Get environment variables (with user credentials if available)
        # Prioritizes user_id over session_id
        connector_env = await self._get_connector_env(datasource, user_id, session_id, db=db)

        # Create server parameters
        server = StdioServerParameters(
            command=connector["command"],
            args=connector["args"],
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

    def _get_cache_key(self, datasource: str, tool_name: str, arguments: dict) -> str:
        """Generate a cache key for result caching."""
        args_str = json.dumps(arguments, sort_keys=True)
        key_str = f"{datasource}:{tool_name}:{args_str}"
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

        # CHECK CACHE FIRST (instant return if cached)
        # Only cache read-only operations
        cacheable_tools = [
            "list_buckets", "list_objects", "search_objects",  # S3
            "list_projects", "get_project", "search_issues", "get_issue", "query_jira",  # JIRA
            "list_tables", "describe_table",  # MySQL (not execute_query - could have side effects)
            "get_events", "list_messages", "search_drive_files",  # Google Workspace
        ]

        cache_key = None
        if tool_name in cacheable_tools:
            cache_key = self._get_cache_key(datasource, tool_name, arguments)
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

            # Store in cache for future requests
            if cache_key:
                self._store_result_cache(cache_key, result_content)

            return result_content

    async def _create_persistent_session(
        self,
        datasource: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        db: Optional[any] = None,
    ):
        """Create and store a persistent MCP session."""
        if datasource not in self.connectors:
            raise ValueError(f"Unknown data source: {datasource}")

        connector = self.connectors[datasource]
        connector_env = await self._get_connector_env(datasource, user_id, session_id, db=db)

        # Create server parameters
        server = StdioServerParameters(
            command=connector["command"],
            args=connector["args"],
            env={**os.environ.copy(), **connector_env},
        )

        # Start the stdio client and keep it alive
        # We need to manage the context manually to keep it persistent
        import subprocess
        import sys

        # Start subprocess directly
        process = await asyncio.create_subprocess_exec(
            connector["command"],
            *connector["args"],
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
