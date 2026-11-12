"""Every awp command is a proposing row or an exclusion with a reason (ADR-0027, SR3 F4)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from tl_mod_awp.commands import AWP_COMMANDS
from tl_mod_awp.module import PROPOSABLE

EXCLUSIONS = Path(__file__).resolve().parents[4] / "tests" / "tools" / "proposable_exclusions.toml"


def test_every_awp_command_is_a_proposable_row_or_an_exclusion() -> None:
    excluded = tomllib.loads(EXCLUSIONS.read_text())["commands"]
    rows = {p.model.__name__ for p in PROPOSABLE}
    every = {c.model.__name__ for c in AWP_COMMANDS}
    assert rows <= every and rows | set(excluded) >= every and not rows & set(excluded)
    assert all(excluded[name] for name in every - rows)
