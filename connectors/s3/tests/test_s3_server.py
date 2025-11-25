"""Tests for S3 MCP Server."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime


@pytest.fixture
def mock_s3_client():
    """Mock boto3 S3 client."""
    with patch("s3_server.s3_client") as mock:
        yield mock


@pytest.mark.asyncio
async def test_list_buckets(mock_s3_client):
    """Test listing S3 buckets."""
    from s3_server import handle_list_buckets

    # Mock response
    mock_s3_client.list_buckets.return_value = {
        "Buckets": [
            {"Name": "bucket1", "CreationDate": datetime(2024, 1, 1)},
            {"Name": "bucket2", "CreationDate": datetime(2024, 1, 2)},
        ]
    }

    result = await handle_list_buckets()

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["count"] == 2
    assert len(data["buckets"]) == 2
    assert data["buckets"][0]["name"] == "bucket1"


@pytest.mark.asyncio
async def test_list_objects(mock_s3_client):
    """Test listing objects in a bucket."""
    from s3_server import handle_list_objects

    mock_s3_client.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": "file1.txt",
                "Size": 1024,
                "LastModified": datetime(2024, 1, 1),
                "StorageClass": "STANDARD",
            },
            {
                "Key": "file2.txt",
                "Size": 2048,
                "LastModified": datetime(2024, 1, 2),
                "StorageClass": "STANDARD",
            },
        ],
        "IsTruncated": False,
    }

    arguments = {"bucket": "test-bucket", "prefix": "", "max_keys": 1000}
    result = await handle_list_objects(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["count"] == 2
    assert data["bucket"] == "test-bucket"
    assert data["objects"][0]["key"] == "file1.txt"


@pytest.mark.asyncio
async def test_read_object_text(mock_s3_client):
    """Test reading a text object."""
    from s3_server import handle_read_object

    # Mock head_object for size check
    mock_s3_client.head_object.return_value = {
        "ContentLength": 100,
        "ContentType": "text/plain",
    }

    # Mock get_object for content
    mock_body = MagicMock()
    mock_body.read.return_value = b"Hello, World!"
    mock_s3_client.get_object.return_value = {
        "Body": mock_body,
    }

    arguments = {"bucket": "test-bucket", "key": "test.txt", "max_size_mb": 10}
    result = await handle_read_object(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["content"] == "Hello, World!"
    assert data["encoding"] == "utf-8"
    assert data["size"] == 100


@pytest.mark.asyncio
async def test_read_object_too_large(mock_s3_client):
    """Test reading an object that exceeds size limit."""
    from s3_server import handle_read_object

    # Mock head_object with large size
    mock_s3_client.head_object.return_value = {
        "ContentLength": 20 * 1024 * 1024,  # 20 MB
        "ContentType": "text/plain",
    }

    arguments = {"bucket": "test-bucket", "key": "large.txt", "max_size_mb": 10}
    result = await handle_read_object(arguments)

    assert len(result) == 1
    assert "exceeds maximum allowed size" in result[0].text


@pytest.mark.asyncio
async def test_write_object(mock_s3_client):
    """Test writing an object."""
    from s3_server import handle_write_object

    mock_s3_client.put_object.return_value = {}

    arguments = {
        "bucket": "test-bucket",
        "key": "new-file.txt",
        "content": "Test content",
        "content_type": "text/plain",
    }
    result = await handle_write_object(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["status"] == "success"
    assert data["key"] == "new-file.txt"

    # Verify put_object was called
    mock_s3_client.put_object.assert_called_once()


@pytest.mark.asyncio
async def test_search_objects(mock_s3_client):
    """Test searching for objects."""
    from s3_server import handle_search_objects

    mock_s3_client.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "data/file1.csv", "Size": 1024, "LastModified": datetime(2024, 1, 1)},
            {"Key": "data/file2.csv", "Size": 2048, "LastModified": datetime(2024, 1, 2)},
            {"Key": "data/file3.txt", "Size": 512, "LastModified": datetime(2024, 1, 3)},
        ]
    }

    arguments = {"bucket": "test-bucket", "pattern": "data/*.csv", "max_results": 100}
    result = await handle_search_objects(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["count"] == 2  # Only CSV files should match
    assert all(".csv" in obj["key"] for obj in data["objects"])


@pytest.mark.asyncio
async def test_get_object_metadata(mock_s3_client):
    """Test getting object metadata."""
    from s3_server import handle_get_metadata

    mock_s3_client.head_object.return_value = {
        "ContentLength": 1024,
        "ContentType": "application/json",
        "LastModified": datetime(2024, 1, 1),
        "ETag": '"abc123"',
        "Metadata": {"custom-key": "custom-value"},
        "StorageClass": "STANDARD",
    }

    arguments = {"bucket": "test-bucket", "key": "data.json"}
    result = await handle_get_metadata(arguments)

    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["size"] == 1024
    assert data["content_type"] == "application/json"
    assert data["metadata"]["custom-key"] == "custom-value"


@pytest.mark.asyncio
async def test_error_handling(mock_s3_client):
    """Test error handling for AWS errors."""
    from s3_server import call_tool
    from botocore.exceptions import ClientError

    mock_s3_client.list_buckets.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
        "ListBuckets",
    )

    result = await call_tool("list_buckets", {})

    assert len(result) == 1
    assert "Error:" in result[0].text
