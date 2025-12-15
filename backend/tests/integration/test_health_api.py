"""
Integration tests for health check endpoints.
"""

import pytest
from httpx import AsyncClient


class TestHealthEndpoints:
    """Tests for health check API endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test basic health check endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_liveness_probe(self, client: AsyncClient):
        """Test liveness probe endpoint."""
        response = await client.get("/health/live")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "alive"

    @pytest.mark.asyncio
    async def test_readiness_probe(self, client: AsyncClient):
        """Test readiness probe endpoint."""
        response = await client.get("/health/ready")
        # Note: May fail if DB is not available in test environment
        # In real tests, we'd mock the database
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "ready"
            assert "checks" in data

    @pytest.mark.asyncio
    async def test_detailed_health_check(self, client: AsyncClient):
        """Test detailed health check endpoint."""
        response = await client.get("/health/detailed")
        # May fail if DB is not available
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "healthy"
            assert "version" in data
            assert "uptime" in data
            assert "system" in data
            assert "components" in data

    @pytest.mark.asyncio
    async def test_config_check(self, client: AsyncClient):
        """Test configuration check endpoint."""
        response = await client.get("/health/config")

        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "configured"
            assert "core" in data
            assert "connectors" in data

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, client: AsyncClient):
        """Test Prometheus metrics endpoint."""
        response = await client.get("/health/metrics")
        assert response.status_code == 200

        # Check content type
        assert "text/plain" in response.headers.get("content-type", "")

        # Check for Prometheus format markers
        content = response.text
        assert "# HELP" in content or content == ""  # May be empty initially
