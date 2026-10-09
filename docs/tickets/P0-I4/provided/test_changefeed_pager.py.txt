"""fetch_changes: filtered, paged reads of the event log with a resume cursor (P0-I4-T01)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from tl_core.changefeed import ChangePage, SubscriptionFilter, fetch_changes
from tl_core.changefeed.pager import MAX_SCAN_PAGES, PAGE
from tl_core.ledger import Event

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_event(
    seq: int,
    event_type: str = "Record.Created",
    scope: str = "project:P1",
    stream_id: str = "s1",
) -> Event:
    return Event(
        event_type=event_type,
        payload={},
        seq=seq,
        event_id=f"E{seq:025d}",
        stream_id=stream_id,
        stream_type="core.Record",
        stream_version=seq,
        scope=scope,
        actor="user:dev",
        recorded_at=NOW,
        effective_at=NOW,
        correlation_id="c",
        causation_id=None,
        source="test",
        prev_hash=None,
        hash="0" * 64,
    )


class FakeLedger:
    """Only ``read_after`` is real; it records every call."""

    def __init__(self, events: list[Event]) -> None:
        self.events = events
        self.calls: list[tuple[int, str | None, int]] = []

    def read_after(self, seq: int, *, scope: str | None = None, limit: int = 1000) -> list[Event]:
        self.calls.append((seq, scope, limit))
        found = [e for e in self.events if e.seq > seq and (scope is None or e.scope == scope)]
        return found[:limit]

    def __getattr__(self, name: str) -> Any:  # pragma: no cover
        # fetch_changes may only call read_after
        raise AssertionError(f"fetch_changes must only call read_after, not {name}")


def seqs(page: ChangePage) -> list[int]:
    return [event.seq for event in page.events]


def test_an_empty_ledger_gives_an_empty_page_at_the_same_cursor() -> None:
    page = fetch_changes(FakeLedger([]), after_seq=7)  # type: ignore[arg-type]
    assert page == ChangePage([], 7, False)


def test_everything_after_the_cursor_comes_back_in_order() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, 6)])
    page = fetch_changes(ledger, after_seq=2)  # type: ignore[arg-type]
    assert seqs(page) == [3, 4, 5]
    assert page.next_seq == 5
    assert page.has_more is False


def test_the_default_cursor_is_the_start_of_the_log() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, 4)])
    assert seqs(fetch_changes(ledger)) == [1, 2, 3]  # type: ignore[arg-type]


def test_limit_pages_the_result_and_the_cursor_resumes_without_gap_or_repeat() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, 6)])
    first = fetch_changes(ledger, limit=2)  # type: ignore[arg-type]
    assert (seqs(first), first.next_seq, first.has_more) == ([1, 2], 2, True)
    second = fetch_changes(ledger, after_seq=first.next_seq, limit=2)  # type: ignore[arg-type]
    assert (seqs(second), second.next_seq, second.has_more) == ([3, 4], 4, True)
    third = fetch_changes(ledger, after_seq=second.next_seq, limit=2)  # type: ignore[arg-type]
    assert (seqs(third), third.next_seq, third.has_more) == ([5], 5, False)


def test_a_page_that_ends_exactly_at_the_log_end_has_no_more() -> None:
    ledger = FakeLedger([make_event(1), make_event(2)])
    page = fetch_changes(ledger, limit=2)  # type: ignore[arg-type]
    assert (seqs(page), page.next_seq, page.has_more) == ([1, 2], 2, False)


def test_non_matching_events_are_skipped_but_the_cursor_moves_past_them() -> None:
    types = ["Record.Created", "Link.Added", "Record.Updated", "Link.Retracted", "Record.Voided"]
    ledger = FakeLedger([make_event(n + 1, t) for n, t in enumerate(types)])
    flt = SubscriptionFilter.of(event_types=["Link.*"])
    page = fetch_changes(ledger, flt=flt)  # type: ignore[arg-type]
    assert seqs(page) == [2, 4]
    assert page.next_seq == 5  # past the trailing non-matching event
    assert page.has_more is False


def test_with_a_limit_the_cursor_stops_at_the_last_returned_event() -> None:
    types = ["Link.Added", "Record.Updated", "Link.Retracted", "Record.Voided", "Link.Added"]
    ledger = FakeLedger([make_event(n + 1, t) for n, t in enumerate(types)])
    flt = SubscriptionFilter.of(event_types=["Link.*"])
    page = fetch_changes(ledger, flt=flt, limit=2)  # type: ignore[arg-type]
    assert (seqs(page), page.next_seq, page.has_more) == ([1, 3], 3, True)
    rest = fetch_changes(ledger, after_seq=page.next_seq, flt=flt, limit=2)  # type: ignore[arg-type]
    assert (seqs(rest), rest.next_seq, rest.has_more) == ([5], 5, False)


def test_the_scope_is_passed_down_to_the_ledger_read() -> None:
    ledger = FakeLedger(
        [make_event(1, scope="project:P1"), make_event(2, scope="company"), make_event(3)]
    )
    page = fetch_changes(ledger, flt=SubscriptionFilter(scope="company"))  # type: ignore[arg-type]
    assert seqs(page) == [2]
    assert page.next_seq == 2  # the ledger never showed the other scopes
    assert {scope for _seq, scope, _limit in ledger.calls} == {"company"}


def test_record_ids_filter_selects_the_stream() -> None:
    ledger = FakeLedger([make_event(1, stream_id="A"), make_event(2, stream_id="B")])
    flt = SubscriptionFilter.of(record_ids=["B"])
    assert seqs(fetch_changes(ledger, flt=flt)) == [2]  # type: ignore[arg-type]


def test_reads_the_ledger_in_pages_of_the_documented_size() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, 2 * PAGE + 11)])
    page = fetch_changes(ledger, limit=5000)  # type: ignore[arg-type]
    assert len(page.events) == 2 * PAGE + 10
    assert [limit for _seq, _scope, limit in ledger.calls] == [PAGE, PAGE, PAGE]
    assert [seq for seq, _scope, _limit in ledger.calls] == [0, PAGE, 2 * PAGE]


def test_a_log_that_is_an_exact_multiple_of_the_page_size_ends_cleanly() -> None:
    ledger = FakeLedger([make_event(n) for n in range(1, PAGE + 1)])
    page = fetch_changes(ledger, limit=5000)  # type: ignore[arg-type]
    assert (len(page.events), page.next_seq, page.has_more) == (PAGE, PAGE, False)


def test_a_very_selective_filter_stops_at_the_scan_cap_and_can_be_resumed() -> None:
    total = MAX_SCAN_PAGES * PAGE + 30
    events = [make_event(n, "Record.Updated") for n in range(1, total + 1)]
    events.append(make_event(total + 1, "Link.Added"))
    ledger = FakeLedger(events)
    flt = SubscriptionFilter.of(event_types=["Link.Added"])
    first = fetch_changes(ledger, flt=flt)  # type: ignore[arg-type]
    assert first.events == []
    assert first.next_seq == MAX_SCAN_PAGES * PAGE
    assert first.has_more is True
    assert len(ledger.calls) == MAX_SCAN_PAGES
    second = fetch_changes(ledger, after_seq=first.next_seq, flt=flt)  # type: ignore[arg-type]
    assert seqs(second) == [total + 1]
    assert (second.next_seq, second.has_more) == (total + 1, False)


def test_following_the_cursor_visits_every_matching_event_exactly_once() -> None:
    types = ["Record.Created", "Link.Added", "Record.Updated"]
    ledger = FakeLedger([make_event(n, types[n % 3]) for n in range(1, 40)])
    flt = SubscriptionFilter.of(event_types=["Record.*"])
    seen: list[int] = []
    cursor = 0
    for _ in range(100):
        page = fetch_changes(ledger, after_seq=cursor, flt=flt, limit=4)  # type: ignore[arg-type]
        seen.extend(seqs(page))
        assert page.next_seq >= cursor
        cursor = page.next_seq
        if not page.has_more:
            break
    assert seen == [n for n in range(1, 40) if types[n % 3].startswith("Record.")]


@pytest.mark.parametrize("limit", [0, -1])
def test_a_limit_below_one_is_refused(limit: int) -> None:
    with pytest.raises(ValueError):
        fetch_changes(FakeLedger([]), limit=limit)  # type: ignore[arg-type]


def test_a_negative_cursor_is_refused() -> None:
    with pytest.raises(ValueError):
        fetch_changes(FakeLedger([]), after_seq=-1)  # type: ignore[arg-type]
