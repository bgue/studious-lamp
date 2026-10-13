"""The DMS register mapping template and its sample file (P1-I2-T12b)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_mod_documents.imports.mapping import (
    MappingError,
    load_mapping,
    parse_mapping,
    read_rows,
)

ROOT = Path(__file__).resolve().parents[4]
TEMPLATE = ROOT / "dev" / "seed" / "templates" / "document-register-dms-export.yaml"
SAMPLE = ROOT / "dev" / "seed" / "legacy" / "dms-document-register.csv"

SMALL = """\
name: small
description: a small template
columns:
  - {column: DOC, to: number}
  - {column: NAME, to: title}
  - column: KIND
    to: type
    values: {DRAWING: DRW}
"""


def test_the_template_of_the_dms_export_parses() -> None:
    template = load_mapping(TEMPLATE)
    assert template.name == "dms-document-register" and template.delimiter == ","
    assert [c.to for c in template.columns] == [
        "number", "title", "type", "discipline", "originator", "revision", "status", "date"
    ]  # fmt: skip
    assert "FILE PATH" in template.ignore and template.columns[2].values["P&ID"] == "PID"


def test_the_sample_file_reads_with_the_template() -> None:
    rows = read_rows(SAMPLE.read_text(encoding="utf-8"), load_mapping(TEMPLATE))
    assert len(rows) == 16
    first = rows[0]
    assert first.line == 2 and first.problems == []
    assert (first.number, first.title, first.doc_type, first.discipline) == (
        "ISO-0101",
        "Isometric, line 47-P-101",
        "ISO",
        "PIP",
    )
    assert (first.originator, first.legacy_revision, first.legacy_status, first.legacy_date) == (
        "Acme Piping",
        "C",
        "IFC",
        "2024-02-12",
    )
    assert first.note == "Legacy register: revision C, status IFC, dated 2024-02-12"
    assert first.raw["CHECKED BY"] == "R. Singh" and first.raw["FILE PATH"].endswith(
        "ISO-0101_C.pdf"
    )


def test_a_row_that_cannot_be_read_carries_its_problems_and_the_file_goes_on() -> None:
    rows = {
        r.line: r for r in read_rows(SAMPLE.read_text(encoding="utf-8"), load_mapping(TEMPLATE))
    }
    assert rows[14].discipline is None and rows[14].problems == [
        "DISCIPLINE: 'WELDING' is not one of the mapped values"
    ]
    assert rows[15].number == "" and rows[15].problems == ["the document number is blank"]
    assert rows[17].legacy_status is None and rows[17].problems == [
        "STATUS: 'UNDER REVIEW' is not one of the mapped values"
    ]
    assert rows[16].title is None and rows[16].problems == []  # a blank title is the plan's finding
    assert rows[11].number == "ISO-0101"  # a repeated number is also the plan's finding
    assert (rows[4].legacy_revision, rows[8].legacy_revision) == ("D", "0")


def test_a_note_names_only_what_the_legacy_row_has() -> None:
    rows = {
        r.line: r for r in read_rows(SAMPLE.read_text(encoding="utf-8"), load_mapping(TEMPLATE))
    }
    assert rows[7].note == "Legacy register: revision 1, status IFR, dated 2024-03-05"
    template = parse_mapping(SMALL)
    (row,) = read_rows("DOC,NAME,KIND\nDRW-0001,Plan,\n", template)
    assert row.note is None and row.doc_type is None and row.title == "Plan"


def test_a_file_with_a_bom_blank_lines_and_a_short_row_still_reads() -> None:
    template = parse_mapping(SMALL)
    text = "﻿DOC,NAME,KIND\n\nDRW-0001,Plan,DRAWING\nDRW-0002\n"
    rows = read_rows(text, template)
    assert [(r.line, r.number, r.title, r.doc_type) for r in rows] == [
        (3, "DRW-0001", "Plan", "DRW"),
        (4, "DRW-0002", None, None),
    ]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "the file has no header row"),
        ("DOC,DOC,NAME,KIND\nx,x,y,DRAWING\n", "the file has a column twice: DOC"),
        ("DOC,KIND\nx,DRAWING\n", r"the file lacks the column\(s\): NAME"),
        ('DOC,NAME,KIND\n"x,y,DRAWING\n', "the file is not readable as CSV"),
    ],
)
def test_a_file_that_cannot_be_read_is_a_mapping_error(text: str, message: str) -> None:
    with pytest.raises(MappingError, match=message):
        read_rows(text, parse_mapping(SMALL))


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (":\n  - [", "invalid YAML"),
        ("- a\n- b\n", "a mapping template must be a YAML mapping"),
        (SMALL.replace("to: number", "to: tag"), "columns.0.to"),
        (SMALL.replace("{column: NAME, to: title}", "{column: DOC, to: title}"), "mapped twice"),
        (SMALL + "  - {column: ALT, to: title}\n", "two columns map to title"),
        (
            SMALL.replace("{column: DOC, to: number}", "{column: DOC, to: title}"),
            "exactly one column",
        ),
        (SMALL.replace("to: title}", "to: title, values: {a: b}}"), "title cannot have values"),
        (SMALL + "ignore: [DOC]\n", "both mapped and ignored"),
        (SMALL + 'delimiter: "ab"\n', "delimiter must be one character"),
    ],
)
def test_a_template_that_does_not_validate_is_a_mapping_error(text: str, message: str) -> None:
    with pytest.raises(MappingError, match=message) as caught:
        parse_mapping(text, source="t.yaml")
    assert str(caught.value).startswith("t.yaml: ")


def test_a_template_file_that_is_missing_is_a_mapping_error(tmp_path: Path) -> None:
    with pytest.raises(MappingError, match="cannot read file"):
        load_mapping(tmp_path / "nope.yaml")
