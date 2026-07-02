"""Unit tests for the caching module."""

import pytest
import time
from src.cache.cache_manager import CacheManager


@pytest.fixture
def cache():
    return CacheManager(max_size=10, ttl_seconds=5)


class TestCacheManager:
    """Tests for CacheManager."""

    def test_set_and_get(self, cache):
        """Test basic set and get operations."""
        cache.set("key1", "value1", "test")
        result = cache.get("key1", "test")
        assert result == "value1"

    def test_get_nonexistent_key(self, cache):
        """Test getting a key that doesn't exist."""
        result = cache.get("nonexistent", "test")
        assert result is None

    def test_cache_expiration(self, cache):
        """Test that entries expire after TTL."""
        cache_short = CacheManager(max_size=10, ttl_seconds=1)
        cache_short.set("key1", "value1", "test")
        assert cache_short.get("key1", "test") == "value1"
        time.sleep(1.1)
        assert cache_short.get("key1", "test") is None

    def test_cache_eviction_lru(self, cache):
        """Test LRU eviction when cache is full."""
        for i in range(12):
            cache.set(f"key{i}", f"value{i}", "test")

        # First entries should be evicted
        assert cache.get("key0", "test") is None
        assert cache.get("key1", "test") is None
        # Recent entries should exist
        assert cache.get("key11", "test") == "value11"

    def test_metrics_tracking(self, cache):
        """Test that metrics are tracked correctly."""
        cache.set("key1", "value1", "test")
        cache.get("key1", "test")  # Hit
        cache.get("key2", "test")  # Miss

        metrics = cache.get_metrics()
        assert metrics["total_hits"] == 1
        assert metrics["total_misses"] == 1
        assert metrics["total_requests"] == 2
        assert metrics["hit_rate"] == 50.0

    def test_invalidate(self, cache):
        """Test cache invalidation."""
        cache.set("key1", "value1", "test")
        cache.invalidate("key1")
        assert cache.get("key1", "test") is None

    def test_clear_by_type(self, cache):
        """Test clearing cache by type."""
        cache.set("key1", "value1", "type_a")
        cache.set("key2", "value2", "type_b")
        cache.clear("type_a")
        assert cache.get("key1", "type_a") is None
        # Note: get increments miss count, so we check differently
        # key2 should still be in cache
        assert "key2" in cache._cache

    def test_generate_key(self, cache):
        """Test deterministic key generation."""
        key1 = CacheManager.generate_key("hello world", "test")
        key2 = CacheManager.generate_key("hello world", "test")
        key3 = CacheManager.generate_key("different", "test")
        assert key1 == key2
        assert key1 != key3

    def test_generate_key_with_prefix(self, cache):
        """Test key generation with prefix."""
        key = CacheManager.generate_key("content", "resume_parse")
        assert key.startswith("resume_parse:")
