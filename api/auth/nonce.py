"""In-memory nonce cache for HMAC replay protection.

SINGLE-INSTANCE ONLY. The spec accepts this because decision 5 pins a single
container. If the API is ever horizontally scaled, this must move to a shared
store or nonces will replay across instances. See the risk table in the spec.
"""

from __future__ import annotations

import time
from collections import OrderedDict


class NonceCache:
    def __init__(self, ttl_seconds: int = 600, max_entries: int = 100_000) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._seen: OrderedDict[str, float] = OrderedDict()

    def consume(self, nonce: str, now: float | None = None) -> bool:
        """Record a nonce. Returns False if it was already used and still live."""
        current = time.time() if now is None else now
        self._expire(current)

        if nonce in self._seen:
            return False

        self._seen[nonce] = current
        while len(self._seen) > self._max:
            self._seen.popitem(last=False)
        return True

    def _expire(self, now: float) -> None:
        cutoff = now - self._ttl
        while self._seen:
            oldest_nonce, seen_at = next(iter(self._seen.items()))
            if seen_at >= cutoff:
                break
            self._seen.pop(oldest_nonce)

    def size(self) -> int:
        return len(self._seen)
