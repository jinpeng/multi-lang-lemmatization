from api.auth.nonce import NonceCache


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
