#!/usr/bin/env python3
"""
Amazon S3 MCP Server

Provides MCP tools for interacting with Amazon S3 buckets.
"""

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from mcp.server import Server
from mcp.types import Tool, TextContent, ErrorData

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("s3-mcp-server")

# Initialize S3 client
s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
)

# Create MCP server
app = Server("s3-connector")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available S3 tools."""
    return [
        Tool(
            name="list_buckets",
            description="List all S3 buckets in the AWS account",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="list_objects",
            description="""List objects in an S3 bucket with optional prefix filter.

IMPORTANT: The 'bucket' parameter is REQUIRED. You must provide the bucket name.
- Call list_buckets first to see available buckets
- Then use the bucket name here: {"bucket": "bucket-name-here"}
- Example: {"bucket": "bideclaudetest"} to list objects in the bideclaudetest bucket""",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket": {
                        "type": "string",
                        "description": "REQUIRED: The name of the S3 bucket (e.g., 'bideclaudetest'). Cannot be empty.",
                    },
                    "prefix": {
                        "type": "string",
                        "description": "Optional prefix to filter objects (e.g., 'folder/')",
                    },
                    "max_keys": {
                        "type": "integer",
                        "description": "Maximum number of objects to return (default: 1000)",
                        "default": 1000,
                    },
                },
                "required": ["bucket"],
            },
        ),
        Tool(
            name="read_object",
            description="""Read the content of an S3 object.

