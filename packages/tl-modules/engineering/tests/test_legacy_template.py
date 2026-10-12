"""The legacy instrument-index template and its sample file, end to end (P1-I1-T12)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_adapters.db import DbTarget, open_uow
from tl_mod_engineering import registry
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.imports.apply import apply_plan, existing_tags
from tl_mod_engineering.imports.diff import plan_import
from tl_mod_engineering.imports.mapping import load_mapping, read_rows
from tl_mod_engineering.imports.model import ImportPlan
from tl_mod_engineering.loader import load_standards

pytestmark = pytest.mark.usefixtures("fixture_schemas")

ROOT = Path(__file__).resolve().parents[4]
TEMPLATE = ROOT / "dev" / "seed" / "templates" / "tag-list-instrument-index.yaml"
SAMPLE = ROOT / "dev" / "seed" / "legacy" / "instrument-index.csv"
ACME = ROOT / "schema" / "fixtures" / "standards" / "co.acme.standards@1.0.0.yaml"
SCOPE = "project:P123"


@pytest.fixture
def world(db: DbTarget) -> DbTarget:
    with open_uow(db) as uow:
        load_standards(uow, load_standards_file(ACME), actor="user:seed", source="test")
    return db


def plan(db: DbTarget) -> ImportPlan:
    rows = read_rows(SAMPLE.read_text(encoding="utf-8"), load_mapping(TEMPLATE))
    with open_uow(db, readonly=True) as uow:
        return plan_import(rows, existing_tags(uow.conn(), SCOPE))


def test_the_sample_file_reads_with_the_template() -> None:
    template = load_mapping(TEMPLATE)
    assert template.name == "instrument-index" and "P&ID" in template.ignore
    rows = read_rows(SAMPLE.read_text(encoding="utf-8"), template)
    assert len(rows) == 14
    first = rows[0]
    assert (first.number, first.class_code, first.service) == (
        "47-FV-1001",
        "ControlValve",
        "Feed gas flow control",
    )
    assert first.psets["valve_data"] == {
        "size_in": 4.0,
        "body_material": "SS316L",
        "manufacturer": "Acme Valves",
        "fail_action": "FC",
        "x.fat_witness_by": "J. Okafor",
    }


def test_the_plan_names_the_rows_that_cannot_be_imported(world: DbTarget) -> None:
    found = plan(world)
    assert found.counts() == {"new": 11, "changed": 0, "unchanged": 0, "removed": 0, "invalid": 3}
    problems = {row.line: row.problems for row in found.invalid}
    assert problems[12] == ["the tag number is blank"]
    assert problems[13] == ["duplicate of row 3"]
    assert "ZZ" in problems[14][0]


def test_applying_the_sample_makes_tags_and_keeps_the_legacy_number_as_a_violation(
    world: DbTarget,
) -> None:
    with open_uow(world) as uow:
        result = apply_plan(
            uow, SCOPE, plan(world), actor="user:dc", source="import:sample", reason="sample",
            skip_invalid=True,
        )  # fmt: skip
    assert (result.created, result.skipped) == (11, 3)
    with open_uow(world, readonly=True) as uow:
        tags = {t.number: t for t in registry.list_tags(uow.conn(), SCOPE)}
    assert len(tags) == 11
    assert tags["47-FV-1001"].number_status == "ok"
    assert tags["47-FV-1001"].psets["valve_data"]["x"] == {"fat_witness_by": "J. Okafor"}
    assert tags["FV1009"].number_status == "violation"
    assert tags["47-XX-1010"].number_status == "violation"
    assert tags["47-XX-1010"].class_code is None
    assert tags["47-FT-1006"].class_code == "Transmitter"


def test_a_second_import_of_the_sample_has_nothing_left_to_do(world: DbTarget) -> None:
    with open_uow(world) as uow:
        apply_plan(
            uow, SCOPE, plan(world), actor="user:dc", source="import:sample", reason="sample",
            skip_invalid=True,
        )  # fmt: skip
    again = plan(world)
    assert (again.counts()["new"], again.counts()["changed"], again.counts()["unchanged"]) == (
        0,
        0,
        11,
    )
