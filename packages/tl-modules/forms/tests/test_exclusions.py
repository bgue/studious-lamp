"""ADR-0027 decision 4: every forms command is a ProposableCommand row or an exclusion."""

from __future__ import annotations

import tomllib
from pathlib import Path

from tl_mod_forms.module import FORMS_COMMANDS, PROPOSABLE

ROOT = Path(__file__).resolve().parents[4]
EXCLUSIONS = ROOT / "tests" / "tools" / "proposable_exclusions.toml"


def test_every_command_is_a_row_or_an_exclusion() -> None:
    excluded = tomllib.loads(EXCLUSIONS.read_text())["commands"]
    rows = {p.model.__name__ for p in PROPOSABLE}
    names = {c.model.__name__ for c in FORMS_COMMANDS}
    assert rows == {"SubmitForm"}
    assert names <= rows | set(excluded)
    assert not rows & set(excluded)
    assert len(names) == 15 and len(names - rows) == 14 and (names - rows) <= set(excluded)
    for name in names - rows:
        reason = excluded[name]
        assert reason == "person acts directly" or reason.startswith("act: ")


def test_the_proposal_runs_as_the_accepting_person_with_the_user_word() -> None:
    (row,) = PROPOSABLE
    assert (row.tool, row.access, row.agent_tool) == ("propose_form_submission", "user", True)
