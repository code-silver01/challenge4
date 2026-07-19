"""In-memory token-bucket rate limiter per session_id.

Design
------
* Each session gets its own bucket with ``max_tokens`` capacity.
* Tokens refill at ``refill_rate`` per second.
* A request consumes 1 token; if empty, the request is rate-limited.

In production, swap for Redis-backed rate limiting (see README).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    """A single token bucket for one session."""

    tokens: float
    last_refill: float
    max_tokens: float


class RateLimiter:
    """Per-session rate limiter using the token-bucket algorithm.

    Usage::

        limiter = RateLimiter(max_rpm=30)
        if not limiter.allow("session-123"):
            raise HTTPException(429, "Too many requests")
    """

    def __init__(self, max_rpm: int = 30) -> None:
        self._max_tokens = float(max_rpm)
        self._refill_rate = max_rpm / 60.0  # tokens per second
        self._buckets: dict[str, _Bucket] = {}

    def allow(self, session_id: str) -> bool:
        """Check if a request from *session_id* is allowed.

        Parameters
        ----------
        session_id:
            The session making the request.

        Returns
        -------
        bool
            True if the request is allowed, False if rate-limited.
        """
        now = time.monotonic()
        bucket = self._buckets.get(session_id)

        if bucket is None:
            # First request — full bucket
            self._buckets[session_id] = _Bucket(
                tokens=self._max_tokens - 1,
                last_refill=now,
                max_tokens=self._max_tokens,
            )
            return True

        # Refill tokens based on elapsed time
        elapsed = now - bucket.last_refill
        bucket.tokens = min(
            bucket.max_tokens,
            bucket.tokens + elapsed * self._refill_rate,
        )
        bucket.last_refill = now

        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True

        return False

    def reset(self, session_id: str) -> None:
        """Reset a session's bucket (e.g. after key rotation)."""
        self._buckets.pop(session_id, None)

    def reset_all(self) -> None:
        """Clear all buckets — used in tests."""
        self._buckets.clear()
