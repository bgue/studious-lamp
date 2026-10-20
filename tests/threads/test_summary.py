"""The deterministic /summarise text: a pure function of a page of the thread (T10c).

Provided; do not edit.
"""

from __future__ import annotations

from tl_core.integration.contract import RecordRef
from tl_core.threads.contract import (
    SUMMARY_MAX_CHARS,
    SUMMARY_MAX_MESSAGES,
    DispatchOutcome,
    ThreadMessageView,
)
from tl_core.threads.queries import ThreadPage, ThreadParticipant
from tl_core.threads.summary import LINE_CHARS, build_summary

RECORD = RecordRef(id="R1", key="REC-1", record_type="core.Record", version=1)


def message(
    n: int,
    body: str,
    *,
    author: str = "user:a",
    retracted: bool = False,
    dispatch: DispatchOutcome | None = None,
) -> ThreadMessageView:
    return ThreadMessageView(
        message_id=f"M{n}",
        record_id="R1",
        author=author,
        body="" if retracted else body,
        posted_at="2026-10-17T07:00:00+00:00",
        retracted=retracted,
        dispatch=dispatch,
    )


def page(
    messages: list[ThreadMessageView],
    kinds: list[str] | None = None,
    *,
    total: int | None = None,
    people: list[str] | None = None,
) -> ThreadPage:
    return ThreadPage(
        record=RECORD,
        enabled=True,
        dispatch_enabled=True,
        message_count=len(messages) if total is None else total,
        participants=[ThreadParticipant(actor=p, reasons=["author"]) for p in people or []],
        messages=messages,
        seqs=list(range(1, len(messages) + 1)),
        kinds=kinds if kinds is not None else ["message"] * len(messages),
    )


def test_the_summary_says_it_is_counted_and_lists_counts_people_and_messages() -> None:
    text = build_summary(
        page(
            [message(1, "Flanges short\nfor W019"), message(2, "On it", author="user:b")],
            total=7,
            people=["user:a", "user:b"],
        )
    )
    assert text.splitlines() == [
        "Thread summary (counted by the system, no model).",
        "Messages: 7. Participants: user:a, user:b.",
        "Last messages:",
        "- user:a: Flanges short",
        "- user:b: On it",
    ]


def test_nobody_in_the_thread_reads_none_and_an_empty_page_has_no_message_list() -> None:
    text = build_summary(page([]))
    assert text.splitlines() == [
        "Thread summary (counted by the system, no model).",
        "Messages: 0. Participants: none.",
    ]


def test_dispatched_commands_are_listed_with_their_result_lines() -> None:
    raised = DispatchOutcome(message_id="M2", verb="raise", summary="Create record: Leak")
    quiet = DispatchOutcome(message_id="M3", verb="hold")
    text = build_summary(
        page(
            [
                message(1, "Leak at C4"),
                message(2, "/raise record Leak", dispatch=raised),
                message(3, "/hold", dispatch=quiet),
            ],
            ["message", "dispatch", "dispatch"],
        )
    )
    assert text.splitlines()[2:] == [
        "Dispatched:",
        "- raise: Create record: Leak",
        "- hold: done",
        "Last messages:",
        "- user:a: Leak at C4",
    ]


def test_retracted_summary_and_reminder_messages_are_left_out_of_the_list() -> None:
    text = build_summary(
        page(
            [
                message(1, "kept"),
                message(2, "gone", retracted=True),
                message(3, "an older summary"),
                message(4, "ring them", author="svc:threads"),
            ],
            ["message", "message", "summary", "reminder"],
        )
    )
    assert text.splitlines()[-2:] == ["Last messages:", "- user:a: kept"]


def test_only_the_last_messages_are_shown_and_a_long_line_is_cut() -> None:
    many = [message(i, f"message {i}") for i in range(SUMMARY_MAX_MESSAGES + 5)]
    lines = build_summary(page(many)).splitlines()
    listed = lines[lines.index("Last messages:") + 1 :]
    assert len(listed) == SUMMARY_MAX_MESSAGES
    assert listed[0] == "- user:a: message 5" and listed[-1].endswith(f"message {len(many) - 1}")
    long = build_summary(page([message(1, "x" * 500)])).splitlines()[-1]
    assert long == "- user:a: " + "x" * (LINE_CHARS - 1) + "…"


def test_the_text_is_bounded_and_ends_with_an_ellipsis_when_cut() -> None:
    wide = [message(i, "y" * 90, author=f"user:{'p' * 30}{i}") for i in range(SUMMARY_MAX_MESSAGES)]
    text = build_summary(page(wide, people=[f"user:{'q' * 40}{i}" for i in range(60)]))
    assert len(text) == SUMMARY_MAX_CHARS and text.endswith("…")


def test_the_same_page_gives_the_same_text() -> None:
    same = page([message(1, "a"), message(2, "b")])
    assert build_summary(same) == build_summary(same.model_copy(deep=True))


def test_a_text_of_exactly_the_limit_is_not_cut() -> None:
    base = build_summary(page([message(1, "hello", author="user:")]))
    padding = SUMMARY_MAX_CHARS - len(base)
    assert padding > 0
    text = build_summary(page([message(1, "hello", author="user:" + "a" * padding)]))
    assert len(text) == SUMMARY_MAX_CHARS and text.endswith("hello")
