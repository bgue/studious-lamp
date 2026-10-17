"""ThreadProjector and ClockProjector: thread and clock events into their tables (P1-I5-T03b)."""

from __future__ import annotations

from typing import Any

from corrworld import Events, apply, as_json, install, table_rows
from sqlalchemy import Engine

THREAD = "THR1"
CLOCK = "CLK1"
ITEM = "ITEM1"
THREAD_TYPE = "correspondence.CorrespondenceThread"
CLOCK_TYPE = "correspondence.ResponseClock"
THREAD_TABLE = "cur_correspondence_correspondence_thread"
CLOCK_TABLE = "cur_correspondence_response_clock"


def started(events: Events, stream: str = CLOCK, **more: Any) -> list[Any]:
    payload: dict[str, Any] = {
        "item_id": ITEM,
        "item_number": "P123-COR-0002",
        "label": "Reply expected",
        "kind": "response_from_them",
        "start_on": "2026-10-17",
        "duration_days": 14,
        "day_type": "calendar",
        "calendar": "P123-default@1",
        "warn_days": [7, 3, 1],
        "due_on": "2026-10-31",
        "owner": "user:amy",
        "trigger": "issue",
        **more,
    }
    return [
        events.created(stream, CLOCK_TYPE, f"P123-COR-0002/{stream}", title="Reply expected"),
        events.make("ResponseClock.Started", payload, stream_id=stream, stream_type=CLOCK_TYPE),
    ]


def clock_event(events: Events, event_type: str, payload: dict[str, Any]) -> Any:
    return events.make(event_type, payload, stream_id=CLOCK, stream_type=CLOCK_TYPE)


def thread_events(events: Events) -> list[Any]:
    return [
        events.created(THREAD, THREAD_TYPE, "P123-THR-0001", title="revised programme"),
        events.make(
            "CorrespondenceThread.Defined",
            {
                "number": "P123-THR-0001",
                "subject_key": "revised programme",
                "domain": "general",
                "governing_item_id": ITEM,
                "item_on": "2026-10-17",
            },
            stream_id=THREAD,
            stream_type=THREAD_TYPE,
        ),
        events.make(
            "CorrespondenceThread.ItemAdded",
            {"item_id": "ITEM2", "item_on": "2026-10-20"},
            stream_id=THREAD,
            stream_type=THREAD_TYPE,
        ),
        events.make(
            "CorrespondenceThread.ItemAdded",
            {"item_id": "ITEM3", "item_on": "2026-10-18"},  # earlier than the last: date stays
            stream_id=THREAD,
            stream_type=THREAD_TYPE,
        ),
        events.make(
            "CorrespondenceThread.StateChanged",
            {"state": "closed", "reason": "Every question answered"},
            stream_id=THREAD,
            stream_type=THREAD_TYPE,
        ),
    ]


def test_a_thread_counts_its_items_and_keeps_the_newest_date(engine: Engine) -> None:
    apply(engine, *thread_events(Events()))
    (row,) = table_rows(engine, THREAD_TABLE)
    assert row["id"] == THREAD and row["scope"] == "project:P123"
    assert row["number"] == "P123-THR-0001" and row["subject_key"] == "revised programme"
    assert row["domain"] == "general" and row["governing_item_id"] == ITEM
    assert row["item_count"] == 3
    assert row["last_item_on"] == "2026-10-20"
    assert row["state"] == "closed"


def test_a_new_thread_is_open_with_one_item(engine: Engine) -> None:
    apply(engine, *thread_events(Events())[:2])
    (row,) = table_rows(engine, THREAD_TABLE)
    assert row["state"] == "open" and row["item_count"] == 1
    assert row["last_item_on"] == "2026-10-17"


def test_a_thread_without_a_domain_keeps_it_null(engine: Engine) -> None:
    events = Events()
    first, second = thread_events(events)[:2]
    second.payload["domain"] = None
    apply(engine, first, second)
    (row,) = table_rows(engine, THREAD_TABLE)
    assert row["domain"] is None


def test_a_started_clock_has_the_fields_of_its_event(engine: Engine) -> None:
    apply(engine, *started(Events(), clause_id="CL1"))
    (row,) = table_rows(engine, CLOCK_TABLE)
    assert row["id"] == CLOCK and row["scope"] == "project:P123"
    assert row["item_id"] == ITEM and row["item_number"] == "P123-COR-0002"
    assert row["label"] == "Reply expected" and row["kind"] == "response_from_them"
    assert row["start_on"] == "2026-10-17" and row["due_on"] == "2026-10-31"
    assert row["duration_days"] == 14 and row["day_type"] == "calendar"
    assert row["calendar"] == "P123-default@1"
    assert as_json(row["warn_days_json"]) == [7, 3, 1]
    assert row["state"] == "running" and row["owner"] == "user:amy"
    assert row["clause_id"] == "CL1" and row["restarts"] == 0
    assert row["paused_on"] is None and row["closed_on"] is None and row["warned_level"] is None


