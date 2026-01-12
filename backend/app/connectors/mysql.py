"""
MySQL connector configuration.

Provides MCP tools for querying MySQL databases:
- Listing tables
- Describing table schemas
- Executing SQL queries
"""

from typing import Dict, List, Optional, Any

from .base import BaseConnector, ConnectorMetadata, CredentialField


class MySQLConnector(BaseConnector):
    """MySQL database connector configuration."""

    @property
    def metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            id="mysql",
            name="MySQL",
            description="Query MySQL databases",
            icon="mysql",
        )

    @property
    def credential_fields(self) -> List[CredentialField]:
        return [
            CredentialField(
                name="mysql_host",
                env_var="MYSQL_HOST",
                display_name="Host",
                description="MySQL server hostname",
                required=True,
                sensitive=False,
            ),
            CredentialField(
                name="mysql_port",
                env_var="MYSQL_PORT",
                display_name="Port",
                description="MySQL port (default: 3306)",
                required=False,
                sensitive=False,
            ),
            CredentialField(
                name="mysql_user",
                env_var="MYSQL_USER",
                display_name="Username",
                description="MySQL username",
                required=True,
                sensitive=False,
            ),
            CredentialField(
                name="mysql_password",
                env_var="MYSQL_PASSWORD",
                display_name="Password",
                description="MySQL password",
                required=True,
            ),
            CredentialField(
                name="mysql_database",
                env_var="MYSQL_DATABASE",
                display_name="Database",
                description="Database name to connect to",
                required=True,
                sensitive=False,
            ),
        ]

    @property
    def server_script_path(self) -> str:
        return "../connectors/mysql/src/mysql_server.py"

    @property
    def cacheable_tools(self) -> List[str]:
        return [
            "list_tables",
            "describe_table",
            # Note: execute_query is NOT cacheable as it could have side effects
        ]

    @property
    def system_prompt_addition(self) -> str:
        return """
MYSQL QUERY GUIDE:

**TOOLS:**
- `execute_query(query)` - Run SQL queries. This is the PRIMARY tool.
- `list_tables()` - List tables (use only if you truly don't know the schema)
- `describe_table(table)` - Get schema for one table
- `get_table_stats(table)` - Get row count

**CRITICAL: JUST RUN QUERIES - DON'T LOOP**
When the user asks about specific tables (providers, claims, users, etc.):
1. IMMEDIATELY construct and run the SQL query
2. Do NOT call list_tables or get_table_stats first
3. If a query fails due to unknown table/column, THEN check schema

**ANALYTICAL QUERY EXAMPLES:**

"Count of providers" or "how many providers":
→ execute_query(query="SELECT COUNT(*) as total_providers FROM providers")

"Providers by type" or "count by type":
→ execute_query(query="SELECT type, COUNT(*) as count FROM providers GROUP BY type")

"Claims for each provider type" (requires JOIN):
→ execute_query(query="SELECT p.type, COUNT(c.id) as claim_count FROM providers p LEFT JOIN claims c ON p.id = c.provider_id GROUP BY p.type")

"Tell me about providers and claims":
→ Run multiple queries:
  1. SELECT COUNT(*) FROM providers
  2. SELECT type, COUNT(*) FROM providers GROUP BY type
  3. SELECT p.type, COUNT(c.id) FROM providers p LEFT JOIN claims c ON p.id = c.provider_id GROUP BY p.type

**QUERY BUILDING RULES:**
- User says "count" or "how many" → use COUNT(*)
- User says "by type" or "each type" → use GROUP BY
- User says "for each" or "per" → likely needs a JOIN
- Always add LIMIT for SELECT * queries (LIMIT 50)
- Don't add LIMIT for COUNT/aggregate queries

**AVOID THESE MISTAKES:**
- DON'T call get_table_stats repeatedly - just run the query
- DON'T explore schema if user already named the tables
- DON'T ask which database - use the configured one
- DON'T call the same tool twice in a row
"""

    def get_direct_routing(self, message: str) -> Optional[List[Dict[str, Any]]]:
        """Direct routing for common MySQL queries."""
        message_lower = message.lower().strip()

        # List tables
        if any(kw in message_lower for kw in ["table", "tables", "list table", "show table", "what table"]):
            return [{"tool": "list_tables", "args": {}}]

        return None


# Export singleton instance
mysql_connector = MySQLConnector()
