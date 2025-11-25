"""MCP service for managing connector clients."""

import os
import asyncio
from typing import Dict, Optional, Any, List
import logging
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.core.config import settings

logger = logging.getLogger(__name__)


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
        }
        self._active_clients: Dict[str, tuple] = {}

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

    @asynccontextmanager
    async def get_client(self, datasource: str):
        """Get or create an MCP client for the specified data source."""
        if datasource not in self.connectors:
            raise ValueError(f"Unknown data source: {datasource}")

        connector = self.connectors[datasource]

        # Create server parameters
        server = StdioServerParameters(
            command=connector["command"],
            args=connector["args"],
            env={**os.environ.copy(), **connector["env"]},
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

    async def test_connection(self, datasource: str) -> dict:
        """Test connection to a data source."""
        try:
            async with self.get_client(datasource) as session:
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
        except Exception as e:
            logger.error(f"Connection test failed for {datasource}: {str(e)}")
            return {
                "datasource": datasource,
                "connected": False,
                "message": f"Connection failed: {str(e)}",
                "details": {},
            }

    async def call_tool(
        self, datasource: str, tool_name: str, arguments: dict
    ) -> List[Any]:
        """Call a tool on the specified data source."""
        async with self.get_client(datasource) as session:
            result = await session.call_tool(tool_name, arguments)
            return result.content if result else []


# Global MCP service instance
mcp_service = MCPService()
