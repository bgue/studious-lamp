"""The display text of a record thread: header, lines, cards, preview panel, verb completion
(P1-I7 WS-B, T11a).

Provided; do not edit.
"""

from __future__ import annotations

from tl_core.integration.contract import RecordRef
from tl_core.threads.contract import (
    DispatchOutcome,
    DispatchResult,
    ThreadMessageView,
)
from tl_core.threads.queries import ThreadPage, ThreadParticipant
from tl_tui.thread_text import (
    card_lines,
    clock,
    header_text,
    message_lines,
    person,
)

RECORD = RecordRef(id="R1", key="IWP-0042", record_type="core.Record", version=3)


def message(
    n: int,
    body: str,
    *,
    author: str = "user:rgarcia",
    edited: bool = False,
    retracted: bool = False,
    dispatch: DispatchOutcome | None = None,
) -> ThreadMessageView:
    return ThreadMessageView(
        message_id=f"M{n}",
        record_id="R1",
        author=author,
        body="" if retracted else body,
        posted_at=f"2026-10-17T07:{n:02d}:30+00:00",
        edited=edited,
        retracted=retracted,
        dispatch=dispatch,
    )


def page(
    messages: list[ThreadMessageView],
    kinds: list[str] | None = None,
    *,
    enabled: bool = True,
    dispatch: bool = True,
    people: int = 3,
) -> ThreadPage:
    return ThreadPage(
        record=RECORD,
        enabled=enabled,
        dispatch_enabled=dispatch,
        message_count=len(messages),
        participants=[ThreadParticipant(actor=f"user:p{i}") for i in range(people)],
        messages=messages,
        seqs=list(range(1, len(messages) + 1)),
        kinds=kinds if kinds is not None else ["message"] * len(messages),
    )


def test_person_and_clock() -> None:
    assert person("user:rgarcia") == "rgarcia"
    assert person("agent:planner") == "agent:planner ⚙"
    assert person("svc:threads") == "svc:threads"
    assert clock("2026-10-17T07:02:30+00:00") == "07:02"
    assert clock("short") == "short"


def test_the_header_names_the_record_the_people_and_dispatch() -> None:
    assert header_text(page([])) == "IWP-0042 · Thread · 3 participants · dispatch on"
    assert header_text(page([], dispatch=False, people=1)) == (
        "IWP-0042 · Thread · 1 participant · dispatch off"
    )
    assert header_text(page([], enabled=False)) == (
        "IWP-0042 · Thread · threads are off for core.Record"
    )


def test_a_message_is_a_clock_an_author_and_its_text_with_the_rest_indented() -> None:
    lines = message_lines(page([message(2, "Crew P-07 starting\nFlanges short for W019")]))
    assert lines == ["07:02 rgarcia  Crew P-07 starting", "      Flanges short for W019"]


def test_edited_retracted_and_agent_messages() -> None:
    lines = message_lines(
        page(
            [
                message(1, "first", edited=True),
                message(2, "gone", retracted=True),
                message(3, "propose /dispatch scaffold-inspect", author="agent:planner"),
            ]
        )
    )
    assert lines == [
        "07:01 rgarcia  first (edited)",
        "07:02 rgarcia  [retracted]",
        "07:03 agent:planner ⚙  propose /dispatch scaffold-inspect",
    ]


def test_reminders_and_summaries_are_marked_by_their_kind() -> None:
    lines = message_lines(
        page(
            [
                message(1, "Reminder from user:a", author="svc:threads"),
                message(2, "Thread summary"),
            ],
            ["reminder", "summary"],
        )
    )
    assert lines == [
        "07:01 svc:threads  ⏰ Reminder from user:a",
        "07:02 rgarcia  Σ Thread summary",
    ]


def test_a_dispatch_shows_its_result_card_under_the_line() -> None:
    outcome = DispatchOutcome(
        message_id="M3",
        verb="raise",
        summary="Create record: Clash",
        results=[
            DispatchResult(
                command_type="CreateRecord", stream_id="S1", key="P123-REC-0044", version=1
            ),
            DispatchResult(command_type="AddLink", stream_id="S2", version=1),
        ],
        link_ids=["L1"],
    )
    assert card_lines(outcome) == [
        "▤ raise: Create record: Clash",
        "  CreateRecord P123-REC-0044 v1",
        "  AddLink S2 v1",
        "  1 dispatched-from link added",
    ]
    assert card_lines(DispatchOutcome(message_id="M", verb="notify")) == ["▤ notify: done"]
    two = DispatchOutcome(message_id="M", verb="hold", link_ids=["a", "b"])
    assert card_lines(two)[-1] == "  2 dispatched-from links added"
    lines = message_lines(page([message(3, "/raise record Clash", dispatch=outcome)], ["dispatch"]))
    assert lines[0] == "07:03 rgarcia  /raise record Clash"
    assert lines[1:] == [f"      {ln}" for ln in card_lines(outcome)]
