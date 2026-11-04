"""Per-key token bucket.

In-memory, unlike the nonce cache (which is shared through SQLite because
replay protection must hold across workers). Each `--workers` process keeps its
own buckets, so the effective limit is roughly `rpm x workers`; a replica-per-
process cache would leave the same gap. The bucket is keyed by key_id, so one
abusive tenant cannot starve another.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass


@dataclass
class Decision:
    allowed: bool
    remaining: int
    limit: int
    retry_after: int = 0


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}

    def check(self, key_id: str, *, rpm: int, burst: int, now: float | None = None) -> Decision:
        current = time.time() if now is None else now
        rate_per_second = rpm / 60.0

        tokens, last = self._buckets.get(key_id, (float(burst), current))
        tokens = min(float(burst), tokens + (current - last) * rate_per_second)

        if tokens >= 1.0:
            tokens -= 1.0
            self._buckets[key_id] = (tokens, current)
            return Decision(allowed=True, remaining=int(tokens), limit=burst)

        self._buckets[key_id] = (tokens, current)
        deficit = 1.0 - tokens
        retry_after = max(1, math.ceil(deficit / rate_per_second))
        return Decision(allowed=False, remaining=0, limit=burst, retry_after=retry_after)
