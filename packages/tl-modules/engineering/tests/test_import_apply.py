"""Applying a tag-list import to a project's tags on every adapter (P1-I1-T10c)."""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_mod_engineering import registry
from tl_mod_engineering.errors import ImportApplyError
from tl_mod_engineering.handlers.tags import RenameTag, handle_rename_tag
from tl_mod_engineering.imports.apply import apply_plan, existing_tags
from tl_mod_engineering.imports.diff import plan_import
from tl_mod_engineering.imports.mapping import parse_mapping, read_rows
from tl_mod_engineering.imports.model import ImportPlan
from tl_mod_engineering.testing import seed_registry

pytestmark = pytest.mark.usefixtures("fixture_schemas")

SCOPE = "project:P123"
MAPPING = parse_mapping(
    yaml.safe_dump(
        {
            "name": "instrument-index",
            "description": "A test export.",
            "columns": [
                {"column": "TAG NO", "to": "number"},
                {"column": "SERVICE", "to": "service"},
                {
                    "column": "CLASS",
                    "to": "class",
                    "values": {"CV": "ControlValve", "MV": "ManualValve", "XX": "NoSuchClass"},
                },
                {"column": "SIZE", "to": "psets.valve_data.size_in", "type": "decimal"},
                {"column": "MFR", "to": "psets.valve_data.manufacturer"},
                {"column": "WITNESS", "to": "psets.valve_data.x.fat_witness_by"},
            ],
        }
    )
)
HEADER = "TAG NO,SERVICE,CLASS,SIZE,MFR,WITNESS\n"
FILE = HEADER + (
    "47-FV-1001,Feed gas,CV,4,Acme,Jo\n"
    "47-FV-1002,Fuel gas,CV,6,,\n"
    "10-PT-0001,Pressure,,,,\n"
    "LEGACY-1,Old line,MV,,,\n"
)


@pytest.fixture
def ledger(db: DbTarget) -> DbTarget:
    seed_registry(db)
    return db


def plan_of(db: DbTarget, text_: str) -> ImportPlan:
    with open_uow(db, readonly=True) as uow:
        return plan_import(read_rows(text_, MAPPING), existing_tags(uow.conn(), SCOPE))


def apply(db: DbTarget, text_: str, **more: Any) -> Any:
    plan = plan_of(db, text_)
    with open_uow(db) as uow:
        return apply_plan(
            uow, SCOPE, plan, actor="user:u", source="import:J1", reason="import J1", **more
        )


def tag(db: DbTarget, number: str) -> registry.TagRow:
    with open_uow(db, readonly=True) as uow:
        found = registry.find_tag(uow.conn(), SCOPE, number)
    assert found is not None
    return found


def scalar(db: DbTarget, sql: str, **params: Any) -> Any:
    with open_uow(db, readonly=True) as uow:
        return uow.conn().execute(text(sql), params).scalar_one()


def test_new_rows_become_tags_with_their_values_and_origin(ledger: DbTarget) -> None:
    result = apply(ledger, FILE)
    assert (result.created, result.changed, result.unchanged) == (4, 0, 0)
    valve = tag(ledger, "47-FV-1001")
    assert (valve.class_code, valve.title, valve.origin) == ("ControlValve", "Feed gas", "import")
    assert valve.number_status == "ok" and valve.segments["seq"] == "1001"
    assert valve.psets["valve_data"]["size_in"] == 4
    assert valve.psets["valve_data"]["x"] == {"fat_witness_by": "Jo"}
    assert tag(ledger, "10-PT-0001").class_code is None


def test_a_legacy_number_is_kept_as_a_violation(ledger: DbTarget) -> None:
    apply(ledger, FILE)
    legacy = tag(ledger, "LEGACY-1")
    assert legacy.number_status == "violation" and legacy.violations
    assert legacy.class_code == "ManualValve"


