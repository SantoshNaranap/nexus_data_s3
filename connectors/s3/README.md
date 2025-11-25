# S3 MCP Connector

MCP server for Amazon S3 integration, providing tools to interact with S3 buckets and objects.

## Features

- List all S3 buckets
- List objects in a bucket with prefix filtering
- Read object content (text and binary)
- Write objects to S3
- Search objects by pattern
- Get object metadata

## Installation

```bash
cd connectors/s3
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

## Configuration

Set the following environment variables:

```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

## Running as Standalone Server

```bash
python src/s3_server.py
```

## Testing

```bash
pytest tests/
```

With coverage:

```bash
pytest --cov=src --cov-report=html tests/
```

## Usage in MCP Client

```json
{
  "mcpServers": {
    "s3": {
      "command": "python",
      "args": ["/path/to/connectors/s3/src/s3_server.py"],
      "env": {
        "AWS_ACCESS_KEY_ID": "your_key",
        "AWS_SECRET_ACCESS_KEY": "your_secret",
        "AWS_DEFAULT_REGION": "us-east-1"
      }
    }
  }
}
```

## Available Tools

### list_buckets

List all S3 buckets in the AWS account.

**Parameters**: None

### list_objects

List objects in an S3 bucket.

**Parameters**:
- `bucket` (required): Bucket name
- `prefix` (optional): Prefix filter
- `max_keys` (optional): Maximum number of objects (default: 1000)

### read_object

Read content from an S3 object.

**Parameters**:
- `bucket` (required): Bucket name
- `key` (required): Object key
- `max_size_mb` (optional): Maximum size in MB (default: 10)

### write_object

Write content to an S3 object.

**Parameters**:
- `bucket` (required): Bucket name
- `key` (required): Object key
- `content` (required): Content to write
- `content_type` (optional): MIME type (default: text/plain)

### search_objects

Search for objects matching a pattern.

**Parameters**:
- `bucket` (required): Bucket name
- `pattern` (required): Search pattern with wildcards
- `max_results` (optional): Maximum results (default: 100)

### get_object_metadata

Get metadata for an S3 object.

**Parameters**:
- `bucket` (required): Bucket name
- `key` (required): Object key

## Export and Reuse

This connector can be exported and used in other applications:

1. Copy the `connectors/s3` directory to your project
2. Install dependencies from `pyproject.toml`
3. Import and use in your MCP client configuration

## Security Notes

- Always use IAM roles or temporary credentials when possible
- Implement least privilege access
- Never commit credentials to version control
- Consider using AWS Secrets Manager for credential management

## License

[To be determined]
