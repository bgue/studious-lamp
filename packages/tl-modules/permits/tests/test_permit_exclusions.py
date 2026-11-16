"""Marks and decisions of the ten permit commands (D-PTW1: permits are safety acts)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from tl_mod_permits.module import COMMANDS, PROPOSABLE, spec

EXCLUSIONS = Path(__file__).resolve().parents[4] / "tests" / "tools" / "proposable_exclusions.toml"
NAMES = {c.model.__name__ for c in COMMANDS}


def test_all_ten_commands_are_excluded_reserved_in_the_row() -> None:
    assert len(COMMANDS) == len(NAMES) == 10
    assert {c.model.__name__: c.meta for c in COMMANDS} == {
        name: {"delegation": "excluded:reserved"} for name in NAMES
    }


def test_request_permit_keeps_its_agent_row_and_the_other_nine_are_excluded() -> None:
    assert [(p.tool, p.model.__name__, p.access) for p in PROPOSABLE] == [
        ("propose_permit", "RequestPermit", "user")
    ]
    listed = tomllib.loads(EXCLUSIONS.read_text(encoding="utf-8"))["commands"]
    assert {n for n in NAMES if n in listed} == NAMES - {"RequestPermit"}
    assert "RequestPermit" not in listed


def test_the_spec_words_agree_with_the_rows() -> None:
    words = dict(spec().command_words)
    assert words == {c.model.__name__: c.access for c in COMMANDS}
    assert words["CancelPermit"] == words["ClosePermit"] == "permits.close"
    assert words["RejectPermit"] == words["ApprovePermit"] == "permits.approve"