def test_pause_and_resume_move_the_state_and_the_due_date(engine: Engine) -> None:
    events = Events()
    apply(engine, *started(events))
    apply(
        engine, clock_event(events, "ResponseClock.Paused", {"on": "2026-10-20", "reason": "Wait"})
    )
    (paused,) = table_rows(engine, CLOCK_TABLE)
    assert paused["state"] == "paused" and paused["paused_on"] == "2026-10-20"
    assert paused["pause_reason"] == "Wait" and paused["due_on"] == "2026-10-31"
    apply(
        engine,
        clock_event(events, "ResponseClock.Resumed", {"on": "2026-10-23", "due_on": "2026-11-03"}),
    )
    (resumed,) = table_rows(engine, CLOCK_TABLE)
    assert resumed["state"] == "running" and resumed["due_on"] == "2026-11-03"
    assert resumed["paused_on"] is None and resumed["pause_reason"] is None


def test_a_restart_begins_again_and_forgets_the_warnings(engine: Engine) -> None:
    events = Events()
    apply(engine, *started(events))
    apply(
        engine,
        clock_event(
            events, "ResponseClock.Warned", {"on": "2026-10-24", "level": 7, "days_left": 7}
        ),
    )
    (warned,) = table_rows(engine, CLOCK_TABLE)
    assert warned["warned_level"] == 7 and warned["state"] == "running"
    apply(
        engine,
        clock_event(
            events,
            "ResponseClock.Restarted",
            {"start_on": "2026-10-27", "due_on": "2026-11-10", "reason": "Revised letter"},
        ),
    )
    (row,) = table_rows(engine, CLOCK_TABLE)
    assert row["start_on"] == "2026-10-27" and row["due_on"] == "2026-11-10"
    assert row["warned_level"] is None and row["restarts"] == 1 and row["state"] == "running"


def test_a_restart_reopens_a_clock_that_had_expired(engine: Engine) -> None:
    events = Events()
    apply(engine, *started(events))
    apply(
        engine,
        clock_event(events, "ResponseClock.Expired", {"on": "2026-11-01", "days_overdue": 1}),
    )
    (expired,) = table_rows(engine, CLOCK_TABLE)
    assert expired["state"] == "expired"
    apply(
        engine,
        clock_event(
            events,
            "ResponseClock.Restarted",
            {"start_on": "2026-11-02", "due_on": "2026-11-16", "reason": "Again"},
        ),
    )
    (row,) = table_rows(engine, CLOCK_TABLE)
    assert row["state"] == "running" and row["closed_on"] is None


def test_met_and_cancelled_close_the_clock_with_a_date_and_a_reason(engine: Engine) -> None:
    events = Events()
    apply(engine, *started(events))
    apply(
        engine, clock_event(events, "ResponseClock.Paused", {"on": "2026-10-20", "reason": "Wait"})
    )
    apply(
        engine,
        clock_event(events, "ResponseClock.Met", {"on": "2026-10-25", "response_id": "ITEM9"}),
    )
    (met,) = table_rows(engine, CLOCK_TABLE)
    assert met["state"] == "met" and met["closed_on"] == "2026-10-25"
    assert met["closed_reason"] == "ITEM9"
    assert met["paused_on"] is None and met["pause_reason"] is None

    other = Events()
    apply(engine, *started(other, stream="CLK2"))
    apply(
        engine,
        other.make(
            "ResponseClock.Cancelled",
            {"on": "2026-10-26", "reason": "Withdrawn"},
            stream_id="CLK2",
            stream_type=CLOCK_TYPE,
        ),
    )
    rows = {r["id"]: r for r in table_rows(engine, CLOCK_TABLE)}
    assert rows["CLK2"]["state"] == "cancelled" and rows["CLK2"]["closed_reason"] == "Withdrawn"


def test_a_reason_given_with_met_wins_over_the_answering_item(engine: Engine) -> None:
    events = Events()
    apply(engine, *started(events))
    apply(
        engine,
        clock_event(
            events,
            "ResponseClock.Met",
            {"on": "2026-10-25", "response_id": "ITEM9", "reason": "Answered by phone"},
        ),
    )
    (row,) = table_rows(engine, CLOCK_TABLE)
    assert row["closed_reason"] == "Answered by phone"


def test_expired_marks_a_running_clock_and_keeps_its_dates(engine: Engine) -> None:
    events = Events()
    apply(engine, *started(events))
    apply(
        engine,
        clock_event(events, "ResponseClock.Expired", {"on": "2026-11-01", "days_overdue": 1}),
    )
    (row,) = table_rows(engine, CLOCK_TABLE)
    assert row["state"] == "expired" and row["due_on"] == "2026-10-31" and row["closed_on"] is None


def test_the_same_events_give_the_same_rows_on_a_second_database(
    engine: Engine, new_engine: Any, dialect: str
) -> None:
    events = Events()
    journal = [
        *thread_events(events),
        *started(events),
        clock_event(
            events, "ResponseClock.Warned", {"on": "2026-10-24", "level": 7, "days_left": 7}
        ),
        clock_event(events, "ResponseClock.Paused", {"on": "2026-10-25", "reason": "Wait"}),
        clock_event(events, "ResponseClock.Resumed", {"on": "2026-10-28", "due_on": "2026-11-03"}),
        clock_event(events, "ResponseClock.Met", {"on": "2026-11-01"}),
    ]
    apply(engine, *journal)
    other = new_engine()
    install(other, dialect)
    apply(other, *journal)
    for table in (THREAD_TABLE, CLOCK_TABLE):
        assert table_rows(other, table) == table_rows(engine, table)
    other.dispose()
