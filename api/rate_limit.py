"""Foundation rate limiting (EPIC-M1.132).

A real, enforced, in-memory fixed-window limiter keyed by client identity
(bearer token subject once M1.145 lands, falling back to client host).
This is intentionally a single-process implementation -- multi-instance
deployments need a shared store (e.g. Redis) behind the same
``RateLimiter`` interface, which is why the window bookkeeping is
isolated in one small class rather than scattered across middleware.
"""

from __future__ import annotations

import time
from collections import OrderedDict

from .errors import RateLimitedError

# Bounds steady-state memory growth from distinct client keys that stop sending
# requests (found in the 2026-08-21 QA/integration audit: `_hits` previously grew
# without bound for the life of the process). Sized well above any real deployment's
# concurrent-client count for this single-process limiter.
_DEFAULT_MAX_TRACKED_KEYS = 50_000


class RateLimiter:
    def __init__(self, *, limit: int, window_seconds: int, max_tracked_keys: int = _DEFAULT_MAX_TRACKED_KEYS) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_tracked_keys = max_tracked_keys
        # Ordered oldest-touched -> newest-touched: `check` always pops-and-reinserts
        # the key it touches, so the front of the dict is always the
        # least-recently-touched entry -- a correct place to look for expired windows
        # and, as a backstop, the right entry to evict first if the map still grows
        # past `max_tracked_keys` (e.g. many distinct keys within one window).
        self._hits: OrderedDict[str, tuple[float, int]] = OrderedDict()

    def check(self, key: str, *, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        window_start, count = self._hits.pop(key, (now, 0))
        if now - window_start >= self.window_seconds:
            window_start, count = now, 0
        count += 1
        self._hits[key] = (window_start, count)
        self._evict_stale(now)
        if count > self.limit:
            retry_after = max(1, int(self.window_seconds - (now - window_start)))
            raise RateLimitedError(retry_after)

    def _evict_stale(self, now: float) -> None:
        while self._hits:
            oldest_key, (window_start, _count) = next(iter(self._hits.items()))
            if now - window_start < self.window_seconds:
                break
            del self._hits[oldest_key]
        while len(self._hits) > self.max_tracked_keys:
            self._hits.popitem(last=False)

    def tracked_key_count(self) -> int:
        """For tests/observability -- not used in the request path."""
        return len(self._hits)


default_limiter = RateLimiter(limit=120, window_seconds=60)


def client_key(client_host: str | None, subject: str | None) -> str:
    return subject or client_host or "anonymous"
