# MySQL MCP Connector

MCP server for MySQL database integration, providing tools to query and explore MySQL databases.

## Features

- List all databases
- List tables in a database
- Describe table schema
- Execute SELECT queries (read-only)
- Get table statistics
- Get table indexes

## Installation

```bash
cd connectors/mysql
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

## Configuration

Set the following environment variables:

```bash
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
export MYSQL_USER=your_user
export MYSQL_PASSWORD=your_password
export MYSQL_DATABASE=your_database
```

## Running as Standalone Server

```bash
python src/mysql_server.py
```

## Testing

```bash
pytest tests/
```

With coverage:

```bash
pytest --cov=src --cov-report=html tests/
```

## Security Notes

- Only SELECT queries are permitted for security
- Use read-only database users when possible
- Never expose database credentials in logs or responses
- Consider using SSL/TLS for database connections
- Implement query timeouts for long-running queries

## License

[To be determined]
