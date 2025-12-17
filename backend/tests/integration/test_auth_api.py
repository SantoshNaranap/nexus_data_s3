"""
Integration tests for authentication endpoints.
"""

import pytest
from httpx import AsyncClient


class TestAuthEndpoints:
    """Tests for authentication API endpoints."""

    @pytest.mark.asyncio
    async def test_auth_status_unauthenticated(self, client: AsyncClient):
        """Test auth status when not authenticated."""
        response = await client.get("/api/auth/status")
        assert response.status_code == 200

        data = response.json()
        assert data["authenticated"] is False

    @pytest.mark.asyncio
    async def test_auth_status_authenticated(
        self, authenticated_client: AsyncClient, test_user
    ):
        """Test auth status when authenticated."""
        response = await authenticated_client.get("/api/auth/status")
        assert response.status_code == 200

        data = response.json()
        assert data["authenticated"] is True
        assert data["user"]["email"] == test_user.email

    @pytest.mark.asyncio
    async def test_get_me_unauthenticated(self, client: AsyncClient):
        """Test /me endpoint without authentication."""
        response = await client.get("/api/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_authenticated(
        self, authenticated_client: AsyncClient, test_user
    ):
        """Test /me endpoint with authentication."""
        response = await authenticated_client.get("/api/auth/me")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == test_user.id
        assert data["email"] == test_user.email
        assert data["name"] == test_user.name

    @pytest.mark.asyncio
    async def test_logout(self, authenticated_client: AsyncClient):
        """Test logout endpoint."""
        response = await authenticated_client.post("/api/auth/logout")
        assert response.status_code == 200

        data = response.json()
        assert "message" in data

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client: AsyncClient):
        """Test login with invalid credentials."""
        response = await client.post(
            "/api/auth/login",
            json={"email": "nonexistent@example.com", "password": "wrongpassword"}
        )
        # Should return 401 for invalid credentials
        assert response.status_code == 401
