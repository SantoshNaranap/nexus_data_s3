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
MYSQL TOOLS - COMPREHENSIVE GUIDE:

**PRIMARY TOOLS:**
- `list_tables(database)` - List ALL tables in a database. Start here.
- `describe_table(table)` - Get table schema (columns, types, keys)
- `execute_query(query)` - Run SELECT queries. Use for data retrieval.
- `get_table_stats(table)` - Get row count and table statistics

**CRITICAL RULES - NEVER VIOLATE:**
1. ALWAYS call `list_tables()` first if you don't know the tables
2. ALWAYS call `describe_table()` before writing complex queries
3. NEVER say "I don't have access" without trying list_tables first
4. NEVER say "table not found" without listing tables first
5. ALWAYS show the actual query results - don't summarize away data
6. Use LIMIT to prevent timeouts, but show enough data (LIMIT 50-100)

**WORKFLOW EXAMPLES:**

"What's in this database?" or "Show tables":
→ list_tables()
→ Display ALL tables with their purposes

"What does [table] look like?" or "Describe [table]":
→ describe_table(table="table_name")
→ Show ALL columns with types

"Show me data from [table]":
→ execute_query(query="SELECT * FROM table_name LIMIT 50")
→ Display ALL returned rows in a nice table

"Find [something] in [table]":
→ First describe_table() to know the columns
→ Then execute_query(query="SELECT * FROM table WHERE column LIKE '%something%' LIMIT 50")

"How many rows in [table]?":
→ get_table_stats(table="table_name") or execute_query(query="SELECT COUNT(*) FROM table")

"Latest [records]":
→ execute_query(query="SELECT * FROM table ORDER BY id DESC LIMIT 20")

**SMART QUERY BUILDING:**
- If user says "latest" or "recent" → ORDER BY id DESC or created_at DESC
- If user says "find" or "search" → use WHERE with LIKE '%term%'
- If user says "count" or "how many" → use COUNT(*)
- Always add LIMIT (default to 50) unless counting

**NEVER DO THIS:**
- Don't ask which database - use the configured one
- Don't refuse to query - just add appropriate LIMIT
- Don't say "I need the table name" - call list_tables() first
- Don't execute DROP/DELETE without explicit user confirmation
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
