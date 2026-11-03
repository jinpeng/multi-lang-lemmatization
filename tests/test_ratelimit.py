from api.auth.ratelimit import RateLimiter


def test_allows_requests_under_the_limit():
    rl = RateLimiter()
    for i in range(5):
        assert rl.check("k1", rpm=60, burst=5, now=1000.0 + i * 0.01).allowed


def test_blocks_once_burst_is_exhausted():
    rl = RateLimiter()
    for _ in range(5):
        rl.check("k1", rpm=60, burst=5, now=1000.0)
    result = rl.check("k1", rpm=60, burst=5, now=1000.0)
    assert result.allowed is False
    assert result.retry_after >= 1


def test_refills_over_time():
    rl = RateLimiter()
    for _ in range(5):
        rl.check("k1", rpm=60, burst=5, now=1000.0)
    # 60 rpm = 1 token/sec, so 1s should release exactly one
    assert rl.check("k1", rpm=60, burst=5, now=1001.0).allowed is True


def test_keys_are_isolated():
    rl = RateLimiter()
    for _ in range(5):
        rl.check("k1", rpm=60, burst=5, now=1000.0)
    assert rl.check("k2", rpm=60, burst=5, now=1000.0).allowed is True


def test_remaining_is_reported():
    rl = RateLimiter()
    result = rl.check("k1", rpm=60, burst=5, now=1000.0)
    assert result.remaining == 4
    assert result.limit == 5
