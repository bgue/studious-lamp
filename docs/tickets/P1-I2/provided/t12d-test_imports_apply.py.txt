"""Applying an import plan of the DMS register (P1-I2-T12d)."""

from __future__ import annotations

from pathlib import Path

import pytest
from docworld import World
from tl_adapters.db import open_uow
from tl_core.services.errors import DuplicateKeyError
from tl_mod_documents.imports.apply import ImportRefusedError, apply_plan
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


@pytest.fixture
def loaded(world: World) -> World:
    for name in ("co.acme.standards@1.0.0.yaml", "co.acme.documents@1.0.0.yaml"):
        with open_uow(world.db) as uow:
            load_standards(
                uow, load_standards_file(STANDARDS / name), actor="user:admin", source="test"
            )
    return world


def planned(world: World) -> ImportPlan:
    rows = read_rows(SAMPLE.read_text(encoding="utf-8"), load_mapping(TEMPLATE))
    with open_uow(world.db, readonly=True) as uow:
        return plan_import(uow.conn(), SCOPE, rows)


def apply(world: World, plan: ImportPlan, **more: object) -> list[object]:
    with open_uow(world.db) as uow:
        return list(
            apply_plan(uow, SCOPE, plan, actor="user:admin", job="dms-2024", **more)  # type: ignore[arg-type]
        )


def test_a_plan_with_invalid_rows_is_refused_and_nothing_is_written(loaded: World) -> None:
    with pytest.raises(ImportRefusedError, match=r"7 row\(s\) cannot be imported"):
        apply(loaded, planned(loaded))
    assert loaded.scalar("SELECT COUNT(*) FROM cur_documents_document") == 0


def test_skip_invalid_registers_the_valid_rows_with_the_legacy_note(loaded: World) -> None:
    results = apply(loaded, planned(loaded), skip_invalid=True)
    assert len(results) == 9
    assert [d.number for d in map(loaded.document, ["ISO-0101", "CAL-0007"])] == [
        "ISO-0101",
        "CAL-0007",
    ]
    first = loaded.document("ISO-0101")
    assert (first.state, first.title, first.doc_type, first.discipline) == (
        "Registered",
        "Isometric, line 47-P-101",
        "ISO",
        "PIP",
    )
    assert first.originator == "Acme Piping"
    assert first.description == "Legacy register: revision C, status IFC, dated 2024-02-12"
    assert loaded.scalar("SELECT COUNT(*) FROM cur_documents_document") == 9
    assert loaded.scalar("SELECT COUNT(*) FROM cur_documents_revision") == 0  # documents only


def test_the_history_says_where_each_document_came_from(loaded: World) -> None:
    apply(loaded, planned(loaded), skip_invalid=True)
    sources = {
        r["source"]
        for r in loaded.rows(
            "SELECT DISTINCT source FROM events WHERE stream_type = 'documents.Document'"
        )
    }
    assert sources == {"import:dms-2024"}


def test_a_second_run_registers_nothing_new(loaded: World) -> None:
    apply(loaded, planned(loaded), skip_invalid=True)
    again = planned(loaded)
    assert again.counts() == {"new": 0, "exists": 9, "invalid": 7}
    assert apply(loaded, again, skip_invalid=True) == []


def test_a_failure_part_way_leaves_nothing_registered(loaded: World) -> None:
    plan = planned(loaded)
    plan.new.append(plan.new[0])  # the same number twice: the second registration is refused
    with pytest.raises(DuplicateKeyError):
        apply(loaded, plan, skip_invalid=True)
    assert loaded.scalar("SELECT COUNT(*) FROM cur_documents_document") == 0


def test_the_job_name_is_checked_before_anything_is_written(loaded: World) -> None:
    for job in ("", "a b", "x" * 65, "../etc"):
        with open_uow(loaded.db) as uow, pytest.raises(ImportRefusedError, match="job name"):
            apply_plan(uow, SCOPE, ImportPlan(), actor="user:admin", job=job)


def test_an_empty_plan_registers_nothing(loaded: World) -> None:
    row = ImportRow(
        line=2, number="", title=None, doc_type=None, discipline=None, originator=None,
        legacy_revision=None, legacy_status=None, legacy_date=None,
    )  # fmt: skip
    assert apply(loaded, ImportPlan(invalid=[row]), skip_invalid=True) == []
