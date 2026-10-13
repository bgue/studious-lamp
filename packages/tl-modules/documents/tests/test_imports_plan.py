"""Planning an import of the DMS register against a project's documents (P1-I2-T12c)."""

from __future__ import annotations

from pathlib import Path

from docworld import World
from tl_adapters.db import open_uow
from tl_mod_documents.imports.diff import plan_import
from tl_mod_documents.imports.mapping import load_mapping, read_rows
from tl_mod_documents.imports.model import ImportPlan, ImportRow
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.loader import load_standards

ROOT = Path(__file__).resolve().parents[4]
STANDARDS = ROOT / "schema" / "fixtures" / "standards"
TEMPLATE = ROOT / "dev" / "seed" / "templates" / "document-register-dms-export.yaml"
SAMPLE = ROOT / "dev" / "seed" / "legacy" / "dms-document-register.csv"
SCOPE = "project:P123"


def load_registry(world: World) -> None:
    for name in ("co.acme.standards@1.0.0.yaml", "co.acme.documents@1.0.0.yaml"):
        with open_uow(world.db) as uow:
            load_standards(
                uow, load_standards_file(STANDARDS / name), actor="user:admin", source="test"
            )


def sample() -> list[ImportRow]:
    return read_rows(SAMPLE.read_text(encoding="utf-8"), load_mapping(TEMPLATE))


def plan(world: World, rows: list[ImportRow] | None = None, scope: str = SCOPE) -> ImportPlan:
    with open_uow(world.db, readonly=True) as uow:
        return plan_import(uow.conn(), scope, sample() if rows is None else rows)


def test_the_sample_file_plans_nine_new_documents_and_seven_that_cannot_be_imported(
    world: World,
) -> None:
    load_registry(world)
    found = plan(world)
    assert found.counts() == {"new": 9, "exists": 0, "invalid": 7}
    assert [r.number for r in found.new] == [
        "ISO-0101", "ISO-0102", "PID-0001", "PID-0002", "DS-0010", "DS-0011", "LD-0020",
        "SPC-0003", "CAL-0007",
    ]  # fmt: skip
    assert [r.line for r in found.invalid] == [11, 12, 13, 14, 15, 16, 17]


def test_the_reasons_are_the_files_and_the_registrys(world: World) -> None:
    load_registry(world)
    why = {r.line: r.problems for r in plan(world).invalid}
    assert why[11] == ["the number appears again; first on line 2"]
    assert len(why[12]) == 1 and why[12][0].startswith("number 'ISO-12': ")
    assert len(why[13]) == 1 and why[13][0].startswith("number 'XYZ-0001': ")
    assert why[14] == ["DISCIPLINE: 'WELDING' is not one of the mapped values"]
    assert why[15] == ["the document number is blank"]
    assert why[16] == ["the title is blank"]
    assert why[17] == ["STATUS: 'UNDER REVIEW' is not one of the mapped values"]


def test_a_number_the_project_already_has_is_listed_once_and_not_planned_again(
    world: World,
) -> None:
    load_registry(world)
    world.register("ISO-0102")
    world.register("PID-0001", doc_type="PID")
    found = plan(world)
    assert found.counts() == {"new": 7, "exists": 2, "invalid": 7}
    assert found.exists == ["ISO-0102", "PID-0001"]
    assert "ISO-0102" not in [r.number for r in found.new]


def test_another_project_does_not_see_the_documents_of_this_one(world: World) -> None:
    load_registry(world)
    world.register("ISO-0102")
    assert plan(world, scope="project:P999").counts() == {"new": 9, "exists": 0, "invalid": 7}


def test_without_the_registry_only_the_files_own_rules_apply(world: World) -> None:
    found = plan(world)  # no standards loaded: no pattern, no code lists
    assert found.counts() == {"new": 11, "exists": 0, "invalid": 5}
    assert sorted(r.line for r in found.invalid) == [11, 14, 15, 16, 17]
    assert {12, 13} <= {r.line for r in found.new}


def test_a_number_with_a_reserved_character_is_refused(world: World) -> None:
    rows = [r for r in sample() if r.line == 2]
    odd = ImportRow(
        line=2,
        number="ISO-0101@B",
        title="x",
        doc_type="ISO",
        discipline="PIP",
        originator=None,
        legacy_revision=None,
        legacy_status=None,
        legacy_date=None,
    )
    found = plan(world, [*rows, odd])
    assert [r.number for r in found.invalid] == ["ISO-0101@B"] or found.invalid[0].problems
    assert any("'@'" in p for r in found.invalid for p in r.problems)


def test_an_empty_file_plans_nothing(world: World) -> None:
    assert plan(world, []).counts() == {"new": 0, "exists": 0, "invalid": 0}
