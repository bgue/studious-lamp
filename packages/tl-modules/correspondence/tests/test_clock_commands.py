"""Clock commands on a ledger: start, pause, resume, restart, meet, cancel, sweep (P1-I5-T04).

The projection row and the engine must agree: after each act the row equals what ``replay`` gives
from the clock's events (recompute from the ledger).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.services.errors import RecordNotFoundError
from tl_mod_correspondence import catalog, registry
from tl_mod_correspondence.clocks import replay
from tl_mod_correspondence.errors import (
    CalendarUnavailableError,
    ClockStateError,
    InvalidClockError,
    ItemBackdatedError,
)
from tl_mod_correspondence.handlers.clocks import (
    SweepClocks,
    close_clocks_of_item,
    handle_sweep_clocks,
)
from tl_mod_correspondence.handlers.common import correlated
from tl_mod_correspondence.testing import BASE, CorrWorld, frozen_today

MONDAY = "2026-10-19"


def assert_row_is_replay(world: CorrWorld, clock_id: str) -> Any:
    """The stored row equals what the engine recomputes from the clock's events."""
    row = world.clock(clock_id)
    with open_uow(world.db, readonly=True) as uow:
        facts = registry.clock_facts(uow.conn(), clock_id)
    fig = replay(facts, catalog.calendar_for(row.calendar))
    assert (row.state, row.due_on, row.start_on, row.restarts) == (
        fig.state,
        fig.due_on.isoformat(),
        fig.start_on.isoformat(),
        fig.restarts,
    )
    assert row.warned_level == fig.warned_level
    return fig


@pytest.fixture
def item(world: CorrWorld) -> str:
    return world.forge_item()


def test_a_clock_starts_with_the_engines_due_date_on_the_project_calendar(
    world: CorrWorld, item: str
) -> None:
    with frozen_today(MONDAY):
        made = world.start_clock(item)
    assert made.key == "P123-COR-0001-C01"
    started = world.events_of(made.stream_id)[-1]
    assert started[0] == "ResponseClock.Started"
    assert started[1] | {} == {
        "item_id": item,
        "item_number": "P123-COR-0001",
        "label": "Reply due",
        "kind": "response_from_them",
        "start_on": MONDAY,
        "duration_days": 14,
        "day_type": "calendar",
        "calendar": "P123-default@1",
        "warn_days": [7, 3, 1],
        "due_on": "2026-11-02",
        "owner": None,
        "clause_id": None,
        "trigger": "manual",
    }
    row = world.clock(made.stream_id)
    assert (row.state, row.due_on, row.item_number) == ("running", "2026-11-02", "P123-COR-0001")
    assert_row_is_replay(world, made.stream_id)


def test_a_working_day_clock_skips_weekends_and_the_project_holidays(
    world: CorrWorld, item: str
) -> None:
    with frozen_today("2026-04-02"):  # Thursday; Good Friday and Easter Monday follow
        made = world.start_clock(item, duration_days=5, day_type="working", warn_days=[])
    assert world.clock(made.stream_id).due_on == "2026-04-13"


def test_clocks_of_one_item_are_numbered_in_order(world: CorrWorld, item: str) -> None:
    with frozen_today(MONDAY):
        first = world.start_clock(item)
        second = world.start_clock(item, label="Second")
    assert (first.key, second.key) == ("P123-COR-0001-C01", "P123-COR-0001-C02")
    assert [c.label for c in world.clocks("P123-COR-0001")] == ["Reply due", "Second"]


def test_a_start_the_calendar_cannot_count_is_refused(world: CorrWorld, item: str) -> None:
    with frozen_today("2028-12-20"), pytest.raises(CalendarUnavailableError):
        world.start_clock(item, duration_days=30, day_type="working")  # runs past 2028-12-31


def test_a_clock_with_bad_parameters_is_refused_before_anything_is_written(
    world: CorrWorld, item: str
) -> None:
    with frozen_today(MONDAY):
        for more in (
            {"warn_days": [15]},
            {"warn_days": [3, 3]},
            {"warn_days": [0]},
        ):
            with pytest.raises(InvalidClockError):
                world.start_clock(item, **more)
        for more in (
            {"duration_days": 0},
            {"duration_days": 3651},
            {"day_type": "weekly"},
            {"kind": "other"},
            {"label": "  "},
            {"unknown_field": 1},
        ):
            with pytest.raises(ValidationError):
                world.start_clock(item, **more)
    assert world.clocks("P123-COR-0001") == []


