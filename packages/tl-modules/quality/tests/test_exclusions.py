"""ADR-0027 decision 4: every punch command is a ProposableCommand row or an exclusion."""

from __future__ import annotations

import tomllib
from pathlib import Path

from tl_mod_quality.module import PROPOSABLE, PUNCH_COMMANDS

ROOT = Path(__file__).resolve().parents[4]
EXCLUSIONS = ROOT / "tests" / "tools" / "proposable_exclusions.toml"


def test_every_command_is_a_row_or_an_exclusion() -> None:
    excluded = set(tomllib.loads(EXCLUSIONS.read_text())["commands"])
    rows = {p.model.__name__ for p in PROPOSABLE}
    names = {c.model.__name__ for c in PUNCH_COMMANDS}
    assert rows == {"RaisePunchItem"}
    assert names <= rows | excluded
    assert not rows & excluded
    assert {"ClearPunchItem", "EditPunchItem", "VerifyPunchItem", "ReopenPunchItem"} <= excluded
    assert "VoidPunchItem" in excluded


def test_the_proposal_runs_as_the_accepting_person_with_the_user_word() -> None:
    (row,) = PROPOSABLE
    assert (row.tool, row.access, row.agent_tool) == ("propose_punch_item", "user", True)
