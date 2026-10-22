"""The status timeline as text (P1-UX2-S5): rows from events and clocks, oldest first."""

from __future__ import annotations

from fakes_rfi_record import answered_history, clock, event, transition
from tl_mod_correspondence.names import COMMERCIAL
from tl_tui.display import Labels, find_technical
from tl_tui.timeline_text import TimelineRow, person, timeline_lines, timeline_rows

PLAIN = Labels()


def whats(rows: list[TimelineRow]) -> list[str]:
    return [row.what for row in rows]


def test_rows_run_oldest_first_whatever_the_order_given() -> None:
    events = list(reversed(answered_history()))
    rows = timeline_rows(events, [], PLAIN, technical=False)
    assert [row.when for row in rows] == sorted(row.when for row in rows)
    assert whats(rows)[0] == "Raised" and whats(rows)[-1] == "Answer accepted"


def test_a_tie_on_the_moment_goes_by_the_sequence() -> None:
    first = event(8, "Technical.Defined", "user:ben")
    second = event(7, "Technical.Defined", "user:amy").model_copy(
        update={"effective_at": first.effective_at}
    )
    rows = timeline_rows([first, second], [], PLAIN, technical=False)
    assert [row.who for row in rows] == ["amy", "ben"]


def test_the_whole_walk_reads_as_the_states_it_went_through() -> None:
    rows = timeline_rows(answered_history(), [], PLAIN, technical=False)
    assert whats(rows) == [
        "Raised", "Submitted", "Issued", "Answered", "Answer rejected", "Reissued",
        "Issued", "Answered", "Answer accepted",
    ]  # fmt: skip


def test_reject_then_reissue_then_accept_is_three_rows_with_who_and_note() -> None:
    rows = timeline_rows(answered_history(), [], PLAIN, technical=False)
    by_what = {row.what: row for row in rows}
    assert by_what["Answer rejected"] == TimelineRow(
        "2026-10-09", "amy", "Answer rejected", "does not answer the clash"
    )
    assert by_what["Reissued"].note == "names both beams"
    assert by_what["Answer accepted"].note == ""
    assert by_what["Answered"].who == "cy"


def test_property_edits_and_automatic_steps_are_not_rows() -> None:
    kinds = {e.event_type for e in answered_history()}
    assert {"Technical.Updated", "Record.Created", "Correspondence.Responded"} <= kinds
    rows = timeline_rows(answered_history(), [], PLAIN, technical=False)
    assert len(rows) == 9  # 19 events; the edit, the envelope and the follow-on steps are not rows


def test_an_unknown_event_type_or_transition_is_skipped_never_shown_raw() -> None:
    events = [
        event(1, "Technical.Defined"),
        event(2, "Weird.NewThing", payload={"transition": "submit"}),
        transition(3, "mystery_step"),
        event(4, "Technical.Reviewed", payload={"decision": "maybe"}),
    ]
    rows = timeline_rows(events, [], PLAIN, technical=False)
    assert whats(rows) == ["Raised"]
    assert "Weird" not in " ".join(timeline_lines(rows))


def test_a_service_reads_as_system_and_an_agent_with_the_gear_mark() -> None:
    events = [
        event(1, "Technical.Defined", "svc:rules-engine"),
        event(2, "Technical.Answered", "agent:planner"),
    ]
    rows = timeline_rows(events, [], PLAIN, technical=False)
    assert [row.who for row in rows] == ["System", "planner ⚙"]
    assert person("svc:rules-engine", PLAIN, technical=True) == "svc:rules-engine"
    assert person("agent:planner", PLAIN, technical=True) == "agent:planner ⚙"
    named = Labels(services={"agent:planner": "Planner", "svc:rules-engine": "Rules"})
    assert [r.who for r in timeline_rows(events, [], named, technical=False)] == [
        "Rules",
        "Planner ⚙",
    ]