def test_a_start_dated_before_today_needs_a_reason_and_never_after_today(
    world: CorrWorld, item: str
) -> None:
    with frozen_today(MONDAY):
        with pytest.raises(ItemBackdatedError):
            world.start_clock(item, start_on="2026-10-12")
        with pytest.raises(ItemBackdatedError):
            world.start_clock(item, start_on="2026-10-20")
        with pytest.raises(InvalidClockError):
            world.start_clock(item, start_on="12/10/2026")
        made = world.start_clock(item, start_on="2026-10-12", start_reason="logged a week late")
    assert world.clock(made.stream_id).due_on == "2026-10-26"


def test_a_clock_needs_an_active_clause_in_its_scope(world: CorrWorld, item: str) -> None:
    with frozen_today(MONDAY), pytest.raises(InvalidClockError):
        world.start_clock(item, clause_id="no-such-clause")


def test_a_clock_on_an_unknown_item_or_another_scope_is_not_found(
    world: CorrWorld, item: str
) -> None:
    with frozen_today(MONDAY):
        with pytest.raises(RecordNotFoundError):
            world.start_clock("01J000000000000000000000")
        with pytest.raises(RecordNotFoundError):
            world.start_clock(item, scope="project:OTHER")


def test_a_hidden_item_answers_as_if_it_did_not_exist(world: CorrWorld) -> None:
    secret = world.forge_item("P123-COR-0002", confidentiality="restricted")
    plain = cf.Viewer(actor="user:ann", level=0, account="user:ann")
    controller = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")
    with frozen_today(MONDAY):
        with cf.use_viewer(plain), pytest.raises(RecordNotFoundError) as caught:
            world.start_clock(secret)
        with cf.use_viewer(plain), pytest.raises(RecordNotFoundError) as unknown:
            world.start_clock("01J000000000000000000000")
        assert str(caught.value).replace(secret, "X") == str(unknown.value).replace(
            "01J000000000000000000000", "X"
        )
        with cf.use_viewer(controller):
            made = world.start_clock(secret)
        with cf.use_viewer(plain):
            for act in (world.pause, world.resume, world.meet, world.cancel, world.restart):
                with pytest.raises(RecordNotFoundError):
                    act(made.stream_id)


def test_pause_stops_the_count_and_resume_moves_the_due_date(world: CorrWorld, item: str) -> None:
    with frozen_today(MONDAY):
        made = world.start_clock(item)  # due Mon 2 Nov
    cid = made.stream_id
    with frozen_today("2026-10-20"):
        world.pause(cid, reason="Waiting for a drawing")
    row = world.clock(cid)
    assert (row.state, row.paused_on, row.pause_reason) == (
        "paused",
        "2026-10-20",
        "Waiting for a drawing",
    )
    assert_row_is_replay(world, cid)
    with frozen_today("2026-10-23"):
        world.resume(cid)
    row = world.clock(cid)
    assert (row.state, row.due_on, row.paused_on) == ("running", "2026-11-05", None)
    assert_row_is_replay(world, cid)
    kinds = [e[0] for e in world.events_of(cid)]
    assert kinds[-2:] == ["ResponseClock.Paused", "ResponseClock.Resumed"]


def test_only_a_running_clock_pauses_and_only_a_paused_one_resumes(
    world: CorrWorld, item: str
) -> None:
    with frozen_today(MONDAY):
        cid = world.start_clock(item).stream_id
        with pytest.raises(ClockStateError):
            world.resume(cid)
        world.pause(cid)
        with pytest.raises(ClockStateError):
            world.pause(cid)
        world.resume(cid)
        world.cancel(cid)
        with pytest.raises(ClockStateError):
            world.pause(cid)
        with pytest.raises(ClockStateError):
            world.meet(cid)
        with pytest.raises(ClockStateError):
            world.cancel(cid)


