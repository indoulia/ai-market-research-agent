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

from .errors import RateLimitedError


class RateLimiter:
    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, tuple[float, int]] = {}

    def check(self, key: str, *, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        window_start, count = self._hits.get(key, (now, 0))
        if now - window_start >= self.window_seconds:
            window_start, count = now, 0
        count += 1
        self._hits[key] = (window_start, count)
        if count > self.limit:
            retry_after = max(1, int(self.window_seconds - (now - window_start)))
            raise RateLimitedError(retry_after)


default_limiter = RateLimiter(limit=120, window_seconds=60)


def client_key(client_host: str | None, subject: str | None) -> str:
    return subject or client_host or "anonymous"
