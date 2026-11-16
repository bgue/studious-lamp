"""ADR-0027 decision 4 for the inspection commands: a row or an exclusion; the marks."""

from __future__ import annotations

import tomllib
from pathlib import Path

from tl_mod_quality.module import INSP_COMMANDS, PROPOSABLE, QUALITY_COMMANDS, spec

ROOT = Path(__file__).resolve().parents[4]
TOOLS = ROOT / "tests" / "tools"
NAMES = {c.model.__name__ for c in INSP_COMMANDS}


def test_every_command_is_a_row_or_an_exclusion() -> None:
    excluded = set(tomllib.loads((TOOLS / "proposable_exclusions.toml").read_text())["commands"])
    rows = {p.model.__name__ for p in PROPOSABLE}
    assert rows == {"RaisePunchItem", "PlanInspection"}
    assert {c.model.__name__ for c in QUALITY_COMMANDS} <= rows | excluded
    assert not rows & excluded
    assert len(NAMES) == 11 and len(NAMES - rows) == 10 and NAMES - rows <= excluded


def test_the_proposal_row_runs_plan_inspection_as_the_accepting_person() -> None:
    (row,) = (p for p in PROPOSABLE if p.tool == "propose_inspection")
    assert (row.model.__name__, row.access, row.agent_tool) == ("PlanInspection", "user", True)


def test_one_command_is_eligible_and_the_other_ten_are_reserved() -> None:
    marks = tomllib.loads((TOOLS / "delegation_marks.toml").read_text())
    assert {n for n in NAMES if n in marks["eligible"]} == {"PlanInspection"}
    assert {n for n in NAMES if marks["excluded"].get(n) == "reserved"} == NAMES - {
        "PlanInspection"
    }


def test_the_words_of_the_commands_are_the_design_table() -> None:
    words = {c.model.__name__: c.access for c in INSP_COMMANDS}
    assert words == {
        "CreateChecklist": "quality.checklist.edit",
        "EditChecklist": "quality.checklist.edit",
        "PublishChecklist": "quality.checklist.publish",
        "RetireChecklist": "quality.checklist.publish",
        "ReviseChecklist": "quality.checklist.publish",
        "PlanInspection": "quality.inspection.plan",
        "ScheduleInspection": "quality.inspection.plan",
        "RecordInspectionResult": "quality.inspection.record",
        "VerifyInspection": "quality.inspection.verify",
        "ReinspectInspection": "quality.inspection.plan",
        "CancelInspection": "quality.inspection.cancel",
    }
    assert dict(spec().command_words) == {c.model.__name__: c.access for c in QUALITY_COMMANDS}
