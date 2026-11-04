import pytest

from api.auth.nonce import NonceCache, SqliteNonceCache


def test_first_use_is_accepted():
    cache = NonceCache()
    assert cache.consume("n1", now=1000.0) is True


def test_replay_is_rejected():
    cache = NonceCache()
    cache.consume("n1", now=1000.0)
    assert cache.consume("n1", now=1000.0) is False


def test_entry_expires_after_ttl():
    cache = NonceCache(ttl_seconds=10)
    cache.consume("n1", now=1000.0)
    assert cache.consume("n1", now=1009.0) is False
    assert cache.consume("n1", now=1011.0) is True


def test_capacity_is_bounded():
    cache = NonceCache(max_entries=3)
    for i in range(10):
        cache.consume(f"n{i}", now=1000.0 + i)
    assert cache.size() <= 3


def test_evicted_nonce_becomes_accepted_again_documented_tradeoff():
    """Capacity eviction trades replay protection for bounded memory.

    A hostile client that floods nonces can evict its own earlier entries. This
    is acceptable because the nonce is only one of three replay defences (the
    timestamp window and the signature also apply), but it must be explicit.
    """
    cache = NonceCache(max_entries=2, ttl_seconds=10_000)
    cache.consume("target", now=1000.0)
    cache.consume("a", now=1001.0)
    cache.consume("b", now=1002.0)  # evicts "target"
    assert cache.consume("target", now=1003.0) is True


@pytest.fixture
def db_url(tmp_path):
    from api.db import init_db

    url = f"sqlite:///{tmp_path / 'n.db'}"
    init_db(url)
    return url


def test_sqlite_cache_rejects_replay(db_url):
    cache = SqliteNonceCache(db_url)
    assert cache.consume("n1", now=1000.0) is True
    assert cache.consume("n1", now=1000.0) is False


def test_sqlite_cache_is_shared_between_instances(db_url):
    """The regression: two workers each had their own dict, so a nonce consumed
    by one was unknown to the other and the replay succeeded."""
    worker_a = SqliteNonceCache(db_url)
    worker_b = SqliteNonceCache(db_url)
    assert worker_a.consume("shared", now=1000.0) is True
    assert worker_b.consume("shared", now=1000.0) is False


def test_sqlite_cache_purges_old_rows(db_url):
    cache = SqliteNonceCache(db_url)
    cache.consume("old", now=1000.0)
    cache.consume("new", now=1000.0 + 7200)
    assert cache.size() == 2
    removed = cache.purge(now=1000.0 + 7200)
    assert removed >= 1
    assert cache.consume("old", now=1000.0 + 7200) is True