def test_technical_mode_adds_the_time_and_plain_mode_leaks_nothing() -> None:
    noisy = [
        e.model_copy(update={"payload": {**e.payload, "id": "01M5GS39BYTWGS9DRGEVVE6PZ1"}})
        for e in answered_history()
    ]
    plain = timeline_rows(noisy, [clock()], PLAIN, technical=False)
    technical = timeline_rows(noisy, [clock()], PLAIN, technical=True)
    assert plain[0].when == "2026-10-05" and technical[0].when.startswith("2026-10-05 09:")
    assert (
        find_technical("\n".join(timeline_lines(plain)), Labels(domains={"technical": "T"})) == []
    )
    assert all(len(row.when) == 16 for row in technical if row.who != "System")


def test_a_clock_met_expired_or_cancelled_is_a_row_and_a_running_one_is_not() -> None:
    met = clock()
    expired = clock(id="C2", state="running", effective_state="expired", days_left=-3,
                    closed_on=None, closed_reason=None, due_on="2026-10-20")  # fmt: skip
    cancelled = clock(id="C3", state="cancelled", effective_state="cancelled",
                      closed_on="2026-10-15", closed_reason="withdrawn")  # fmt: skip
    running = clock(id="C4", state="running", effective_state="running", closed_on=None)
    rows = timeline_rows([], [running, cancelled, expired, met], PLAIN, technical=False)
    assert rows == [
        TimelineRow("2026-10-12", "System", "Answer required clock met", "Answered"),
        TimelineRow("2026-10-15", "System", "Answer required clock cancelled", "Withdrawn"),
        TimelineRow("2026-10-20", "System", "Answer required clock expired", "3 calendar days overdue"),  # noqa: E501
    ]  # fmt: skip
    text = "\n".join(timeline_lines(rows))
    assert "P123-default" not in text and "C01" not in text
    assert find_technical(text) == []


def test_a_clock_row_follows_the_events_of_its_day() -> None:
    events = [event(1, "Technical.Answered", "user:cy", day=12, hour=23)]
    rows = timeline_rows(events, [clock()], PLAIN, technical=False)
    assert whats(rows) == ["Answered", "Answer required clock met"]


def test_an_escalation_is_a_row_from_the_first_event_of_the_item_raised_from_it() -> None:
    raised = event(
        5, "Correspondence.Defined", "user:ben", day=14, payload={"number": "P123-EW-0001"},
        stream_id="ID-EW", stream_type=COMMERCIAL,
    )  # fmt: skip
    rows = timeline_rows(answered_history(), [], PLAIN, technical=False, escalations=[raised])
    assert rows[-1] == TimelineRow("2026-10-14", "ben", "Escalated", "to P123-EW-0001")
    assert not any(
        row.what == "Escalated"
        for row in timeline_rows(answered_history(), [], PLAIN, technical=False)
    )


def test_a_commercial_item_reports_its_own_defined_and_a_received_letter_says_received() -> None:
    received = event(1, "Correspondence.Defined", payload={"direction": "in"}, stream_type="x.Y")
    drafted = event(2, "Correspondence.Defined", payload={"direction": "out"}, stream_type="x.Y")
    owned = event(3, "Correspondence.Defined", stream_type=COMMERCIAL)
    own = event(4, "Commercial.Defined", stream_type=COMMERCIAL)
    rows = timeline_rows([received, drafted, owned, own], [], PLAIN, technical=False)
    assert whats(rows) == ["Received", "Drafted", "Raised"]


def test_the_lines_read_date_who_what_and_the_note() -> None:
    rows = [TimelineRow("2026-10-12", "Amy Chen", "Issued", "sent to Acme Piling")]
    assert timeline_lines(rows) == ["2026-10-12  Amy Chen  Issued  - sent to Acme Piling"]
    assert timeline_lines([TimelineRow("2026-10-12", "Amy", "Closed")]) == [
        "2026-10-12  Amy  Closed"
    ]
