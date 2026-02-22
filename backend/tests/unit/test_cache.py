"""
Unit tests for cache service.
"""

import time
import pytest
from threading import Thread

from app.core.cache import (
    InMemoryCache,
    CacheService,
    CacheEntry,
    create_cache_service,
)
from app.core.enums import CacheType


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_cache_entry_creation(self):
        """Test CacheEntry creation."""
        entry = CacheEntry(value="test", timestamp=time.time(), ttl=60)
        assert entry.value == "test"
        assert entry.ttl == 60
        assert entry.hits == 0

    def test_cache_entry_not_expired(self):
        """Test CacheEntry is not expired when fresh."""
        entry = CacheEntry(value="test", timestamp=time.time(), ttl=60)
        assert not entry.is_expired()

    def test_cache_entry_expired(self):
        """Test CacheEntry is expired after TTL."""
        entry = CacheEntry(value="test", timestamp=time.time() - 70, ttl=60)
        assert entry.is_expired()

    def test_cache_entry_touch(self):
        """Test CacheEntry touch increments hits."""
        entry = CacheEntry(value="test", timestamp=time.time(), ttl=60)
        assert entry.hits == 0
        entry.touch()
        assert entry.hits == 1
        entry.touch()
        assert entry.hits == 2


class TestInMemoryCache:
    """Tests for InMemoryCache backend."""

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = InMemoryCache()
        cache.set("key1", "value1", ttl=60)
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self):
        """Test getting a non-existent key."""
        cache = InMemoryCache()
        assert cache.get("missing") is None

    def test_get_expired_key(self):
        """Test getting an expired key returns None."""
        cache = InMemoryCache()
        cache.set("key1", "value1", ttl=1)
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_exists(self):
        """Test exists check."""
        cache = InMemoryCache()
        cache.set("key1", "value1", ttl=60)
        assert cache.exists("key1") is True
        assert cache.exists("missing") is False

    def test_delete(self):
        """Test delete operation."""
        cache = InMemoryCache()
        cache.set("key1", "value1", ttl=60)
        assert cache.exists("key1") is True
        assert cache.delete("key1") is True
        assert cache.exists("key1") is False
        assert cache.delete("missing") is False

    def test_clear(self):
        """Test clear operation."""
        cache = InMemoryCache()
        cache.set("key1", "value1", ttl=60)
        cache.set("key2", "value2", ttl=60)
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_lru_eviction(self):
        """Test LRU eviction when max_size is reached."""
        cache = InMemoryCache(max_size=3)
        cache.set("key1", "value1", ttl=60)
        cache.set("key2", "value2", ttl=60)
        cache.set("key3", "value3", ttl=60)

        # Access key1 to make it more recently used
        cache.get("key1")

        # Add new key - should evict key2 (least recently used)
        cache.set("key4", "value4", ttl=60)

        assert cache.get("key1") == "value1"  # Still there (was accessed)
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") == "value3"  # Still there
        assert cache.get("key4") == "value4"  # New key

    def test_get_stats(self):
        """Test statistics tracking."""
        cache = InMemoryCache()
        cache.set("key1", "value1", ttl=60)

        # Miss
        cache.get("missing")

        # Hit
        cache.get("key1")
        cache.get("key1")

        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["hit_rate"] == pytest.approx(0.667, rel=0.01)

    def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        cache = InMemoryCache()
        cache.set("key1", "value1", ttl=1)
        cache.set("key2", "value2", ttl=60)

        time.sleep(1.1)

        removed = cache.cleanup_expired()
        assert removed == 1
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"

    def test_thread_safety(self):
        """Test thread-safe operations."""
        cache = InMemoryCache()
        errors = []

        def writer():
            try:
                for i in range(100):
                    cache.set(f"key{i}", f"value{i}", ttl=60)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for i in range(100):
                    cache.get(f"key{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            Thread(target=writer),
            Thread(target=reader),
            Thread(target=writer),
            Thread(target=reader),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestCacheService:
    """Tests for CacheService."""

    def test_tools_cache(self):
        """Test tool definitions caching."""
        service = CacheService()
        tools = [{"name": "list_channels", "description": "List channels"}]

        # Initially empty
        assert service.get_tools("slack") is None

        # Set and get
        service.set_tools("slack", tools)
        assert service.get_tools("slack") == tools

        # Invalidate
        service.invalidate_tools("slack")
        assert service.get_tools("slack") is None

    def test_results_cache(self):
        """Test tool result caching."""
        service = CacheService()
        result = {"channels": ["general", "random"]}
        args = {"limit": 100}

        # Initially empty
        assert service.get_result("slack", "list_channels", args) is None

        # Set and get
        service.set_result("slack", "list_channels", args, result)
        assert service.get_result("slack", "list_channels", args) == result

        # Different args should be cache miss
        assert service.get_result("slack", "list_channels", {"limit": 50}) is None

    def test_schema_cache(self):
        """Test schema caching."""
        service = CacheService()
        schema = "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(255))"

        # Set and get
        service.set_schema("users", schema)
        assert service.get_schema("users") == schema

    def test_session_cache(self):
        """Test session caching."""
        service = CacheService()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        # Set and get
        service.set_session("session-123", messages)
        assert service.get_session("session-123") == messages

        # Append
        service.append_to_session("session-123", {"role": "user", "content": "How are you?"})
        session = service.get_session("session-123")
        assert len(session) == 3

        # Delete
        service.delete_session("session-123")
        assert service.get_session("session-123") is None

    def test_key_generation(self):
        """Test cache key generation."""
        key = CacheService._make_key(CacheType.TOOLS, "slack")
        assert key == "tools:slack"

        key = CacheService._make_key(CacheType.RESULTS, "slack", "list_channels", "abc123")
        assert key == "results:slack:list_channels:abc123"

    def test_args_hashing(self):
        """Test argument hashing for cache keys."""
        # Same args should produce same hash
        hash1 = CacheService._hash_args({"limit": 100, "query": "test"})
        hash2 = CacheService._hash_args({"query": "test", "limit": 100})  # Different order
        assert hash1 == hash2

        # Different args should produce different hash
        hash3 = CacheService._hash_args({"limit": 50, "query": "test"})
        assert hash1 != hash3

    def test_get_stats(self):
        """Test getting cache statistics."""
        service = CacheService()
        service.set_tools("slack", [])
        service.get_tools("slack")  # Hit
        service.get_tools("jira")  # Miss

        stats = service.get_stats()
        assert "hits" in stats
        assert "misses" in stats

    def test_clear_all(self):
        """Test clearing all caches."""
        service = CacheService()
        service.set_tools("slack", [])
        service.set_result("jira", "list_issues", {}, [])
        service.set_schema("users", "schema")

        service.clear_all()

        assert service.get_tools("slack") is None
        assert service.get_result("jira", "list_issues", {}) is None


class TestCreateCacheService:
    """Tests for cache service factory function."""

    def test_create_in_memory_cache(self):
        """Test creating in-memory cache service."""
        service = create_cache_service(use_redis=False)
        assert service is not None
        assert isinstance(service._backend, InMemoryCache)

    def test_create_redis_cache_fallback(self):
        """Test Redis cache falls back to in-memory when unavailable."""
        # This should fall back to in-memory since Redis isn't running
        service = create_cache_service(
            use_redis=True,
            redis_url="redis://localhost:6380",  # Wrong port
        )
        assert service is not None
        assert isinstance(service._backend, InMemoryCache)
