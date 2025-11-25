"""Tests for MySQL MCP Server."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock


@pytest.fixture
def mock_connection():
    """Mock MySQL connection."""
    with patch("mysql_server.get_connection") as mock:
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        mock.return_value = conn
        yield conn, cursor


@pytest.mark.asyncio
async def test_list_databases(mock_connection):
    """Test listing databases."""
    from mysql_server import handle_list_databases

    conn, cursor = mock_connection
    cursor.fetchall.return_value = [("db1",), ("db2",), ("db3",)]

    result = await handle_list_databases()

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["count"] == 3
    assert "db1" in data["databases"]
    cursor.execute.assert_called_once_with("SHOW DATABASES")


@pytest.mark.asyncio
async def test_list_tables(mock_connection):
    """Test listing tables."""
    from mysql_server import handle_list_tables

    conn, cursor = mock_connection
    cursor.fetchall.return_value = [("table1",), ("table2",)]
    cursor.fetchone.return_value = ("test_db",)

    arguments = {}
    result = await handle_list_tables(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["count"] == 2
    assert data["database"] == "test_db"


@pytest.mark.asyncio
async def test_describe_table(mock_connection):
    """Test describing table structure."""
    from mysql_server import handle_describe_table

    conn, cursor = mock_connection
    cursor.fetchall.side_effect = [
        [
            {"Field": "id", "Type": "int", "Null": "NO", "Key": "PRI"},
            {"Field": "name", "Type": "varchar(100)", "Null": "YES", "Key": ""},
        ],
        [],  # foreign keys
    ]

    arguments = {"table": "users"}
    result = await handle_describe_table(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["table"] == "users"
    assert len(data["columns"]) == 2


@pytest.mark.asyncio
async def test_execute_query_select(mock_connection):
    """Test executing SELECT query."""
    from mysql_server import handle_execute_query

    conn, cursor = mock_connection
    cursor.fetchall.return_value = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]

    arguments = {"query": "SELECT * FROM users", "limit": 100}
    result = await handle_execute_query(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["row_count"] == 2
    assert len(data["rows"]) == 2


@pytest.mark.asyncio
async def test_execute_query_non_select(mock_connection):
    """Test that non-SELECT queries are rejected."""
    from mysql_server import handle_execute_query

    arguments = {"query": "DELETE FROM users WHERE id = 1"}
    result = await handle_execute_query(arguments)

    assert len(result) == 1
    assert "Only SELECT queries are allowed" in result[0].text


@pytest.mark.asyncio
async def test_get_table_stats(mock_connection):
    """Test getting table statistics."""
    from mysql_server import handle_get_table_stats

    conn, cursor = mock_connection
    cursor.fetchone.side_effect = [
        {"row_count": 1000},  # COUNT query
        {  # SHOW TABLE STATUS
            "Engine": "InnoDB",
            "Data_length": 16384,
            "Index_length": 8192,
            "Auto_increment": 1001,
            "Create_time": "2024-01-01 00:00:00",
            "Update_time": "2024-01-02 00:00:00",
        },
    ]

    arguments = {"table": "users"}
    result = await handle_get_table_stats(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["row_count"] == 1000
    assert data["engine"] == "InnoDB"


@pytest.mark.asyncio
async def test_get_table_indexes(mock_connection):
    """Test getting table indexes."""
    from mysql_server import handle_get_table_indexes

    conn, cursor = mock_connection
    cursor.fetchall.return_value = [
        {"Key_name": "PRIMARY", "Non_unique": 0, "Column_name": "id"},
        {"Key_name": "idx_email", "Non_unique": 0, "Column_name": "email"},
    ]

    arguments = {"table": "users"}
    result = await handle_get_table_indexes(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert len(data["indexes"]) == 2
    assert any(idx["name"] == "PRIMARY" for idx in data["indexes"])
