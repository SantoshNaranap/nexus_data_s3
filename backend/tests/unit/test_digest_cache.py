"""Tests for digest pre-loading and caching functionality."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestDigestCache:
    """Tests for the digest caching system."""

    def test_get_cached_digest_returns_none_when_empty(self):
        """Should return None when cache is empty."""
        from app.api.auth import DIGEST_CACHE, get_cached_digest

        # Clear cache
        DIGEST_CACHE.clear()

        result = get_cached_digest("user123")
        assert result is None

    def test_get_cached_digest_returns_data_when_present(self):
        """Should return cached data when available and fresh."""
        from app.api.auth import DIGEST_CACHE, get_cached_digest

        # Clear and populate cache
        DIGEST_CACHE.clear()
        test_data = {
            "since": "2024-01-01T00:00:00",
            "results": [],
            "summary": "Test summary",
            "successful_sources": ["slack"],
            "failed_sources": [],
            "total_time_ms": 100,
        }
        DIGEST_CACHE["user123"] = {
            "data": test_data,
            "timestamp": asyncio.get_event_loop().time(),
        }

        result = get_cached_digest("user123")
        assert result is not None
        assert result["summary"] == "Test summary"
        assert result["successful_sources"] == ["slack"]

    def test_get_cached_digest_returns_none_when_stale(self):
        """Should return None and clear cache when data is stale (>5 min)."""
        from app.api.auth import DIGEST_CACHE, get_cached_digest

        # Clear and populate cache with old timestamp
        DIGEST_CACHE.clear()
        test_data = {"summary": "Old data"}
        DIGEST_CACHE["user123"] = {
            "data": test_data,
            "timestamp": asyncio.get_event_loop().time() - 400,  # 400 seconds ago (>5 min)
        }

        result = get_cached_digest("user123")
        assert result is None
        assert "user123" not in DIGEST_CACHE  # Should be removed


class TestDigestPreload:
    """Tests for the digest pre-loading background task."""

    @pytest.mark.asyncio
    async def test_preload_digest_caches_result(self):
        """Should cache digest result after successful generation."""
        from app.api.auth import DIGEST_CACHE, preload_digest_background

        # Clear cache
        DIGEST_CACHE.clear()

        mock_result = {
            "since": "2024-01-01T00:00:00",
            "results": [{"datasource": "slack", "success": True}],
            "summary": "Test digest",
            "successful_sources": ["slack"],
            "failed_sources": [],
            "total_time_ms": 500,
        }

        with patch('app.api.auth.get_db_context') as mock_db_context:
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            with patch('app.services.digest_service.digest_service') as mock_service:
                mock_service.generate_digest = AsyncMock(return_value=mock_result)

                await preload_digest_background("user123", datetime(2024, 1, 1))

                assert "user123" in DIGEST_CACHE
                assert DIGEST_CACHE["user123"]["data"]["summary"] == "Test digest"

    @pytest.mark.asyncio
    async def test_preload_digest_handles_errors(self):
        """Should log error and not crash when digest generation fails."""
        from app.api.auth import DIGEST_CACHE, preload_digest_background

        # Clear cache
        DIGEST_CACHE.clear()

        with patch('app.api.auth.get_db_context') as mock_db_context:
            mock_db = AsyncMock()
            mock_db_context.return_value.__aenter__.return_value = mock_db

            with patch('app.services.digest_service.digest_service') as mock_service:
                mock_service.generate_digest = AsyncMock(side_effect=Exception("DB error"))

                # Should not raise
                await preload_digest_background("user123", datetime(2024, 1, 1))

                # Cache should remain empty
                assert "user123" not in DIGEST_CACHE


class TestDigestEndpointCacheIntegration:
    """Tests for cache integration in the digest endpoint."""

    @pytest.mark.asyncio
    async def test_digest_endpoint_uses_cache_when_available(self):
        """Should return cached data without regenerating."""
        from app.api.auth import DIGEST_CACHE
        from app.api.digest import get_what_you_missed, DigestRequest

        # Setup cache
        DIGEST_CACHE.clear()
        cached_data = {
            "since": "2024-01-01T00:00:00",
            "results": [{"datasource": "slack", "summary": "Cached result"}],
            "summary": "Cached summary",
            "successful_sources": ["slack"],
            "failed_sources": [],
            "total_time_ms": 50,
        }
        DIGEST_CACHE["user123"] = {
            "data": cached_data,
            "timestamp": asyncio.get_event_loop().time(),
        }

        # Mock user and db
        mock_user = MagicMock()
        mock_user.id = "user123"
        mock_user.email = "test@example.com"
        mock_user.previous_login = datetime(2024, 1, 1)
        mock_db = AsyncMock()

        with patch('app.services.digest_service.digest_service') as mock_service:
            mock_service.generate_digest = AsyncMock()

            result = await get_what_you_missed(
                request=None,
                current_user=mock_user,
                db=mock_db
            )

            # Should return cached data
            assert result.summary == "Cached summary"
            assert result.total_time_ms == 50

            # Should NOT call digest_service
            mock_service.generate_digest.assert_not_called()

    @pytest.mark.asyncio
    async def test_digest_endpoint_bypasses_cache_for_custom_time(self):
        """Should not use cache when custom 'since' timestamp provided."""
        from app.api.auth import DIGEST_CACHE
        from app.api.digest import get_what_you_missed, DigestRequest

        # Setup cache
        DIGEST_CACHE.clear()
        cached_data = {
            "since": "2024-01-01T00:00:00",
            "results": [],
            "summary": "Cached",
            "successful_sources": [],
            "failed_sources": [],
            "total_time_ms": 50,
        }
        DIGEST_CACHE["user123"] = {
            "data": cached_data,
            "timestamp": asyncio.get_event_loop().time(),
        }

        fresh_data = {
            "since": "2024-06-01T00:00:00",
            "results": [],
            "summary": "Fresh",
            "successful_sources": [],
            "failed_sources": [],
            "total_time_ms": 100,
        }

        mock_user = MagicMock()
        mock_user.id = "user123"
        mock_user.email = "test@example.com"
        mock_user.previous_login = datetime(2024, 1, 1)
        mock_db = AsyncMock()

        # Patch at the module level where it's imported
        with patch('app.api.digest.digest_service') as mock_service:
            mock_service.generate_digest = AsyncMock(return_value=fresh_data)

            request = DigestRequest(since=datetime(2024, 6, 1))
            result = await get_what_you_missed(
                request=request,
                current_user=mock_user,
                db=mock_db
            )

            # Should return fresh data, not cached
            assert result.summary == "Fresh"

            # Should call digest_service
            mock_service.generate_digest.assert_called_once()
