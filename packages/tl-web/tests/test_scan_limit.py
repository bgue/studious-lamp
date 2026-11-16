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


def miss(counter: MissCounter, token: str, address: str) -> int:
    """A lookup that turns out to be a miss: reserved and kept. Returns the wait (0: it ran)."""
    return counter.reserve(token, address)[0]


def make(clock: Clock, **more: int) -> MissCounter:
    return MissCounter(clock=clock, **more)


def test_the_constants_are_the_ones_of_the_spec() -> None:
    assert (scan_limit.MISS_LIMIT_SESSION, scan_limit.MISS_LIMIT_ADDRESS) == (10, 30)
    assert scan_limit.WINDOW_S == 600


def test_a_session_is_limited_after_its_tenth_miss_and_not_before() -> None:
    clock = Clock()
    counter = make(clock)
    for n in range(scan_limit.MISS_LIMIT_SESSION):
        assert miss(counter, "tok", f"10.0.0.{n}") == 0, n
    assert miss(counter, "tok", "10.9.9.9") > 0  # another address, the same session
    assert miss(counter, "other", "10.9.9.9") == 0  # another session is free


def test_an_address_is_limited_after_its_thirtieth_miss_across_sessions() -> None:
    counter = make(Clock())
    for n in range(scan_limit.MISS_LIMIT_ADDRESS):
        assert miss(counter, f"tok{n}", "10.0.0.1") == 0, n
    assert miss(counter, "fresh", "10.0.0.1") > 0
    assert miss(counter, "fresh", "10.0.0.2") == 0


def test_hits_are_never_counted() -> None:
    counter = make(Clock(), session_limit=2)
    for _ in range(100):  # a hit reserves, runs, and gives the count back
        wait, stamp = counter.reserve("tok", "10.0.0.1")
        assert wait == 0
        counter.refund("tok", "10.0.0.1", stamp)
    assert counter.keys() == 0


def test_concurrent_lookups_cannot_pass_the_limit() -> None:
    import threading

    counter = MissCounter(session_limit=10, address_limit=1000)
    ran: list[int] = []
    barrier = threading.Barrier(40)

    def lookup() -> None:
        barrier.wait()
        if counter.reserve("tok", "a")[0] == 0:
            ran.append(1)  # a miss: the count stays

    threads = [threading.Thread(target=lookup) for _ in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ran) == 10  # a burst gets exactly the limit, never more


def test_the_window_slides_and_the_wait_counts_down() -> None:
    clock = Clock()
    counter = make(clock, session_limit=2, address_limit=99)
    miss(counter, "tok", "a")
    clock.now += 100
    miss(counter, "tok", "a")
    assert (
        miss(counter, "tok", "a") == 500
    )  # the first miss leaves at +600; this one counted nothing
    clock.now += 499
    assert miss(counter, "tok", "a") == 1
    clock.now += 1
    assert miss(counter, "tok", "a") == 0  # one left in the window: below the limit
    assert miss(counter, "tok", "a") > 0


def test_the_token_is_never_a_key() -> None:
    counter = make(Clock())
    miss(counter, "super-secret-token", "a")
    assert all("super-secret-token" not in key for key in counter._seen)  # pyright: ignore[reportPrivateUsage]


def test_the_number_of_keys_is_capped_and_the_oldest_go_first() -> None:
    clock = Clock()
    counter = make(clock, max_keys=4, session_limit=1)
    for n in range(10):
        clock.now += 1
        miss(counter, f"tok{n}", f"addr{n}")
    assert counter.keys() == 4
    assert miss(counter, "tok9", "x") > 0  # the newest are kept
    assert miss(counter, "tok0", "x") == 0  # the oldest were dropped


def test_a_bad_setting_is_refused() -> None:
    with pytest.raises(ValueError):
        MissCounter(session_limit=0)
    with pytest.raises(ValueError):
        MissCounter(window_s=0)
