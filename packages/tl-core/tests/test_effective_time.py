"""The simulated-time override (FANOUT D5): scope, nesting, threads, and what it refuses."""

from __future__ import annotations

import contextvars
import threading
from datetime import UTC, datetime, timedelta, timezone

import pytest
from tl_core.util import current_effective_time, effective_time

WHEN = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)


def test_there_is_no_override_by_default() -> None:
    assert current_effective_time() is None


def test_the_block_sets_and_restores_the_override() -> None:
    with effective_time(WHEN):
        assert current_effective_time() == WHEN
    assert current_effective_time() is None


def test_blocks_nest_and_none_clears_an_outer_override() -> None:
    later = WHEN + timedelta(hours=1)
    with effective_time(WHEN):
        with effective_time(later):
            assert current_effective_time() == later
        assert current_effective_time() == WHEN
        with effective_time(None):
            assert current_effective_time() is None
        assert current_effective_time() == WHEN


def test_the_override_is_restored_when_the_block_raises() -> None:
    with pytest.raises(RuntimeError):
        with effective_time(WHEN):
            raise RuntimeError("boom")
    assert current_effective_time() is None


def test_a_naive_datetime_is_refused_and_sets_nothing() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        with effective_time(datetime(2026, 11, 2, 8, 0)):
            pass
    assert current_effective_time() is None


def test_another_timezone_is_kept_as_given() -> None:
    plus_two = datetime(2026, 11, 2, 10, 0, tzinfo=timezone(timedelta(hours=2)))
    with effective_time(plus_two):
        assert current_effective_time() == WHEN  # the same instant


def test_a_thread_does_not_see_the_override_unless_it_copies_the_context() -> None:
    seen: dict[str, datetime | None] = {}

    def plain() -> None:
        seen["plain"] = current_effective_time()

    with effective_time(WHEN):
        plain_thread = threading.Thread(target=plain)
        plain_thread.start()
        plain_thread.join(timeout=5)
        copied = contextvars.copy_context()
        copy_thread = threading.Thread(
            target=lambda: seen.__setitem__("copied", copied.run(current_effective_time))
        )
        copy_thread.start()
        copy_thread.join(timeout=5)
    assert seen == {"plain": None, "copied": WHEN}
