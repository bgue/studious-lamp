"""``parse_intent_flags``: the four intent options as the command body's ``intent`` (P2-INT-T02)."""

from __future__ import annotations

import click
import pytest
from tl_cli.intent_flags import parse_intent_flags


def test_no_option_is_no_intent() -> None:
    assert parse_intent_flags(None, [], None, None) is None
    assert parse_intent_flags("", [], None, None) is None


def test_why_and_goal_ref() -> None:
    assert parse_intent_flags("welds are late", [], None, "g-1") == {
        "why": "welds are late",
        "goal_ref": "g-1",
    }


def test_next_items() -> None:
    got = parse_intent_flags(
        None, ["TransitionWorkflow:WP-1", "text:ask the foreman: Monday"], None, None
    )
    assert got == {
        "next": [
            {"command": "TransitionWorkflow", "target": "WP-1"},
            {"text": "ask the foreman: Monday"},
        ]
    }


@pytest.mark.parametrize("item", ["nocolon", "cmd:", ":WP-1", "text:", ""])
def test_a_malformed_next_item_is_a_usage_error(item: str) -> None:
    with pytest.raises(click.UsageError, match="expected command:target or text:<words>"):
        parse_intent_flags(None, [item], None, None)


def test_toward_state_and_condition() -> None:
    assert parse_intent_flags(None, [], "WP-1:released", None) == {
        "toward": {"target": "WP-1", "state": "released"}
    }
    assert parse_intent_flags(None, [], "WP-1:~released by Friday", None) == {
        "toward": {"target": "WP-1", "condition": "released by Friday"}
    }


@pytest.mark.parametrize("value", ["WP-1", "WP-1:", ":released", "WP-1:~"])
def test_a_malformed_toward_is_a_usage_error(value: str) -> None:
    with pytest.raises(click.UsageError, match="--toward"):
        parse_intent_flags(None, [], value, None)