def test_a_date_before_the_last_event_is_refused_by_the_engine(world: CorrWorld, item: str) -> None:
    with frozen_today("2026-10-26"):
        cid = world.start_clock(item, start_on="2026-10-26").stream_id
    with frozen_today("2026-10-27"):
        with pytest.raises(ClockStateError):
            world.pause(cid, on="2026-10-20", reason="waiting")  # before the start
        with pytest.raises(ItemBackdatedError):
            world.pause(cid, on="2026-10-28")  # after today


def test_a_resume_dated_before_today_needs_a_reason(world: CorrWorld, item: str) -> None:
    with frozen_today(MONDAY):
        cid = world.start_clock(item).stream_id
        world.pause(cid)
    with frozen_today("2026-10-22"):
        with pytest.raises(ItemBackdatedError):
            world.resume(cid, on="2026-10-21")
        world.resume(cid, on="2026-10-21", reason="we agreed it on the phone")
    assert_row_is_replay(world, cid)


def test_a_working_clock_pause_over_a_weekend_counts_only_working_days(
    world: CorrWorld, item: str
) -> None:
    with frozen_today(MONDAY):
        cid = world.start_clock(item, duration_days=5, day_type="working", warn_days=[]).stream_id
    with frozen_today("2026-10-21"):
        world.pause(cid)
    with frozen_today("2026-10-26"):
        world.resume(cid)
    assert world.clock(cid).due_on == "2026-10-29"
    assert_row_is_replay(world, cid)


def test_restart_counts_again_and_forgets_warnings(world: CorrWorld, item: str) -> None:
    with frozen_today(MONDAY):
        cid = world.start_clock(item).stream_id
    with frozen_today("2026-10-30"):
        world.sweep()
    assert world.clock(cid).warned_level == 3
    with frozen_today("2026-11-04"):
        world.restart(cid, reason="Revised letter")
    row = world.clock(cid)
    assert (row.start_on, row.due_on, row.restarts, row.warned_level) == (
        "2026-11-04",
        "2026-11-18",
        1,
        None,
    )
    assert_row_is_replay(world, cid)


def test_restart_reopens_a_closed_clock(world: CorrWorld, item: str) -> None:
    with frozen_today(MONDAY):
        cid = world.start_clock(item).stream_id
        world.cancel(cid)
        world.restart(cid)
    assert world.clock(cid).state == "running"
    assert_row_is_replay(world, cid)


def test_meeting_a_clock_after_its_due_date_is_allowed_and_dated(
    world: CorrWorld, item: str
) -> None:
    with frozen_today(MONDAY):
        cid = world.start_clock(item).stream_id
    with frozen_today("2026-11-05"):
        world.sweep()
        assert world.clock(cid).state == "expired"
        world.meet(cid, reason="late reply received")
    row = world.clock(cid)
    assert (row.state, row.closed_on, row.closed_reason) == (
        "met",
        "2026-11-05",
        "late reply received",
    )
    assert_row_is_replay(world, cid)


def test_a_clock_is_met_by_an_item_of_the_same_scope(world: CorrWorld, item: str) -> None:
    answer = world.forge_item("P123-COR-0002", direction="out", state="Draft")
    with frozen_today(MONDAY):
        cid = world.start_clock(item).stream_id
        with pytest.raises(RecordNotFoundError):
            world.meet(cid, response_id="01J000000000000000000000")
        world.meet(cid, response_id=answer)
    assert world.events_of(cid)[-1][1]["response_id"] == answer


def test_the_sweep_warns_once_per_threshold_and_expires_past_due(
    world: CorrWorld, item: str
) -> None:
    with frozen_today(MONDAY):
        cid = world.start_clock(item).stream_id  # due Mon 2 Nov; warns at 7, 3, 1
        assert world.sweep().events == []
    seen: list[tuple[str, int | None]] = []
    for day in ("2026-10-26", "2026-10-26", "2026-10-30", "2026-11-01", "2026-11-03"):
        with frozen_today(day):
            for event in world.sweep().events:
                seen.append((event.event_type, event.payload.get("level")))
    assert seen == [
        ("ResponseClock.Warned", 7),
        ("ResponseClock.Warned", 3),
        ("ResponseClock.Warned", 1),
        ("ResponseClock.Expired", None),
    ]
    row = world.clock(cid)
    assert (row.state, row.warned_level) == ("expired", 1)
    assert_row_is_replay(world, cid)
    with frozen_today("2026-11-10"):
        assert world.sweep().events == []  # an expired clock stays expired, nothing repeats


