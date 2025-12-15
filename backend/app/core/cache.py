"""
Cache service for ConnectorMCP.

Provides a unified caching interface with support for:
- In-memory caching (default)
- Redis caching (production)
- LRU eviction policy
- TTL-based expiration
"""

import hashlib
import json
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Generic, List, Optional, TypeVar

from app.core.enums import CacheTTL, CacheType
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """A cached value with metadata."""

    value: T
    timestamp: float
    ttl: int
    hits: int = 0

    def is_expired(self) -> bool:
        """Check if the entry has expired."""
        return time.time() - self.timestamp > self.ttl

    def touch(self) -> None:
        """Update hit count."""
        self.hits += 1


class CacheBackend(ABC):
    """Abstract cache backend interface."""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int) -> None:
        """Set a value in cache with TTL."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all cached values."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        pass


class InMemoryCache(CacheBackend):
    """
    Thread-safe in-memory cache with LRU eviction.

    Features:
    - LRU eviction when max_size is reached
    - TTL-based expiration
    - Thread-safe operations
    """

    def __init__(self, max_size: int = 1000):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._lock = Lock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache, returning None if expired or missing."""
        with self._lock:
            if key not in self._cache:
                self._stats["misses"] += 1
                return None

            entry = self._cache[key]

            if entry.is_expired():
                del self._cache[key]
                self._stats["misses"] += 1
                return None

            # Move to end for LRU
            self._cache.move_to_end(key)
            entry.touch()
            self._stats["hits"] += 1

            return entry.value

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL."""
        with self._lock:
            # Evict if at capacity
            while len(self._cache) >= self._max_size:
                self._evict_oldest()

            self._cache[key] = CacheEntry(
                value=value,
                timestamp=time.time(),
                ttl=ttl,
            )
            # Move to end (most recently used)
            self._cache.move_to_end(key)

    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all cached values."""
        with self._lock:
            self._cache.clear()

    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        with self._lock:
            if key not in self._cache:
                return False
            entry = self._cache[key]
            if entry.is_expired():
                del self._cache[key]
                return False
            return True

    def _evict_oldest(self) -> None:
        """Evict the oldest (least recently used) entry."""
        if self._cache:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            self._stats["evictions"] += 1
            logger.debug(f"Evicted cache entry: {oldest_key[:20]}...")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            hit_rate = (
                self._stats["hits"] / (self._stats["hits"] + self._stats["misses"])
                if (self._stats["hits"] + self._stats["misses"]) > 0
                else 0
            )
            return {
                **self._stats,
                "size": len(self._cache),
                "max_size": self._max_size,
                "hit_rate": round(hit_rate, 3),
            }

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of removed entries."""
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items() if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)


class CacheService:
    """
    Unified cache service for the application.

    Provides separate caches for different data types with appropriate
    TTLs and eviction policies.

    Usage:
        cache = CacheService()

        # Tool definitions cache
        tools = cache.get_tools("slack")
        if not tools:
            tools = await fetch_tools()
            cache.set_tools("slack", tools)

        # Result cache
        result = cache.get_result("slack", "list_channels", {})
        if not result:
            result = await call_tool()
            cache.set_result("slack", "list_channels", {}, result)
    """

    def __init__(
        self,
        backend: Optional[CacheBackend] = None,
        tools_ttl: int = CacheTTL.TOOLS,
        results_ttl: int = CacheTTL.RESULTS,
        schema_ttl: int = CacheTTL.SCHEMA,
        max_size: int = 1000,
    ):
        self._backend = backend or InMemoryCache(max_size=max_size)
        self._tools_ttl = tools_ttl
        self._results_ttl = results_ttl
        self._schema_ttl = schema_ttl

    # ============ Key Generation ============

    @staticmethod
    def _make_key(cache_type: CacheType, *parts: str) -> str:
        """Generate a cache key from parts."""
        return f"{cache_type.value}:{':'.join(parts)}"

    @staticmethod
    def _hash_args(args: Dict[str, Any]) -> str:
        """Generate a hash of tool arguments for cache key."""
        args_str = json.dumps(args, sort_keys=True)
        return hashlib.md5(args_str.encode()).hexdigest()[:12]

    # ============ Tools Cache ============

    def get_tools(self, datasource: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached tool definitions for a datasource."""
        key = self._make_key(CacheType.TOOLS, datasource)
        result = self._backend.get(key)
        if result:
            logger.debug(f"Tools cache hit for {datasource}")
        return result

    def set_tools(self, datasource: str, tools: List[Dict[str, Any]]) -> None:
        """Cache tool definitions for a datasource."""
        key = self._make_key(CacheType.TOOLS, datasource)
        self._backend.set(key, tools, self._tools_ttl)
        logger.debug(f"Cached {len(tools)} tools for {datasource}")

    def invalidate_tools(self, datasource: str) -> None:
        """Invalidate cached tools for a datasource."""
        key = self._make_key(CacheType.TOOLS, datasource)
        self._backend.delete(key)
        logger.debug(f"Invalidated tools cache for {datasource}")

    # ============ Results Cache ============

    def get_result(
        self,
        datasource: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Optional[Any]:
        """Get cached tool result."""
        args_hash = self._hash_args(arguments)
        key = self._make_key(CacheType.RESULTS, datasource, tool_name, args_hash)
        result = self._backend.get(key)
        if result:
            logger.debug(f"Result cache hit for {datasource}/{tool_name}")
        return result

    def set_result(
        self,
        datasource: str,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """Cache a tool result."""
        args_hash = self._hash_args(arguments)
        key = self._make_key(CacheType.RESULTS, datasource, tool_name, args_hash)
        self._backend.set(key, result, ttl or self._results_ttl)
        logger.debug(f"Cached result for {datasource}/{tool_name}")

    def invalidate_result(
        self,
        datasource: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> None:
        """Invalidate a specific cached result."""
        args_hash = self._hash_args(arguments)
        key = self._make_key(CacheType.RESULTS, datasource, tool_name, args_hash)
        self._backend.delete(key)

    def invalidate_datasource_results(self, datasource: str) -> None:
        """Invalidate all cached results for a datasource."""
        # Note: This is a simplified implementation
        # A production implementation would use key patterns with Redis SCAN
        logger.info(f"Invalidating all results for {datasource}")
        self._backend.clear()  # Simplified - clears all for in-memory

    # ============ Schema Cache ============

    def get_schema(self, table_name: str) -> Optional[str]:
        """Get cached table schema."""
        key = self._make_key(CacheType.SCHEMA, table_name)
        return self._backend.get(key)

    def set_schema(self, table_name: str, schema: str) -> None:
        """Cache a table schema."""
        key = self._make_key(CacheType.SCHEMA, table_name)
        self._backend.set(key, schema, self._schema_ttl)
        logger.debug(f"Cached schema for {table_name}")

    def get_all_schemas(self) -> Dict[str, str]:
        """Get all cached schemas (for system prompt injection)."""
        # Note: Simplified implementation
        # Production would use Redis SCAN with pattern matching
        return {}

    # ============ Session Cache ============

    def get_session(self, session_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached session messages."""
        key = self._make_key(CacheType.SESSION, session_id)
        return self._backend.get(key)

    def set_session(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        ttl: int = CacheTTL.SESSION,
    ) -> None:
        """Cache session messages."""
        key = self._make_key(CacheType.SESSION, session_id)
        self._backend.set(key, messages, ttl)

    def append_to_session(
        self,
        session_id: str,
        message: Dict[str, Any],
    ) -> None:
        """Append a message to cached session."""
        messages = self.get_session(session_id) or []
        messages.append(message)
        self.set_session(session_id, messages)

    def delete_session(self, session_id: str) -> None:
        """Delete a cached session."""
        key = self._make_key(CacheType.SESSION, session_id)
        self._backend.delete(key)

    # ============ Utility Methods ============

    def clear_all(self) -> None:
        """Clear all caches."""
        self._backend.clear()
        logger.info("Cleared all caches")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if isinstance(self._backend, InMemoryCache):
            return self._backend.get_stats()
        return {}

    def cleanup(self) -> int:
        """Clean up expired entries. Returns count of removed entries."""
        if isinstance(self._backend, InMemoryCache):
            count = self._backend.cleanup_expired()
            if count > 0:
                logger.info(f"Cleaned up {count} expired cache entries")
            return count
        return 0


# ============ Redis Backend (Production) ============


class RedisCache(CacheBackend):
    """
    Redis-backed cache for production deployments.

    Requires redis-py: pip install redis
    """

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        try:
            import redis

            self._client = redis.from_url(redis_url, decode_responses=True)
            self._client.ping()
            logger.info(f"Connected to Redis at {redis_url}")
        except ImportError:
            raise ImportError("redis package required: pip install redis")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Redis: {e}")

    def get(self, key: str) -> Optional[Any]:
        """Get value from Redis."""
        value = self._client.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in Redis with TTL."""
        serialized = json.dumps(value) if not isinstance(value, str) else value
        self._client.setex(key, ttl, serialized)

    def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        return self._client.delete(key) > 0

    def clear(self) -> None:
        """Clear all keys (use with caution!)."""
        self._client.flushdb()

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        return self._client.exists(key) > 0


# ============ Factory Function ============


def create_cache_service(
    use_redis: bool = False,
    redis_url: str = "redis://localhost:6379",
    **kwargs,
) -> CacheService:
    """
    Factory function to create appropriate cache service.

    Args:
        use_redis: Whether to use Redis backend
        redis_url: Redis connection URL
        **kwargs: Additional arguments for CacheService

    Returns:
        Configured CacheService instance
    """
    if use_redis:
        try:
            backend = RedisCache(redis_url)
            logger.info("Using Redis cache backend")
        except Exception as e:
            logger.warning(f"Redis unavailable, falling back to in-memory: {e}")
            backend = InMemoryCache()
    else:
        backend = InMemoryCache()
        logger.info("Using in-memory cache backend")

    return CacheService(backend=backend, **kwargs)


# Global cache instance (will be properly initialized in main.py)
cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get the global cache service instance."""
    global cache_service
    if cache_service is None:
        cache_service = create_cache_service()
    return cache_service


def init_cache_service(use_redis: bool = False, redis_url: str = None) -> CacheService:
    """Initialize the global cache service."""
    global cache_service
    cache_service = create_cache_service(
        use_redis=use_redis,
        redis_url=redis_url or "redis://localhost:6379",
    )
    return cache_service
