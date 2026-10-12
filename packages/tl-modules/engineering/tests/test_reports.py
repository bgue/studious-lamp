"""The base reports: summary by class and state, missing psets, pattern violations (P1-I1-T11)."""

from __future__ import annotations

from typing import Any

import pytest
from engworld import seed_registry
from tl_adapters.db import DbTarget, open_uow
from tl_mod_engineering import reports
from tl_mod_engineering.handlers.tags import (
    CreateTag,
    RecordTag,
    RenameTag,
    handle_create_tag,
    handle_record_tag,
    handle_rename_tag,
)
from tl_mod_engineering.reports import MissingIssue, MissingLine, SummaryLine, ViolationLine

pytestmark = pytest.mark.usefixtures("fixture_schemas")
SCOPE = "project:P123"
BASE: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": SCOPE}


def make(db: DbTarget, number: str, **more: Any) -> str:
    with open_uow(db) as uow:
        return handle_create_tag(uow, CreateTag(**BASE, number=number, **more)).stream_id


def make_legacy(db: DbTarget, number: str) -> str:
    """A tag whose number breaks the pattern, as the import service makes it."""
    with open_uow(db) as uow:
        return handle_record_tag(uow, RecordTag(**BASE, number=number), origin="import").stream_id


@pytest.fixture
def ledger(db: DbTarget) -> DbTarget:
    seed_registry(db)
    make(db, "47-FV-1001", class_code="ControlValve")  # nothing filled in
    make(
        db,
        "47-FV-1002",
        class_code="ControlValve",
        psets={"valve_data": {"size_in": 4, "manufacturer": "Acme"}},
    )
    make(db, "10-PT-0001")  # no class
    make(db, "10-HV-0001", class_code="ManualValve")
    make(db, "47-FV-1005", class_code="ManualValve")  # FV does not usually identify a ManualValve
    make_legacy(db, "LEGACY-1")
    old = make(db, "47-FV-1006", class_code="ControlValve")
    with open_uow(db) as uow:
        handle_rename_tag(
            uow, RenameTag(**BASE, stream_id=old, new_number="47-FV-1007", reason="r")
        )
    return db


def test_the_summary_counts_tags_in_service_by_class_and_state(ledger: DbTarget) -> None:
    with open_uow(ledger, readonly=True) as uow:
        lines = reports.register_summary(uow.conn(), SCOPE)
    assert lines == [
        SummaryLine(None, None, tags=2, ok=2, warning=0, nonconformant=0),
        SummaryLine("ControlValve", None, tags=3, ok=1, warning=0, nonconformant=2),
        SummaryLine("ManualValve", None, tags=2, ok=0, warning=0, nonconformant=2),
    ]


def test_the_summary_of_another_project_is_empty(ledger: DbTarget) -> None:
    with open_uow(ledger, readonly=True) as uow:
        assert reports.register_summary(uow.conn(), "project:P999") == []


def test_missing_lists_what_each_tag_lacks_by_number(ledger: DbTarget) -> None:
    with open_uow(ledger, readonly=True) as uow:
        lines = reports.missing_psets(uow, SCOPE)
    assert [line.number for line in lines] == [
        "10-HV-0001",
        "47-FV-1001",
        "47-FV-1005",
        "47-FV-1007",
    ]
    first = next(line for line in lines if line.number == "47-FV-1001")
    assert first == MissingLine(
        "47-FV-1001",
        "ControlValve",
        None,
        [
            MissingIssue(
                "psets.valve_data",
                "class_required",
                "nonconformant",
                "Valve data is required by the record's class and has no values",
            ),
            MissingIssue(
                "psets.valve_data.manufacturer",
                "required_in_state",
                "warning",
                "Manufacturer is required",
            ),
        ],
    )


def test_a_tag_with_everything_its_class_requires_and_a_superseded_tag_are_not_listed(
    ledger: DbTarget,
) -> None:
    with open_uow(ledger, readonly=True) as uow:
        listed = {line.number for line in reports.missing_psets(uow, SCOPE)}
    assert "47-FV-1002" not in listed  # complete
    assert "47-FV-1006" not in listed  # superseded by 47-FV-1007


def test_missing_can_be_narrowed_to_one_level(ledger: DbTarget) -> None:
    with open_uow(ledger, readonly=True) as uow:
        hard = reports.missing_psets(uow, SCOPE, level="nonconformant")
        soft = reports.missing_psets(uow, SCOPE, level="warning")
    assert {i.level for line in hard for i in line.issues} == {"nonconformant"}
    assert {i.level for line in soft for i in line.issues} == {"warning"}
    assert all(line.issues[0].rule == "class_required" for line in hard)


def test_pattern_violations_list_the_numbers_that_break_the_pattern(ledger: DbTarget) -> None:
    with open_uow(ledger, readonly=True) as uow:
        plain = reports.pattern_violations(uow.conn(), SCOPE)
        with_warnings = reports.pattern_violations(uow.conn(), SCOPE, include_warnings=True)
    assert [line.number for line in plain] == ["LEGACY-1"]
    assert plain[0].number_status == "violation"
    assert [p["rule"] for p in plain[0].problems] == ["pattern"]
    assert [line.number for line in with_warnings] == ["47-FV-1005", "LEGACY-1"]
    assert with_warnings[0] == ViolationLine(
        "47-FV-1005",
        "ok",
        [
            {
                "segment": "mnemonic",
                "rule": "class_mnemonic",
                "level": "warning",
                "message": "'FV' does not usually identify a ManualValve (HV)",
            }
        ],
    )
