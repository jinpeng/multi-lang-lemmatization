"""Nonce cache for HMAC replay protection.

Originally an in-process dict, which silently broke under `--workers 2`: a nonce
consumed by worker A was unknown to worker B, so a replayed request had roughly
a 50% chance of being accepted. Measured before the fix: 1 of 9 replays got a
200. State must therefore be shared, and SQLite already is.

`InMemoryNonceCache` is kept for single-process use and for the unit tests.
"""

from __future__ import annotations

import time
from collections import OrderedDict

from api.db import session

# Rows older than this can never match a live timestamp window (300s), so they
# are safe to purge. Kept comfortably above it.
_RETENTION_SECONDS = 3600
_PURGE_EVERY = 500


class InMemoryNonceCache:
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


class SqliteNonceCache:
    """Shared nonce store. One INSERT per HMAC-signed request.

    HMAC is the machine-to-machine path, not the interactive one, so a single
    indexed insert is affordable; correctness here is not optional.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._since_purge = 0

    def consume(self, nonce: str, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        with session(self._url) as conn:
            # INSERT OR IGNORE + rowcount is a single atomic claim: exactly one
            # caller can insert a given nonce, whichever worker it lands on.
            result = conn.exec_driver_sql(
                "INSERT OR IGNORE INTO hmac_nonces (nonce, seen_at) VALUES (?, ?)",
                (nonce, current),
            )
            claimed = result.rowcount == 1

        self._since_purge += 1
        if self._since_purge >= _PURGE_EVERY:
            self._since_purge = 0
            self.purge(current)
        return claimed

    def purge(self, now: float | None = None) -> int:
        cutoff = (time.time() if now is None else now) - _RETENTION_SECONDS
        with session(self._url) as conn:
            result = conn.exec_driver_sql("DELETE FROM hmac_nonces WHERE seen_at < ?", (cutoff,))
            return result.rowcount

    def size(self) -> int:
        with session(self._url) as conn:
            return conn.exec_driver_sql("SELECT COUNT(*) FROM hmac_nonces").scalar() or 0


# Backwards-compatible alias for existing call sites.
NonceCache = InMemoryNonceCache
