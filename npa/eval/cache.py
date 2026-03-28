"""Multi-layer cache system for query evaluation.

Provides both intra-query (per-evaluation) and inter-query (shared, TTL-based) caching
for maximum performance with configurable eviction policies.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


class CacheMiss(Exception):
    """Raised when a cache lookup misses."""


@dataclass(frozen=True)
class CacheKey:
    """Immutable, hashable cache key."""
    module: str
    rule: str
    input_hash: str

    @staticmethod
    def build(module: str, rule: str, input_data: Any) -> CacheKey:
        raw = f"{module}/{rule}:{_stable_hash(input_data)}"
        return CacheKey(module=module, rule=rule, input_hash=hashlib.sha256(raw.encode()).hexdigest()[:16])


@dataclass
class CacheEntry:
    value: Any
    created_at: float = field(default_factory=time.monotonic)
    hit_count: int = 0


class IntraQueryCache:
    """Per-evaluation cache — fast, no TTL, no thread safety needed."""

    __slots__ = ("_store",)

    def __init__(self) -> None:
        self._store: dict[CacheKey, Any] = {}

    def get(self, key: CacheKey) -> Any:
        if key in self._store:
            return self._store[key]
        raise CacheMiss(key)

    def put(self, key: CacheKey, value: Any) -> None:
        self._store[key] = value

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


class InterQueryCache:
    """Shared cache across evaluations — thread-safe, LRU eviction, TTL support.

    Uses an OrderedDict for O(1) LRU operations with a lock for concurrency.
    """

    def __init__(self, max_size: int = 10_000, ttl_seconds: float = 300.0) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._store: OrderedDict[CacheKey, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: CacheKey) -> Any:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                raise CacheMiss(key)
            if time.monotonic() - entry.created_at > self._ttl:
                del self._store[key]
                self._misses += 1
                raise CacheMiss(key)
            self._store.move_to_end(key)
            entry.hit_count += 1
            self._hits += 1
            return entry.value

    def put(self, key: CacheKey, value: Any) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self._store[key] = CacheEntry(value=value)
            else:
                if len(self._store) >= self._max_size:
                    self._store.popitem(last=False)
                self._store[key] = CacheEntry(value=value)

    def invalidate(self, key: CacheKey) -> None:
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, module: str) -> int:
        """Invalidate all entries for a given module path."""
        with self._lock:
            to_remove = [k for k in self._store if k.module.startswith(module)]
            for k in to_remove:
                del self._store[k]
            return len(to_remove)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    @property
    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "size": len(self._store),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / max(1, self._hits + self._misses) * 100, 1),
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


def _stable_hash(obj: Any) -> str:
    """Create a stable string representation for hashing."""
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, float)):
        return str(obj)
    if isinstance(obj, str):
        return f'"{obj}"'
    if isinstance(obj, list):
        return "[" + ",".join(_stable_hash(v) for v in obj) + "]"
    if isinstance(obj, dict):
        items = sorted(obj.items(), key=lambda kv: str(kv[0]))
        return "{" + ",".join(f"{_stable_hash(k)}:{_stable_hash(v)}" for k, v in items) + "}"
    if isinstance(obj, (set, frozenset)):
        return "{" + ",".join(sorted(_stable_hash(v) for v in obj)) + "}"
    return str(obj)
