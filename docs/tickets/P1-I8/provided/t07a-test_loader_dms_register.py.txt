"""The loader `dms-register`: the document register of the incumbent DMS (P1-I8-T07a).

Provided; do not edit.
"""

from __future__ import annotations

import csv
from importlib.metadata import entry_points

from tl_mod_documents.imports import mapping as documents_mapping
from tl_mod_legacy.loaders.dms_register import loader
from tl_mod_legacy.model import use_loaders
from tl_mod_legacy.targets import comma_mapping_text
from tl_mod_legacy.testing import ADMIN, DOC_FILE, PROJECT, LegacyWorld

DATA = DOC_FILE.read_bytes()


def test_the_loader_describes_what_it_reads_and_writes() -> None:
    found = loader()
    assert (found.name, found.system, found.table, found.target) == (
        "dms-register",
        "dms",
        "register",
        "documents",
    )
    assert found.file_types == ("csv", "xlsx")
    assert found.confidentiality is None and found.sheet is None and found.header_row == 1
    assert found.description.endswith("(CSV or XLSX).")


def test_the_mapping_is_the_document_register_template_of_the_seed() -> None:
    mapping = documents_mapping.parse_mapping(comma_mapping_text(loader()), source="dms-register")
    assert mapping.name == "dms-register"
    assert [c.column for c in mapping.columns] == [
        "DOC NO",
        "TITLE",
        "DOC TYPE",
        "DISCIPLINE",
        "ORIGINATOR",
        "REV",
        "STATUS",
        "REV DATE",
    ]
    assert mapping.ignore == ["FILE PATH", "CHECKED BY", "REMARKS"]
    rows = documents_mapping.read_rows(DOC_FILE.read_text(encoding="utf-8"), mapping)
    assert len(rows) == 16 and rows[0].number == "ISO-0101" and rows[0].doc_type == "ISO"
    assert rows[0].discipline == "PIP" and rows[0].legacy_status == "IFC"


def test_it_is_installed_under_its_name() -> None:
    found = {e.name: e for e in entry_points(group="throughline.loaders")}
    assert found["dms-register"].value == "tl_mod_legacy.loaders.dms_register:loader"
    assert found["dms-register"].load()() == loader()


def test_the_sample_register_loads_and_reconciles(world: LegacyWorld) -> None:
    with use_loaders({"dms-register": loader()}):
        run = world.through_plan("dms-register", "register.csv", DATA)
        assert (run.key, run.plan_new, run.plan_existing, run.plan_invalid) == (
            "dms/register#1",
            9,
            0,
            7,
        )
        outcome = world.service.load(PROJECT, run.key, actor=ADMIN)
        assert (outcome.created, outcome.skipped_invalid, outcome.source_layer_rows) == (9, 7, 9)
        done, report = world.service.reconcile(PROJECT, run.key, actor=ADMIN)
    assert done.state == "Reconciled" and done.mismatches == 0
    assert report["matched"] == 9 and report["invalid_rows"] == 7 and report["problems"] == []
    docs = {
        r["number"]: r
        for r in world.rows(
            "SELECT d.id, d.number, d.doc_type, d.discipline, d.originator, r.description "
            "FROM cur_documents_document d JOIN cur_core_record r ON r.id = d.id"
        )
    }
    assert len(docs) == 9 and docs["ISO-0101"]["doc_type"] == "ISO"
    assert docs["ISO-0101"]["discipline"] == "PIP" and docs["ISO-0101"]["originator"]
    assert "revision C" in docs["ISO-0101"]["description"]
    assert "status IFC" in docs["ISO-0101"]["description"]


def test_every_column_of_the_file_is_kept_in_the_source_layer(world: LegacyWorld) -> None:
    with use_loaders({"dms-register": loader()}):
        world.loaded("dms-register", "register.csv", DATA)
    first = world.rows(
        "SELECT d.id FROM cur_documents_document d WHERE d.number = :n", n="ISO-0101"
    )[0]["id"]
    values = world.rows(
        "SELECT pset, value_text FROM cur_pset_values WHERE record_id = :i AND layer = 'source'",
        i=first,
    )
    assert {v["pset"] for v in values} == {"src.legacy-dms.register"}
    assert len(values) >= 8
    flat = " ".join(v["value_text"] or "" for v in values)
    assert "R. Singh" in flat  # the CHECKED BY column, which the mapping ignores
    assert "ISO-0101_C.pdf" in flat  # the FILE PATH column, which the mapping ignores


def test_the_register_can_be_read_from_a_workbook_too(world: LegacyWorld) -> None:
    from io import BytesIO

    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for line in DOC_FILE.read_text(encoding="utf-8").splitlines():
        sheet.append(next(csv.reader([line])))
    buffer = BytesIO()
    book.save(buffer)
    with use_loaders({"dms-register": loader()}):
        run = world.through_plan("dms-register", "register.xlsx", buffer.getvalue())
    assert (run.plan_new, run.plan_invalid) == (9, 7)
