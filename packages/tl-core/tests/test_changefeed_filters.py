"""SubscriptionFilter: scope, event-type globs and record ids."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from tl_core.changefeed import ANY, SubscriptionFilter
from tl_core.ledger import Event

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_event(
    event_type: str = "Record.Created",
    *,
    scope: str = "project:P1",
    stream_id: str = "R1",
    payload: dict[str, Any] | None = None,
) -> Event:
    return Event(
        event_type=event_type,
        payload=payload or {},
        seq=1,
        event_id="E" * 26,
        stream_id=stream_id,
        stream_type="core.Record",
        stream_version=1,
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


def test_the_empty_filter_matches_everything() -> None:
    assert SubscriptionFilter().matches(make_event())
    assert ANY.matches(make_event("Whatever.Happened", scope="company"))


def test_scope_must_match_exactly() -> None:
    flt = SubscriptionFilter(scope="project:P1")
    assert flt.matches(make_event(scope="project:P1"))
    assert not flt.matches(make_event(scope="project:P12"))
    assert not flt.matches(make_event(scope="company"))


@pytest.mark.parametrize(
    ("pattern", "event_type", "expected"),
    [
        ("Record.Created", "Record.Created", True),
        ("Record.Created", "Record.Updated", False),
        ("Record.Created", "record.created", False),
        ("Record.*", "Record.Updated", True),
        ("Record.*", "Pset.ValuesSet", False),
        ("*.Created", "Record.Created", True),
        ("*.Created", "Link.Added", False),
        ("Link.*", "Link.Added", True),
        ("*", "Anything.At.All", True),
        ("Link.?dded", "Link.Added", True),
        ("Link.[AR]*", "Link.Retracted", True),
        ("Link.[AR]*", "Link.Flagged", False),
        ("Record", "Record.Created", False),
        ("Record.Cre", "Record.Created", False),
        ("piping.Weld.*", "piping.Weld.Created", True),
    ],
)
def test_event_types_are_exact_names_or_globs(
    pattern: str, event_type: str, expected: bool
) -> None:
    assert SubscriptionFilter(event_types=(pattern,)).matches(make_event(event_type)) is expected


def test_several_event_types_are_ored() -> None:
    flt = SubscriptionFilter.of(event_types=["Record.Created", "Link.*"])
    assert flt.matches(make_event("Record.Created"))
    assert flt.matches(make_event("Link.Retracted"))
    assert not flt.matches(make_event("Record.Updated"))


def test_record_ids_match_the_stream() -> None:
    flt = SubscriptionFilter.of(record_ids=["R1", "R2"])
    assert flt.matches(make_event(stream_id="R2"))
    assert not flt.matches(make_event(stream_id="R3"))


def test_link_events_also_match_through_either_end() -> None:
    flt = SubscriptionFilter.of(record_ids=["R9"])
    ends = {"from_ref": "R1", "to_ref": "R9"}
    assert flt.matches(make_event("Link.Added", stream_id="L1", payload=ends))
    assert flt.matches(make_event("Link.Added", stream_id="L1", payload={"from_ref": "R9"}))
    assert not flt.matches(make_event("Link.Added", stream_id="L1", payload={"to_ref": "R8"}))
    assert not flt.matches(make_event("Link.Added", stream_id="L1"))


@pytest.mark.parametrize("junk", [None, 5, ["R9"], {"id": "R9"}, ("R9",)])
def test_a_link_end_that_is_not_a_string_never_matches_and_never_raises(junk: object) -> None:
    flt = SubscriptionFilter.of(record_ids=["R9"])
    assert not flt.matches(make_event("Link.Added", stream_id="L1", payload={"from_ref": junk}))


def test_all_parts_must_match() -> None:
    flt = SubscriptionFilter(
        scope="project:P1", event_types=("Record.*",), record_ids=frozenset({"R1"})
    )
    assert flt.matches(make_event("Record.Updated", scope="project:P1", stream_id="R1"))
    assert not flt.matches(make_event("Record.Updated", scope="company", stream_id="R1"))
    assert not flt.matches(make_event("Link.Added", scope="project:P1", stream_id="R1"))
    assert not flt.matches(make_event("Record.Updated", scope="project:P1", stream_id="R2"))


def test_empty_collections_are_refused() -> None:
    with pytest.raises(ValueError):
        SubscriptionFilter(event_types=())
    with pytest.raises(ValueError):
        SubscriptionFilter(record_ids=frozenset())
    with pytest.raises(ValueError):
        SubscriptionFilter.of(event_types=[])
    with pytest.raises(ValueError):
        SubscriptionFilter.of(record_ids=set())


def test_filters_are_hashable_values() -> None:
    a = SubscriptionFilter.of(scope="company", event_types=["A.*"], record_ids=["x"])
    b = SubscriptionFilter(scope="company", event_types=("A.*",), record_ids=frozenset({"x"}))
    assert a == b
    assert len({a, b}) == 1
