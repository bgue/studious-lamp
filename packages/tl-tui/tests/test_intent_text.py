"""``intent_lines``: the Why, Next, Toward and Goal lines of an event's intent (P2-INT-T04)."""

from __future__ import annotations

from tl_core.intent import Intent, IntentRef, IntentToward
from tl_tui.intent_text import intent_lines

FULL = Intent(
    why="welds are late",
    next=[
        IntentRef(command="TransitionWorkflow", target="01ID"),
        IntentRef(text="ask the foreman"),
    ],
    toward=IntentToward(target="01ID", state="released"),
    goal_ref="g-1",
)


def test_none_and_empty_show_nothing() -> None:
    assert intent_lines(None, technical=False) == []
    assert intent_lines(Intent(), technical=False) == []
    assert intent_lines(Intent(), technical=True) == []


def test_plain_lines_use_names_for_ids() -> None:
    assert intent_lines(FULL, technical=False, names={"01ID": "WP-1"}) == [
        "Why: welds are late",
        "Next: TransitionWorkflow WP-1",
        "Next: ask the foreman",
        "Toward: WP-1 -> released",
        "Goal: g-1",
    ]


def test_an_unmapped_id_and_not_available_are_shown_as_is() -> None:
    hidden = Intent(
        next=[IntentRef(text="not available")],
        toward=IntentToward(target="not available", condition="done"),
    )
    assert intent_lines(hidden, technical=False) == [
        "Next: not available",
        "Toward: not available -> done",
    ]
    assert intent_lines(FULL, technical=False)[1] == "Next: TransitionWorkflow 01ID"


def test_technical_lines_use_the_raw_keys_and_ids() -> None:
    cond = Intent(toward=IntentToward(target="01ID", condition="released by Friday"))
    assert intent_lines(FULL, technical=True, names={"01ID": "WP-1"}) == [
        "why: welds are late",
        "next: TransitionWorkflow 01ID",
        "next: ask the foreman",
        "toward: 01ID -> released",
        "goal_ref: g-1",
    ]
    assert intent_lines(cond, technical=True) == ["toward: 01ID ~ released by Friday"]
