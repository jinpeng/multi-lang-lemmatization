"""Batched request logging.

Two constraints shaped this:

1. Must not store request text (spec open item 3). Only shape is kept: language,
   token count, byte count. Storing bodies would turn this into a PII store.
2. Must not put a SQLite write on the hot path. Every request would contend for
   the single writer lock with `/v1/lemmatize`, which is the one thing that has
   to stay fast. Records are queued and written in batches by a flusher.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from api.db import session

MAX_QUEUE = 10_000
BATCH_SIZE = 200
RETENTION_DAYS = 7


@dataclass(frozen=True)
class Record:
    at: str
    request_id: str
    key_id: str | None
    lang: str | None
    n_tokens: int | None
    bytes_in: int | None
    latency_ms: int
    status: int
    error_code: str | None
    ip: str | None


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class RequestLogger:
    def __init__(self, url: str, max_queue: int = MAX_QUEUE) -> None:
        self._url = url
        self._queue: deque[Record] = deque(maxlen=max_queue)
        self._lock = threading.Lock()
        self.dropped = 0

    def record(
        self,
        *,
        request_id: str,
        key_id: str | None,
        lang: str | None,
        n_tokens: int | None,
        bytes_in: int | None,
        latency_ms: int,
        status: int,
        error_code: str | None,
        ip: str | None,
    ) -> None:
        rec = Record(
            at=_now(),
            request_id=request_id,
            key_id=key_id,
            lang=lang,
            n_tokens=n_tokens,
            bytes_in=bytes_in,
            latency_ms=latency_ms,
            status=status,
            error_code=error_code,
            ip=ip,
        )
        with self._lock:
            # deque(maxlen=...) silently evicts the oldest; count it so a
            # sustained overflow is visible instead of looking like quiet loss.
            if len(self._queue) == self._queue.maxlen:
                self.dropped += 1
            self._queue.append(rec)

    def pending(self) -> int:
        with self._lock:
            return len(self._queue)

    def flush(self, limit: int = BATCH_SIZE) -> int:
        with self._lock:
            batch = [self._queue.popleft() for _ in range(min(limit, len(self._queue)))]
        if not batch:
            return 0
        with session(self._url) as conn:
            conn.exec_driver_sql(
                """INSERT INTO request_log
                   (at, request_id, key_id, lang, n_tokens, bytes_in,
                    latency_ms, status, error_code, ip)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        r.at,
                        r.request_id,
                        r.key_id,
                        r.lang,
                        r.n_tokens,
                        r.bytes_in,
                        r.latency_ms,
                        r.status,
                        r.error_code,
                        r.ip,
                    )
                    for r in batch
                ],
            )
        return len(batch)

    def flush_all(self) -> int:
        total = 0
        while True:
            written = self.flush()
            total += written
            if written == 0:
                return total


def purge_older_than(url: str, days: int = RETENTION_DAYS) -> int:
    cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with session(url) as conn:
        result = conn.exec_driver_sql("DELETE FROM request_log WHERE at < ?", (cutoff,))
        return result.rowcount


def count(url: str) -> int:
    with session(url) as conn:
        return conn.exec_driver_sql("SELECT COUNT(*) FROM request_log").scalar() or 0


def recent(url: str, limit: int = 100, offset: int = 0) -> list[dict]:
    with session(url) as conn:
        rows = (
            conn.exec_driver_sql(
                """SELECT id, at, request_id, key_id, lang, n_tokens, bytes_in,
                          latency_ms, status, error_code, ip
                   FROM request_log ORDER BY id DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]
