"""Every awp command is a proposing row or an exclusion with a reason (ADR-0027, SR3 F4)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from tl_mod_awp.commands import AWP_COMMANDS
from tl_mod_awp.module import PROPOSABLE
from tl_mod_quality.module import PUNCH_COMMANDS
from tl_mod_requisitions.module import REQUISITIONS_COMMANDS

EXCLUSIONS = Path(__file__).resolve().parents[4] / "tests" / "tools" / "proposable_exclusions.toml"


def test_every_awp_command_is_a_proposable_row_or_an_exclusion() -> None:
    excluded = tomllib.loads(EXCLUSIONS.read_text())["commands"]
    rows = {p.model.__name__ for p in PROPOSABLE}
    every = {c.model.__name__ for c in AWP_COMMANDS}
    others = {c.model.__name__ for c in (*REQUISITIONS_COMMANDS, *PUNCH_COMMANDS)}
    mine = {n for n in excluded if n in every}
    assert rows <= every and rows | mine == every and not rows & mine
    assert set(excluded) - every <= others, "stale exclusion: names no known command"
    assert all(excluded[name] for name in every - rows)
