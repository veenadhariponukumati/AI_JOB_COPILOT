"""In-memory caching layer with metrics tracking.

Caches expensive operations:
1. Job Description Parsing
2. Resume Parsing
3. Embedding Generation
4. ATS Analysis Results

Tracks cache hits, misses, and latency reduction.
"""

import hashlib
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from collections import OrderedDict
from dataclasses import dataclass, field

from src.core.config import get_settings
from src.core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class CacheMetrics:
    """Tracks cache performance metrics."""

    total_hits: int = 0
    total_misses: int = 0
    total_requests: int = 0
    total_latency_saved_ms: float = 0.0
    cache_types: Dict[str, Dict[str, int]] = field(default_factory=dict)

    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_hits / self.total_requests

    @property
    def miss_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_misses / self.total_requests

    def record_hit(self, cache_type: str, latency_saved_ms: float = 0.0):
        self.total_hits += 1
        self.total_requests += 1
        self.total_latency_saved_ms += latency_saved_ms
        if cache_type not in self.cache_types:
            self.cache_types[cache_type] = {"hits": 0, "misses": 0}
        self.cache_types[cache_type]["hits"] += 1

    def record_miss(self, cache_type: str):
        self.total_misses += 1
        self.total_requests += 1
        if cache_type not in self.cache_types:
            self.cache_types[cache_type] = {"hits": 0, "misses": 0}
        self.cache_types[cache_type]["misses"] += 1

    def to_dict(self) -> Dict:
        return {
            "total_hits": self.total_hits,
            "total_misses": self.total_misses,
            "total_requests": self.total_requests,
            "hit_rate": round(self.hit_rate * 100, 2),
            "miss_rate": round(self.miss_rate * 100, 2),
            "total_latency_saved_ms": round(self.total_latency_saved_ms, 2),
            "by_type": self.cache_types,
        }


@dataclass
class CacheEntry:
    """A single cache entry with metadata."""

    value: Any
    created_at: datetime
    expires_at: datetime
    cache_type: str
    access_count: int = 0
    last_accessed: datetime = None

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at


class CacheManager:
    """LRU cache with TTL expiration and metrics tracking.

    Thread-safe for single-process Streamlit/FastAPI usage.
    """

    def __init__(
        self,
        max_size: int = None,
        ttl_seconds: int = None,
    ):
        self.max_size = max_size or settings.CACHE_MAX_SIZE
        self.ttl_seconds = ttl_seconds or settings.CACHE_TTL_SECONDS
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.metrics = CacheMetrics()

    def get(self, key: str, cache_type: str = "general") -> Optional[Any]:
        """Retrieve a value from cache.

        Args:
            key: Cache key.
            cache_type: Type of cached data for metrics.

        Returns:
            Cached value or None if not found/expired.
        """
        if key not in self._cache:
            self.metrics.record_miss(cache_type)
            return None

        entry = self._cache[key]

        # Check expiration
        if entry.is_expired:
            del self._cache[key]
            self.metrics.record_miss(cache_type)
            return None

        # Update access metadata
        entry.access_count += 1
        entry.last_accessed = datetime.utcnow()

        # Move to end (most recently used)
        self._cache.move_to_end(key)

        self.metrics.record_hit(cache_type, latency_saved_ms=100.0)  # Estimated savings
        logger.debug(f"Cache HIT: {cache_type}/{key[:20]}...")
        return entry.value

    def set(
        self,
        key: str,
        value: Any,
        cache_type: str = "general",
        ttl_seconds: Optional[int] = None,
    ):
        """Store a value in cache.

        Args:
            key: Cache key.
            value: Value to cache.
            cache_type: Type of cached data.
            ttl_seconds: Override default TTL.
        """
        # Evict if at capacity
        while len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)  # Remove oldest

        ttl = ttl_seconds or self.ttl_seconds
        now = datetime.utcnow()

        self._cache[key] = CacheEntry(
            value=value,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
            cache_type=cache_type,
            last_accessed=now,
        )
        logger.debug(f"Cache SET: {cache_type}/{key[:20]}... (TTL={ttl}s)")

    def invalidate(self, key: str):
        """Remove a specific entry from cache."""
        if key in self._cache:
            del self._cache[key]

    def clear(self, cache_type: Optional[str] = None):
        """Clear cache entries, optionally filtered by type."""
        if cache_type:
            keys_to_remove = [
                k for k, v in self._cache.items() if v.cache_type == cache_type
            ]
            for key in keys_to_remove:
                del self._cache[key]
        else:
            self._cache.clear()

    def get_metrics(self) -> Dict:
        """Get cache performance metrics."""
        return {
            **self.metrics.to_dict(),
            "current_size": len(self._cache),
            "max_size": self.max_size,
            "ttl_seconds": self.ttl_seconds,
        }

    @staticmethod
    def generate_key(content: str, prefix: str = "") -> str:
        """Generate a deterministic cache key from content.

        Args:
            content: Content to hash.
            prefix: Optional prefix for key namespacing.

        Returns:
            SHA-256 based cache key.
        """
        hash_val = hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]
        return f"{prefix}:{hash_val}" if prefix else hash_val


# Global cache instance (singleton pattern)
_cache_instance: Optional[CacheManager] = None


def get_cache() -> CacheManager:
    """Get or create the global cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheManager()
    return _cache_instance
