from __future__ import annotations

from app.ratelimit import RateLimiter


def test_sliding_window() -> None:
    now = [0.0]
    limiter = RateLimiter(limit=2, window_seconds=60, clock=lambda: now[0])
    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")
    now[0] = 60.5
    assert limiter.allow("a")


def test_rejected_requests_do_not_extend_the_block() -> None:
    now = [0.0]
    limiter = RateLimiter(limit=1, window_seconds=10, clock=lambda: now[0])
    assert limiter.allow("a")
    now[0] = 5
    assert not limiter.allow("a")
    now[0] = 10.5
    assert limiter.allow("a")