def test_every_event_of_an_import_has_its_source_and_one_correlation_id(
    ledger: DbTarget,
) -> None:
    last = scalar(ledger, "SELECT MAX(seq) FROM events")
    result = apply(ledger, FILE)
    where = "FROM events WHERE seq > :last"
    assert scalar(ledger, f"SELECT COUNT(DISTINCT correlation_id) {where}", last=last) == 1
    assert scalar(ledger, f"SELECT COUNT(DISTINCT source) {where}", last=last) == 1
    assert scalar(ledger, f"SELECT MIN(source) {where}", last=last) == "import:J1"
    assert scalar(ledger, f"SELECT MIN(correlation_id) {where}", last=last) == result.correlation_id


def test_changed_rows_update_class_title_and_values_and_the_rest_is_left_alone(
    ledger: DbTarget,
) -> None:
    apply(ledger, FILE)
    again = FILE.replace(
        "47-FV-1001,Feed gas,CV,4,Acme,Jo", "47-FV-1001,Feed gas to flare,MV,8,Acme,Sam"
    )
    again = again.replace("47-FV-1002,Fuel gas,CV,6,,\n", "")  # removed from the file
    result = apply(ledger, again)
    assert (result.created, result.changed, result.unchanged, result.not_in_file) == (0, 1, 2, 1)
    valve = tag(ledger, "47-FV-1001")
    assert (valve.class_code, valve.title) == ("ManualValve", "Feed gas to flare")
    assert valve.psets["valve_data"]["size_in"] == 8
    assert valve.psets["valve_data"]["x"] == {"fat_witness_by": "Sam"}
    assert valve.psets["valve_data"]["manufacturer"] == "Acme"
    assert tag(ledger, "47-FV-1002").status != "Deleted"  # not in the file: untouched


def test_importing_the_same_file_twice_finds_nothing_to_do(ledger: DbTarget) -> None:
    apply(ledger, FILE)
    plan = plan_of(ledger, FILE)
    assert plan.counts() == {"new": 0, "changed": 0, "unchanged": 4, "removed": 0, "invalid": 0}


def test_invalid_rows_stop_the_import_unless_they_are_skipped(ledger: DbTarget) -> None:
    broken = FILE + ",No number,CV,,,\n47-FV-1003,Bad size,CV,wide,,\n"
    with pytest.raises(ImportApplyError) as caught:
        apply(ledger, broken)
    assert caught.value.problems == [
        "line 6: the tag number is blank",
        "line 7: " + plan_of(ledger, broken).invalid[1].problems[0],
    ]
    assert scalar(ledger, "SELECT COUNT(*) FROM cur_engineering_tag") == 0
    result = apply(ledger, broken, skip_invalid=True)
    assert (result.created, result.skipped) == (4, 2)
    assert scalar(ledger, "SELECT COUNT(*) FROM cur_engineering_tag") == 4


def test_a_row_the_tag_commands_refuse_names_its_line_and_nothing_is_written(
    ledger: DbTarget,
) -> None:
    bad = HEADER + "47-FV-1001,Feed gas,CV,4,Acme,\n47-FV-1002,Fuel gas,XX,6,,\n"
    plan = plan_of(ledger, bad)
    with pytest.raises(ImportApplyError, match=r"^line 3 \(47-FV-1002\): .*NoSuchClass"):
        with open_uow(ledger) as uow:
            apply_plan(uow, SCOPE, plan, actor="user:u", source="import:J1", reason="r")
    assert scalar(ledger, "SELECT COUNT(*) FROM cur_engineering_tag") == 0


def test_existing_tags_leave_out_tags_that_were_superseded(ledger: DbTarget) -> None:
    apply(ledger, FILE)
    old = tag(ledger, "47-FV-1001")
    with open_uow(ledger) as uow:
        handle_rename_tag(
            uow,
            RenameTag(
                actor="user:u",
                source="test",
                scope=SCOPE,
                stream_id=old.id,
                new_number="47-FV-1009",
                reason="renumbered",
            ),
        )
    with open_uow(ledger, readonly=True) as uow:
        numbers = [t.number for t in existing_tags(uow.conn(), SCOPE)]
    assert numbers == sorted(numbers)
    assert "47-FV-1009" in numbers and "47-FV-1001" not in numbers
