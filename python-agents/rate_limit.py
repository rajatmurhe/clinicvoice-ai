"""Small per-key sliding window rate limiter (in memory, per process)."""

import threading
import time


class SlidingWindowLimiter:
    def __init__(self, max_requests, window_seconds):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits = {}
        self._lock = threading.Lock()

    def allow(self, key):
        now = time.time()
        with self._lock:
            bucket = [t for t in self._hits.get(key, []) if now - t < self.window_seconds]
            if len(bucket) >= self.max_requests:
                self._hits[key] = bucket
                return False
            bucket.append(now)
            self._hits[key] = bucket
            return True
