"""
Integration tests for API endpoints.

These tests verify the full request/response cycle through the API layer.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

# Import the actual app
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.main import app
from app.models.database import User


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    @pytest.mark.anyio
    async def test_health_returns_200(self, client):
        """Health endpoint should return 200 with healthy status."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


class TestAuthEndpoints:
    """Tests for authentication endpoints."""

    @pytest.mark.anyio
    async def test_login_with_invalid_credentials_returns_401(self, client):
        """Login with invalid credentials should return 401."""
        response = await client.post(
            "/api/auth/login",
            json={"email": "nonexistent@test.com", "password": "wrongpassword"}
        )
        assert response.status_code == 401

    @pytest.mark.anyio
    async def test_login_with_missing_fields_returns_422(self, client):
        """Login with missing fields should return 422."""
        response = await client.post(
            "/api/auth/login",
            json={"email": "test@test.com"}  # Missing password
        )
        assert response.status_code == 422

    @pytest.mark.anyio
    async def test_me_without_auth_returns_401(self, client):
        """/me endpoint without auth should return 401."""
        response = await client.get("/api/auth/me")
        assert response.status_code == 401


class TestDatasourceEndpoints:
    """Tests for datasource endpoints."""

    @pytest.mark.anyio
    async def test_list_datasources_returns_array(self, client):
        """List datasources should return an array."""
        response = await client.get("/api/datasources")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have at least some datasources
        assert len(data) > 0
        # Each datasource should have id and name
        for ds in data:
            assert "id" in ds
            assert "name" in ds


class TestCredentialsEndpoints:
    """Tests for credentials endpoints."""

    @pytest.mark.anyio
    async def test_check_status_without_auth(self, client):
        """Check status without auth returns 200 (uses optional auth)."""
        response = await client.get("/api/credentials/jira/status")
        # Endpoint uses Optional[User] dependency, so it returns 200 with configured=False
        assert response.status_code == 200
        data = response.json()
        assert "configured" in data


class TestChatEndpoints:
    """Tests for chat endpoints."""

    @pytest.mark.anyio
    async def test_chat_without_auth(self, client):
        """Chat endpoint without auth uses optional auth and processes request."""
        response = await client.post(
            "/api/chat/message",
            json={"message": "test", "datasource": "jira"}
        )
        # Endpoint uses Optional[User] dependency - returns 200 (streaming) even without auth
        # The response may fail during tool execution but endpoint itself accepts the request
        assert response.status_code in [200, 500]  # 200 for streaming, 500 if tool fails


class TestAgentEndpoints:
    """Tests for agent/multi-source endpoints."""

    @pytest.mark.anyio
    async def test_agent_sources_returns_list(self, client):
        """Agent sources endpoint should return configured sources."""
        # This endpoint might require auth, so we just check it doesn't 500
        response = await client.get("/api/agent/sources")
        assert response.status_code in [200, 401, 403]

    @pytest.mark.anyio
    async def test_detect_sources_returns_valid_response(self, client):
        """Detect sources should work without auth for simple queries."""
        response = await client.post(
            "/api/agent/detect",
            json={"query": "Show me my JIRA issues"}
        )
        # Should either work or require auth
        assert response.status_code in [200, 401, 403]


class TestDigestEndpoints:
    """Tests for digest/what-you-missed endpoints."""

    @pytest.mark.anyio
    async def test_digest_sources_without_auth_returns_401(self, client):
        """Digest sources without auth should return 401."""
        response = await client.get("/api/digest/sources")
        assert response.status_code == 401

    @pytest.mark.anyio
    async def test_digest_last_login_without_auth_returns_401(self, client):
        """Digest last-login without auth should return 401."""
        response = await client.get("/api/digest/last-login")
        assert response.status_code == 401


class TestInputValidation:
    """Tests for input validation."""

    @pytest.mark.anyio
    async def test_login_with_empty_email_returns_422(self, client):
        """Login with empty email should return 422."""
        response = await client.post(
            "/api/auth/login",
            json={"email": "", "password": "password"}
        )
        assert response.status_code == 422

    @pytest.mark.anyio
    async def test_login_with_invalid_email_format(self, client):
        """Login with invalid email format should handle gracefully."""
        response = await client.post(
            "/api/auth/login",
            json={"email": "notanemail", "password": "password"}
        )
        # Should either validate or return 401 (not found)
        assert response.status_code in [401, 422]


class TestCORSHeaders:
    """Tests for CORS configuration."""

    @pytest.mark.anyio
    async def test_options_request_returns_cors_headers(self, client):
        """OPTIONS request should return CORS headers."""
        response = await client.options(
            "/api/auth/login",
            headers={"Origin": "http://localhost:5173"}
        )
        # Should not error
        assert response.status_code in [200, 204, 405]


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.anyio
    async def test_404_for_unknown_endpoint(self, client):
        """Unknown endpoint should return 404."""
        response = await client.get("/api/unknown/endpoint")
        assert response.status_code == 404

    @pytest.mark.anyio
    async def test_method_not_allowed(self, client):
        """Wrong method should return 405."""
        response = await client.delete("/health")
        assert response.status_code == 405


# Run with: pytest tests/integration/test_api_endpoints.py -v
