"""INSP S2: the eleven quality commands of the design are rows, marked and decided."""

from __future__ import annotations

from ip_rules import problems

PUNCH = {"RaisePunchItem", "EditPunchItem", "ClearPunchItem", "VerifyPunchItem"}
PUNCH |= {"ReopenPunchItem", "VoidPunchItem"}
NAMES = {"CreateChecklist", "EditChecklist", "PublishChecklist", "RetireChecklist"}
NAMES |= {"ReviseChecklist", "PlanInspection", "ScheduleInspection", "RecordInspectionResult"}
NAMES |= {"VerifyInspection", "ReinspectInspection", "CancelInspection"}


def test_the_quality_rows_of_the_inspection_pass_every_rule() -> None:
    assert problems("quality", PUNCH | NAMES) == []
