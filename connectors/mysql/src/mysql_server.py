#!/usr/bin/env python3
"""
MySQL MCP Server

Provides MCP tools for interacting with MySQL databases.
"""

import json
import logging
import os
from typing import Any

import mysql.connector
from mysql.connector import Error as MySQLError
from mcp.server import Server
from mcp.types import Tool, TextContent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mysql-mcp-server")

# Create MCP server
app = Server("mysql-connector")


def get_connection():
    """Create and return a MySQL connection."""
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),
    )


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available MySQL tools."""
    return [
        Tool(
            name="list_databases",
            description="List all databases on the MySQL server",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="list_tables",
            description="List all tables in a database",
            inputSchema={
                "type": "object",
                "properties": {
                    "database": {
                        "type": "string",
                        "description": "The database name (optional if already connected to one)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="describe_table",
            description="Get the schema/structure of a table",
            inputSchema={
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "The table name",
                    },
                    "database": {
                        "type": "string",
                        "description": "The database name (optional)",
                    },
                },
                "required": ["table"],
            },
        ),
        Tool(
            name="execute_query",
            description="Execute a SELECT query (read-only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SQL SELECT query to execute",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of rows to return (default: 100)",
                        "default": 100,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_table_stats",
            description="Get statistics for a table (row count, size, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "The table name",
                    },
                    "database": {
                        "type": "string",
                        "description": "The database name (optional)",
                    },
                },
                "required": ["table"],
            },
        ),
        Tool(
            name="get_table_indexes",
            description="Get all indexes for a table",
            inputSchema={
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "The table name",
                    },
                    "database": {
                        "type": "string",
                        "description": "The database name (optional)",
                    },
                },
                "required": ["table"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "list_databases":
            return await handle_list_databases()
        elif name == "list_tables":
            return await handle_list_tables(arguments)
        elif name == "describe_table":
            return await handle_describe_table(arguments)
        elif name == "execute_query":
            return await handle_execute_query(arguments)
        elif name == "get_table_stats":
            return await handle_get_table_stats(arguments)
        elif name == "get_table_indexes":
            return await handle_get_table_indexes(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except MySQLError as e:
        logger.error(f"MySQL error in {name}: {str(e)}")
        return [TextContent(type="text", text=f"MySQL Error: {str(e)}")]
    except Exception as e:
        logger.error(f"Unexpected error in {name}: {str(e)}")
        return [TextContent(type="text", text=f"Unexpected error: {str(e)}")]


async def handle_list_databases() -> list[TextContent]:
    """List all databases."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SHOW DATABASES")
        databases = [row[0] for row in cursor.fetchall()]

        result = {
            "count": len(databases),
            "databases": databases,
        }

        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    finally:
        cursor.close()
        conn.close()


async def handle_list_tables(arguments: dict[str, Any]) -> list[TextContent]:
    """List all tables in a database."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        database = arguments.get("database")
        if database:
            cursor.execute(f"USE `{database}`")

        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]

        # Get current database
        cursor.execute("SELECT DATABASE()")
        current_db = cursor.fetchone()[0]

        result = {
            "database": current_db,
            "count": len(tables),
            "tables": tables,
        }

        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    finally:
        cursor.close()
        conn.close()


async def handle_describe_table(arguments: dict[str, Any]) -> list[TextContent]:
    """Describe table structure."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        table = arguments["table"]
        database = arguments.get("database")

        if database:
            cursor.execute(f"USE `{database}`")

        cursor.execute(f"DESCRIBE `{table}`")
        columns = cursor.fetchall()

        # Get foreign keys
        cursor.execute(
            f"""
            SELECT
                COLUMN_NAME,
                REFERENCED_TABLE_NAME,
                REFERENCED_COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = '{table}'
                AND REFERENCED_TABLE_NAME IS NOT NULL
        """
        )
        foreign_keys = cursor.fetchall()

        result = {
            "table": table,
            "columns": columns,
            "foreign_keys": foreign_keys,
        }

        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    finally:
        cursor.close()
        conn.close()


async def handle_execute_query(arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a SELECT query."""
    query = arguments["query"].strip()
    limit = arguments.get("limit", 100)

    # Security: Ensure only SELECT queries
    if not query.upper().startswith("SELECT"):
        return [
            TextContent(
                type="text",
                text="Error: Only SELECT queries are allowed for security reasons",
            )
        ]

    # Add LIMIT if not present
    if "LIMIT" not in query.upper():
        query = f"{query} LIMIT {limit}"

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(query)
        rows = cursor.fetchall()

        result = {
            "query": query,
            "row_count": len(rows),
            "rows": rows,
        }

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    finally:
        cursor.close()
        conn.close()


async def handle_get_table_stats(arguments: dict[str, Any]) -> list[TextContent]:
    """Get table statistics."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        table = arguments["table"]
        database = arguments.get("database")

        if database:
            cursor.execute(f"USE `{database}`")

        # Get row count
        cursor.execute(f"SELECT COUNT(*) as row_count FROM `{table}`")
        row_count = cursor.fetchone()["row_count"]

        # Get table status
        cursor.execute(f"SHOW TABLE STATUS LIKE '{table}'")
        status = cursor.fetchone()

        result = {
            "table": table,
            "row_count": row_count,
            "engine": status.get("Engine"),
            "data_length": status.get("Data_length"),
            "index_length": status.get("Index_length"),
            "auto_increment": status.get("Auto_increment"),
            "create_time": str(status.get("Create_time")),
            "update_time": str(status.get("Update_time")),
        }

        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    finally:
        cursor.close()
        conn.close()


async def handle_get_table_indexes(arguments: dict[str, Any]) -> list[TextContent]:
    """Get table indexes."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        table = arguments["table"]
        database = arguments.get("database")

        if database:
            cursor.execute(f"USE `{database}`")

        cursor.execute(f"SHOW INDEX FROM `{table}`")
        indexes = cursor.fetchall()

        # Group by index name
        index_dict = {}
        for idx in indexes:
            name = idx["Key_name"]
            if name not in index_dict:
                index_dict[name] = {
                    "name": name,
                    "unique": not idx["Non_unique"],
                    "columns": [],
                }
            index_dict[name]["columns"].append(idx["Column_name"])

        result = {
            "table": table,
            "indexes": list(index_dict.values()),
        }

        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    finally:
        cursor.close()
        conn.close()


def main():
    """Run the MySQL MCP server."""
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
