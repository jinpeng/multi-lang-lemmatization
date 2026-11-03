from datetime import UTC, datetime, timedelta

import pytest

from api.db import init_db, session
from api.obs.requestlog import RequestLogger, count, purge_older_than


@pytest.fixture
def url(tmp_path):
    u = f"sqlite:///{tmp_path / 't.db'}"
    init_db(u)
    return u


def _rec(logger, **over):
    base = dict(
        request_id="req_1",
        key_id="lk_a",
        lang="de",
        n_tokens=2,
        bytes_in=32,
        latency_ms=5,
        status=200,
        error_code=None,
        ip="127.0.0.1",
    )
    base.update(over)
    logger.record(**base)


def test_record_does_not_write_until_flush(url):
    logger = RequestLogger(url)
    _rec(logger)
    assert logger.pending() == 1
    assert count(url) == 0


def test_flush_persists_the_batch(url):
    logger = RequestLogger(url)
    _rec(logger)
    assert logger.flush() == 1
    assert count(url) == 1
    assert logger.pending() == 0


def test_flush_is_bounded_and_leaves_the_rest_queued(url):
    logger = RequestLogger(url)
    for i in range(10):
        _rec(logger, request_id=f"req_{i}")
    assert logger.flush(limit=4) == 4
    assert logger.pending() == 6
    assert logger.flush_all() == 6
    assert logger.pending() == 0


def test_no_request_text_column_is_stored(url):
    """Only shape is retained. Guard against a future body/PII column."""
    logger = RequestLogger(url)
    _rec(logger)
    logger.flush()
    with session(url) as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(request_log)")}
    assert cols == {
        "id",
        "at",
        "request_id",
        "key_id",
        "lang",
        "n_tokens",
        "bytes_in",
        "latency_ms",
        "status",
        "error_code",
        "ip",
    }
    assert not any(c in cols for c in ("body", "text", "payload", "query"))


def test_queue_overflow_is_counted_not_silent():
    logger = RequestLogger("sqlite://", max_queue=3)
    for i in range(5):
        _rec(logger, request_id=f"r{i}")
    assert logger.pending() == 3
    assert logger.dropped == 2


def test_purge_removes_only_old_rows(url):
    logger = RequestLogger(url)
    _rec(logger)
    logger.flush()
    with session(url) as conn:
        old = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.exec_driver_sql(
            """INSERT INTO request_log
               (at, request_id, key_id, lang, n_tokens, bytes_in, latency_ms,
                status, error_code, ip)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (old, "req_old", "lk_a", "de", 1, 8, 1, 200, None, None),
        )
    assert count(url) == 2
    assert purge_older_than(url, days=7) == 1
    assert count(url) == 1
