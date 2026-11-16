"""The miss counter: limits per session and per address, only misses count, the window slides."""

from __future__ import annotations

import pytest
from tl_web import scan_limit
from tl_web.scan_limit import MissCounter


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make(clock: Clock, **more: int) -> MissCounter:
    return MissCounter(clock=clock, **more)


def test_the_constants_are_the_ones_of_the_spec() -> None:
    assert (scan_limit.MISS_LIMIT_SESSION, scan_limit.MISS_LIMIT_ADDRESS) == (10, 30)
    assert scan_limit.WINDOW_S == 600


def test_a_session_is_limited_after_its_tenth_miss_and_not_before() -> None:
    clock = Clock()
    counter = make(clock)
    for n in range(scan_limit.MISS_LIMIT_SESSION):
        assert counter.retry_after("tok", f"10.0.0.{n}") == 0, n
        counter.record_miss("tok", f"10.0.0.{n}")
    assert counter.retry_after("tok", "10.9.9.9") > 0  # another address, the same session
    assert counter.retry_after("other", "10.9.9.9") == 0  # another session is free


def test_an_address_is_limited_after_its_thirtieth_miss_across_sessions() -> None:
    counter = make(Clock())
    for n in range(scan_limit.MISS_LIMIT_ADDRESS):
        assert counter.retry_after(f"tok{n}", "10.0.0.1") == 0, n
        counter.record_miss(f"tok{n}", "10.0.0.1")
    assert counter.retry_after("fresh", "10.0.0.1") > 0
    assert counter.retry_after("fresh", "10.0.0.2") == 0


def test_hits_are_never_counted() -> None:
    counter = make(Clock())
    for _ in range(100):  # a hit asks, finds the answer 0 and records nothing
        assert counter.retry_after("tok", "10.0.0.1") == 0
    assert counter.keys() == 0


def test_the_window_slides_and_retry_after_counts_down() -> None:
    clock = Clock()
    counter = make(clock, session_limit=2, address_limit=99)
    counter.record_miss("tok", "a")
    clock.now += 100
    counter.record_miss("tok", "a")
    assert counter.retry_after("tok", "a") == 500  # the first miss leaves at +600
    clock.now += 499
    assert counter.retry_after("tok", "a") == 1
    clock.now += 1
    assert counter.retry_after("tok", "a") == 0  # one miss left: below the limit
    counter.record_miss("tok", "a")
    assert counter.retry_after("tok", "a") > 0


def test_the_token_is_never_a_key() -> None:
    counter = make(Clock())
    counter.record_miss("super-secret-token", "a")
    assert all("super-secret-token" not in key for key in counter._seen)  # pyright: ignore[reportPrivateUsage]


def test_the_number_of_keys_is_capped_and_the_oldest_go_first() -> None:
    clock = Clock()
    counter = make(clock, max_keys=4, session_limit=1)
    for n in range(10):
        clock.now += 1
        counter.record_miss(f"tok{n}", f"addr{n}")
    assert counter.keys() == 4
    assert counter.retry_after("tok9", "x") > 0  # the newest are kept
    assert counter.retry_after("tok0", "x") == 0  # the oldest were dropped


def test_a_bad_setting_is_refused() -> None:
    with pytest.raises(ValueError):
        MissCounter(session_limit=0)
    with pytest.raises(ValueError):
        MissCounter(window_s=0)
