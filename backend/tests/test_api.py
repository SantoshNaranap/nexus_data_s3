"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app

client = TestClient(app)


def test_root_endpoint():
    """Test root endpoint returns correct information."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "ConnectorMCP API"
    assert data["status"] == "running"


def test_health_endpoint():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@patch("app.services.mcp_service.mcp_service")
def test_list_datasources(mock_mcp_service):
    """Test listing data sources."""
    mock_mcp_service.get_available_datasources.return_value = [
        {
            "id": "s3",
            "name": "Amazon S3",
            "description": "Test",
            "icon": "s3",
            "enabled": True,
        }
    ]

    response = client.get("/api/datasources")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "s3"


@patch("app.services.chat_service.chat_service")
def test_send_message(mock_chat_service):
    """Test sending a chat message."""
    mock_chat_service.process_message.return_value = (
        "Test response",
        [],
    )

    response = client.post(
        "/api/chat/message",
        json={
            "message": "Test message",
            "datasource": "s3",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "session_id" in data
    assert data["datasource"] == "s3"


def test_list_sessions():
    """Test listing chat sessions."""
    response = client.get("/api/chat/sessions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_session():
    """Test creating a new session."""
    response = client.post(
        "/api/chat/sessions",
        json={
            "datasource": "s3",
            "name": "Test Session",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["datasource"] == "s3"
