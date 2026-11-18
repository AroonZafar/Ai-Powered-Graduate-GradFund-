"""Thread-safe in-memory sliding-window rate limiter.

Per-process only. For multi-worker production deployments this must be backed by a
shared store (Redis); the interface is kept small so that swap is local.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._hits[key]
        while q and now - q[0] >= self._window:
            q.popleft()
        if not q:
            self._hits.pop(key, None)
            return self._hits[key]
        return q

    def retry_after(self, key: str) -> int:
        """Seconds until the key may act again; 0 if it is under the limit."""
        with self._lock:
            now = self._clock()
            q = self._prune(key, now)
            if len(q) < self._limit:
                return 0
            return max(1, int(self._window - (now - q[0])) + 1)

    def record(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            self._prune(key, now).append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)
