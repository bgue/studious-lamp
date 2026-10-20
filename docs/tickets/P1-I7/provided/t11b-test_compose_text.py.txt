"""The composer's text: the preview panel and the slash-verb completion (P1-I7 WS-B, T11b).

Provided; do not edit.
"""

from __future__ import annotations

from tl_core.integration.contract import PlannedCommand, Problem, RecordRef
from tl_core.threads.contract import DispatchPreview, ParsedDispatch
from tl_core.threads.parser import CommandLineParser
from tl_tui.compose_text import VERB_HELP, preview_lines, verb_candidates

RECORD = RecordRef(id="R1", key="IWP-0042", record_type="core.Record", version=3)


def parsed(line: str) -> ParsedDispatch:
    found = CommandLineParser().parse(line)
    assert isinstance(found, ParsedDispatch)
    return found


def preview(planned: list[PlannedCommand], *, can: bool = True, **kw: object) -> DispatchPreview:
    return DispatchPreview(
        record=RECORD,
        parsed=parsed("/raise record Clash"),
        planned=planned,
        side_effecting=True,
        can_dispatch=can,
        token="a" * 64,
        expires_at="2026-10-17T08:00:00+00:00",
        **kw,  # type: ignore[arg-type]
    )


def test_the_preview_panel_lists_the_commands_the_problems_and_the_question() -> None:
    ok = PlannedCommand(
        command_type="CreateRecord", access="user", permitted=True, summary="Create record: Clash"
    )
    lines = preview_lines(preview([ok], notes=["counted by the system"]))
    assert lines == [
        "/raise record Clash",
        "1. CreateRecord · user · ok · Create record: Clash",
        "· counted by the system",
        "Enter to run, Esc to edit",
    ]


def test_the_preview_panel_says_why_a_command_cannot_run() -> None:
    denied = PlannedCommand(command_type="ChangeSetting", access="admin", summary="Change")
    refused = PlannedCommand(
        command_type="AddLink",
        access="user",
        permitted=True,
        summary="Link A to B",
        problem=Problem(code="command_refused", message="SelfLinkError: no"),
    )
    lines = preview_lines(
        preview([denied, refused], can=False, problems=[Problem(code="x", message="Plan problem")])
    )
    assert lines == [
        "/raise record Clash",
        "1. ChangeSetting · admin · not permitted · Change",
        "2. AddLink · user · command_refused · Link A to B",
        "! SelfLinkError: no",
        "! Plan problem",
        "Cannot be dispatched: Esc to edit",
    ]


def test_verb_completion_lists_every_verb_in_order_and_filters_by_prefix() -> None:
    assert [v for v, _ in verb_candidates("")] == [v for v, _ in VERB_HELP]
    assert len(VERB_HELP) == 11
    assert [v for v, _ in verb_candidates("r")] == ["raise", "release", "remind"]
    assert [v for v, _ in verb_candidates("RE")] == ["release", "remind"]
    assert [v for v, _ in verb_candidates("summ")] == ["summarise"]
    assert [v for v, _ in verb_candidates("summarize")] == ["summarise"]
    assert verb_candidates("zzz") == []
    assert all(help_text for _, help_text in VERB_HELP)