IMPORTANT: Both 'bucket' and 'key' parameters are REQUIRED.
- Example: {"bucket": "bideclaudetest", "key": "path/to/file.txt"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket": {
                        "type": "string",
                        "description": "REQUIRED: The name of the S3 bucket. Cannot be empty.",
                    },
                    "key": {
                        "type": "string",
                        "description": "REQUIRED: The key (path) of the object in the bucket. Cannot be empty.",
                    },
                    "max_size_mb": {
                        "type": "integer",
                        "description": "Maximum size in MB to read (default: 10MB)",
                        "default": 10,
                    },
                },
                "required": ["bucket", "key"],
            },
        ),
        Tool(
            name="write_object",
            description="Write content to an S3 object",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket": {
                        "type": "string",
                        "description": "The name of the S3 bucket",
                    },
                    "key": {
                        "type": "string",
                        "description": "The key (path) where the object will be stored",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the object",
                    },
                    "content_type": {
                        "type": "string",
                        "description": "The content type (MIME type) of the object",
                        "default": "text/plain",
                    },
                },
                "required": ["bucket", "key", "content"],
            },
        ),
        Tool(
            name="search_objects",
            description="""Search for objects in an S3 bucket by key pattern.

IMPORTANT: Both 'bucket' and 'pattern' parameters are REQUIRED.
- Example: {"bucket": "bideclaudetest", "pattern": "*.csv"}""",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket": {
                        "type": "string",
                        "description": "REQUIRED: The name of the S3 bucket. Cannot be empty.",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "REQUIRED: Search pattern (supports wildcards like 'data/*.csv'). Cannot be empty.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 100)",
                        "default": 100,
                    },
                },
                "required": ["bucket", "pattern"],
            },
        ),
        Tool(
            name="get_object_metadata",
            description="Get metadata for an S3 object",
            inputSchema={
                "type": "object",
                "properties": {
                    "bucket": {
                        "type": "string",
                        "description": "The name of the S3 bucket",
                    },
                    "key": {
                        "type": "string",
                        "description": "The key (path) of the object",
                    },
                },
                "required": ["bucket", "key"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    try:
        # Validate required parameters before calling handlers
        if name == "list_objects":
            if "bucket" not in arguments or not arguments.get("bucket"):
                return [TextContent(
                    type="text",
                    text="ERROR: Missing required parameter 'bucket'. You MUST provide the bucket name. "
                         "Example: Call list_objects with {\"bucket\": \"bideclaudetest\"}. "
                         "If you don't know the bucket name, call list_buckets first to see available buckets."
                )]
        elif name == "read_object":
            if "bucket" not in arguments or not arguments.get("bucket"):
                return [TextContent(
                    type="text",
                    text="ERROR: Missing required parameter 'bucket'. You MUST provide the bucket name. "
                         "Example: {\"bucket\": \"bideclaudetest\", \"key\": \"path/to/file.txt\"}"
                )]
            if "key" not in arguments or not arguments.get("key"):
                return [TextContent(
                    type="text",
                    text="ERROR: Missing required parameter 'key'. You MUST provide the object key/path."
                )]
        elif name == "search_objects":
            if "bucket" not in arguments or not arguments.get("bucket"):
                return [TextContent(
                    type="text",
                    text="ERROR: Missing required parameter 'bucket'. You MUST provide the bucket name. "
                         "Example: {\"bucket\": \"bideclaudetest\", \"pattern\": \"*.csv\"}"
                )]
            if "pattern" not in arguments or not arguments.get("pattern"):
                return [TextContent(
                    type="text",
                    text="ERROR: Missing required parameter 'pattern'. You MUST provide a search pattern."
                )]

        # Call the appropriate handler
        if name == "list_buckets":
            return await handle_list_buckets()
        elif name == "list_objects":
            return await handle_list_objects(arguments)
        elif name == "read_object":
            return await handle_read_object(arguments)
        elif name == "write_object":
            return await handle_write_object(arguments)
        elif name == "search_objects":
            return await handle_search_objects(arguments)
        elif name == "get_object_metadata":
            return await handle_get_metadata(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except (ClientError, BotoCoreError) as e:
        logger.error(f"AWS error in {name}: {str(e)}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]
    except Exception as e:
        logger.error(f"Unexpected error in {name}: {str(e)}")
        return [TextContent(type="text", text=f"Unexpected error: {str(e)}")]


async def handle_list_buckets() -> list[TextContent]:
    """List all S3 buckets."""
    response = s3_client.list_buckets()
    buckets = [
        {
            "name": bucket["Name"],
            "creation_date": bucket["CreationDate"].isoformat(),
        }
        for bucket in response.get("Buckets", [])
    ]

    result = {
        "count": len(buckets),
        "buckets": buckets,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_list_objects(arguments: dict[str, Any]) -> list[TextContent]:
    """List objects in an S3 bucket."""
    bucket = arguments["bucket"]
    prefix = arguments.get("prefix", "")
    max_keys = arguments.get("max_keys", 1000)

    params = {
        "Bucket": bucket,
        "MaxKeys": max_keys,
    }
    if prefix:
        params["Prefix"] = prefix

    response = s3_client.list_objects_v2(**params)

    objects = [
        {
            "key": obj["Key"],
            "size": obj["Size"],
            "last_modified": obj["LastModified"].isoformat(),
            "storage_class": obj.get("StorageClass", "STANDARD"),
        }
        for obj in response.get("Contents", [])
    ]

    result = {
        "bucket": bucket,
        "prefix": prefix,
        "count": len(objects),
        "is_truncated": response.get("IsTruncated", False),
        "objects": objects,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_read_object(arguments: dict[str, Any]) -> list[TextContent]:
    """Read content from an S3 object."""
    bucket = arguments["bucket"]
    key = arguments["key"]
    max_size_mb = arguments.get("max_size_mb", 10)
    max_size_bytes = max_size_mb * 1024 * 1024

    # Check object size first
    metadata = s3_client.head_object(Bucket=bucket, Key=key)
    size = metadata["ContentLength"]

    if size > max_size_bytes:
        return [
            TextContent(
                type="text",
                text=f"Error: Object size ({size} bytes) exceeds maximum allowed size ({max_size_bytes} bytes)",
            )
        ]

    # Read object content
    response = s3_client.get_object(Bucket=bucket, Key=key)
    content = response["Body"].read()

    # Try to decode as text, fall back to base64 for binary content
    try:
        content_text = content.decode("utf-8")
        result = {
            "bucket": bucket,
            "key": key,
            "size": size,
            "content_type": metadata.get("ContentType", "unknown"),
            "content": content_text,
            "encoding": "utf-8",
        }
    except UnicodeDecodeError:
        import base64

        result = {
            "bucket": bucket,
            "key": key,
            "size": size,
            "content_type": metadata.get("ContentType", "unknown"),
            "content": base64.b64encode(content).decode("ascii"),
            "encoding": "base64",
        }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_write_object(arguments: dict[str, Any]) -> list[TextContent]:
    """Write content to an S3 object."""
    bucket = arguments["bucket"]
    key = arguments["key"]
    content = arguments["content"]
    content_type = arguments.get("content_type", "text/plain")

    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType=content_type,
    )

    result = {
        "bucket": bucket,
        "key": key,
        "size": len(content.encode("utf-8")),
        "content_type": content_type,
        "status": "success",
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_search_objects(arguments: dict[str, Any]) -> list[TextContent]:
    """Search for objects matching a pattern."""
    bucket = arguments["bucket"]
    pattern = arguments["pattern"]
    max_results = arguments.get("max_results", 100)

    # Convert simple wildcard pattern to prefix for efficient search
    prefix = pattern.split("*")[0] if "*" in pattern else pattern

    response = s3_client.list_objects_v2(
        Bucket=bucket,
        Prefix=prefix,
        MaxKeys=max_results * 2,  # Get more to filter
    )

    # Simple pattern matching (can be enhanced)
    import fnmatch

    objects = [
        {
            "key": obj["Key"],
            "size": obj["Size"],
            "last_modified": obj["LastModified"].isoformat(),
        }
        for obj in response.get("Contents", [])
        if fnmatch.fnmatch(obj["Key"], pattern)
    ][:max_results]

    result = {
        "bucket": bucket,
        "pattern": pattern,
        "count": len(objects),
        "objects": objects,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_get_metadata(arguments: dict[str, Any]) -> list[TextContent]:
    """Get metadata for an S3 object."""
    bucket = arguments["bucket"]
    key = arguments["key"]

    response = s3_client.head_object(Bucket=bucket, Key=key)

    result = {
        "bucket": bucket,
        "key": key,
        "size": response["ContentLength"],
        "content_type": response.get("ContentType", "unknown"),
        "last_modified": response["LastModified"].isoformat(),
        "etag": response["ETag"],
        "metadata": response.get("Metadata", {}),
        "storage_class": response.get("StorageClass", "STANDARD"),
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


def main():
    """Run the S3 MCP server."""
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
