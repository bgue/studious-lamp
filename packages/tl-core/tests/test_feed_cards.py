"""The event-card aggregation rules (P0-I6-S3; brief 21.1, FANOUT D1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from tl_core.feed.cards import (
    OpenCard,
    card_id_for,
    disposition,
    fold_cards,
    render_card_summary,
    subjects_of,
    to_us,
)
from tl_core.feed.types import CARD_WINDOW_SECONDS
from tl_core.ledger import Event

T0 = datetime(2026, 10, 9, 9, 0, 0, tzinfo=UTC)


def ev(
    seq: int,
    event_type: str = "Record.Created",
    *,
    actor: str = "user:jo",
    at: float = 0,
    stream_id: str = "01REC",
    payload: dict[str, Any] | None = None,
) -> Event:
    moment = T0 + timedelta(seconds=at)
    return Event(
        event_type=event_type,
        payload=payload or {},
        seq=seq,
        event_id=f"E{seq}",
        stream_id=stream_id,
        stream_type="core.Record",
        stream_version=1,
        scope="project:P1",
        actor=actor,
        recorded_at=moment,
        effective_at=moment,
        correlation_id="c",
        causation_id=None,
        source="test",
        prev_hash=None,
        hash="h",
    )


def open_card(*, actor: str = "user:jo", event_type: str = "Record.Created") -> OpenCard:
    return OpenCard("card:E1", actor, event_type, to_us(T0), 1)


def test_no_open_card_starts_one() -> None:
    assert disposition(None, ev(1)) == "start"


def test_same_actor_and_type_inside_the_window_extends() -> None:
    assert disposition(open_card(), ev(2, at=5)) == "extend"


def test_the_window_end_is_inclusive_and_counted_from_the_first_event() -> None:
    assert disposition(open_card(), ev(2, at=CARD_WINDOW_SECONDS)) == "extend"
    assert disposition(open_card(), ev(2, at=CARD_WINDOW_SECONDS + 0.000001)) == "start"


def test_an_event_recorded_before_the_card_began_starts_a_new_card() -> None:
    assert disposition(open_card(), ev(2, at=-1)) == "start"


def test_another_actor_or_type_starts_a_new_card() -> None:
    assert disposition(open_card(), ev(2, actor="user:al", at=1)) == "start"
    assert disposition(open_card(), ev(2, "Record.Updated", at=1)) == "start"


@pytest.mark.parametrize(
    "event_type",
    [
        "Numbering.Allocated",
        "Link.Suggested",
        "Webhook.Delivered",
        "Proposal.Created",
        "Proposal.Accepted",
        "Proposal.Rejected",
        "Proposal.Failed",
    ],
)
def test_plumbing_events_are_ignored(event_type: str) -> None:
    assert disposition(open_card(), ev(2, event_type, at=1)) == "ignore"
    assert disposition(None, ev(2, event_type)) == "ignore"


@pytest.mark.parametrize(
    "event_type", ["Feed.Posted", "Feed.Edited", "Feed.Retracted", "Feed.Reacted"]
)
def test_feed_events_close_the_open_card_and_never_make_one(event_type: str) -> None:
    assert disposition(open_card(), ev(2, event_type, at=1)) == "close"
    assert disposition(None, ev(2, event_type)) == "close"


def test_microseconds_are_exact() -> None:
    assert to_us(datetime(1970, 1, 1, 0, 0, 1, 5, tzinfo=UTC)) == 1_000_005
    assert to_us(datetime(1970, 1, 1, 0, 0, 1, 5)) == 1_000_005  # naive is UTC


def test_card_id_comes_from_the_first_event() -> None:
    assert card_id_for("01ABC") == "card:01ABC"


def test_subjects() -> None:
    assert subjects_of(ev(1, stream_id="R1")) == ["R1"]
    assert subjects_of(ev(1, "Pset.ValuesSet", stream_id="R2")) == ["R2"]
    assert subjects_of(ev(1, "Workflow.Transitioned", stream_id="R3")) == ["R3"]
    link = ev(1, "Link.Added", stream_id="L1", payload={"from_ref": "R1", "to_ref": "R2"})
    assert subjects_of(link) == ["R1", "R2"]
    loop = ev(1, "Link.Added", stream_id="L1", payload={"from_ref": "R1", "to_ref": "R1"})
    assert subjects_of(loop) == ["R1"]
    assert subjects_of(ev(1, "File.Uploaded", stream_id="F1", payload={"record_id": "R9"})) == [
        "R9"
    ]
    assert subjects_of(ev(1, "File.Uploaded", stream_id="F1")) == []
    assert subjects_of(ev(1, "Setting.Changed", stream_id="S")) == []


@pytest.mark.parametrize(
    ("actor", "event_type", "count", "expected"),
    [
        ("user:jsmith", "Record.Created", 14, "jsmith created 14 records"),
        ("user:jsmith", "Record.Created", 1, "jsmith created a record"),
        ("agent:triage", "Record.Updated", 2, "agent:triage updated 2 records"),
        ("user:jo", "Pset.ValuesSet", 3, "jo set properties on 3 records"),
        ("user:jo", "Link.Added", 1, "jo added a link"),
        ("user:jo", "File.Uploaded", 1, "jo uploaded a file"),
        ("svc:schema", "SchemaPackage.Published", 2, "svc:schema published 2 schemapackage"),
    ],
)
def test_summaries(actor: str, event_type: str, count: int, expected: str) -> None:
    assert render_card_summary(actor, event_type, count) == expected


def test_a_burst_with_numbering_events_between_is_one_card() -> None:
    events = [
        ev(1, "Numbering.Allocated", at=0),
        ev(2, "Record.Created", at=0),
        ev(3, "Numbering.Allocated", at=1),
        ev(4, "Record.Created", at=1),
        ev(5, "Numbering.Allocated", at=2),
        ev(6, "Record.Created", at=2),
    ]
    assert fold_cards(events) == [("card:E2", "user:jo", "Record.Created", 3, 6)]


def test_a_post_splits_a_burst_and_other_actors_split_it_too() -> None:
    events = [
        ev(1, at=0),
        ev(2, at=1),
        ev(3, "Feed.Posted", at=2),
        ev(4, at=3),
        ev(5, actor="user:al", at=4),
        ev(6, actor="user:jo", at=5),
    ]
    assert fold_cards(events) == [
        ("card:E1", "user:jo", "Record.Created", 2, 2),
        ("card:E4", "user:jo", "Record.Created", 1, 4),
        ("card:E5", "user:al", "Record.Created", 1, 5),
        ("card:E6", "user:jo", "Record.Created", 1, 6),
    ]


def test_the_window_runs_from_the_first_event_not_the_latest() -> None:
    events = [ev(1, at=0), ev(2, at=400), ev(3, at=800)]
    assert fold_cards(events) == [
        ("card:E1", "user:jo", "Record.Created", 2, 2),
        ("card:E3", "user:jo", "Record.Created", 1, 3),
    ]