def test_a_sweep_that_finds_a_clock_far_inside_a_threshold_records_the_smallest_one(
    world: CorrWorld, item: str
) -> None:
    with frozen_today(MONDAY):
        cid = world.start_clock(item).stream_id
    with frozen_today("2026-11-01"):  # one day left: crosses 7, 3 and 1 at once
        events = world.sweep().events
    assert [e.payload["level"] for e in events] == [1]
    assert world.clock(cid).warned_level == 1


def test_a_paused_clock_is_not_swept(world: CorrWorld, item: str) -> None:
    with frozen_today(MONDAY):
        cid = world.start_clock(item).stream_id
        world.pause(cid)
    with frozen_today("2026-12-01"):
        assert world.sweep().events == []
    assert world.clock(cid).state == "paused"


def test_the_sweep_judges_as_of_a_day_never_later_than_today(world: CorrWorld, item: str) -> None:
    with frozen_today(MONDAY):
        world.start_clock(item)
    with frozen_today("2026-11-03"):
        with pytest.raises(InvalidClockError):
            world.sweep(on="2026-11-04")
        with pytest.raises(InvalidClockError):
            world.sweep(on="soon")
        assert [e.event_type for e in world.sweep(on="2026-10-31").events] == [
            "ResponseClock.Warned"
        ]


def test_the_sweep_reaches_a_clock_the_runner_may_not_read(world: CorrWorld) -> None:
    """Whoever runs the sweep, a deadline passes (ADR-0016: the sweep only appends the clock's
    own events and reads as the system)."""
    secret = world.forge_item("P123-COR-0002", confidentiality="restricted")
    controller = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")
    plain = cf.Viewer(actor="user:ann", level=0, account="user:ann")
    with frozen_today(MONDAY), cf.use_viewer(controller):
        cid = world.start_clock(secret).stream_id
    with frozen_today("2026-11-03"), cf.use_viewer(plain):
        assert world.sweep().events == []  # it acted, and says nothing about what they cannot read
    with cf.use_viewer(controller):
        assert world.clock(cid).state == "expired"


def test_a_clock_whose_history_the_engine_refuses_is_skipped_not_fatal(
    world: CorrWorld, item: str, caplog: pytest.LogCaptureFixture
) -> None:
    other = world.forge_item("P123-COR-0002")
    with frozen_today(MONDAY):
        bad = world.start_clock(item).stream_id
        good = world.start_clock(other).stream_id
    world.forge_clock_event(
        bad, "ResponseClock.Warned", {"day": "2026-10-20", "level": 5, "days_left": 5}
    )  # 5 is not a threshold of the clock
    with frozen_today("2026-11-03"), caplog.at_level("WARNING"):
        events = world.sweep().events
    assert [e.stream_id for e in events] == [good]
    assert "skipped by the sweep" in caplog.text


def test_closing_the_open_clocks_of_an_item_meets_or_cancels_them(
    world: CorrWorld, item: str
) -> None:
    with frozen_today(MONDAY):
        a = world.start_clock(item).stream_id
        b = world.start_clock(item, kind="time_bar").stream_id
        c = world.start_clock(item).stream_id
        world.cancel(c)
        cmd = correlated(SweepClocks(**BASE))
        with open_uow(world.db) as uow:
            events = close_clocks_of_item(
                uow,
                cmd,
                item,
                how="met",
                day=MONDAY,
                reason="answered",
                kinds=("response_from_them",),
            )
        assert [e.stream_id for e in events] == [a]
        with open_uow(world.db) as uow:
            events = close_clocks_of_item(
                uow, cmd, item, how="cancelled", day=MONDAY, reason="item voided"
            )
        assert [e.stream_id for e in events] == [b]
    assert [world.clock(i).state for i in (a, b, c)] == ["met", "cancelled", "cancelled"]


def test_the_sweep_command_needs_a_project(world: CorrWorld) -> None:
    from tl_mod_correspondence.errors import CorrespondenceScopeError

    with open_uow(world.db) as uow, pytest.raises(CorrespondenceScopeError):
        handle_sweep_clocks(uow, SweepClocks(**{**BASE, "scope": "company"}))
