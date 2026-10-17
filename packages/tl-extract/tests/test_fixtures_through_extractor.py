"""The document schema fixtures, read by the tabular extractor and validated (P1-I3B-T13).

This is the demo path of P1-I3 up to the publish: the sample file extracts to 40 rows that all pass
the schema, the invalid variant fails on exactly one row and the cell that is wrong is named.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from extractsupport import run
from jsonschema import Draft202012Validator
from tl_core.derivation import Cell, ExtractionResult
from tl_extract.tabular import TabularExtractor

FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "document-schemas"
EXTRACTOR = TabularExtractor()


def extract(name: str, options: Mapping[str, object] | None = None) -> ExtractionResult:
    return run(EXTRACTOR, name, "text/csv", (FIXTURES / name).read_bytes(), options)


def validate(code: str, rows: list[dict[str, Cell]]) -> dict[int, list[str]]:
    schema: dict[str, Any] = json.loads((FIXTURES / f"{code}@1.0.0.schema.json").read_text())
    validator = Draft202012Validator(schema)
    bad: dict[int, list[str]] = {}
    for number, row in enumerate(rows, start=1):
        present = {k: v for k, v in row.items() if v is not None}
        errors = [
            ".".join(str(p) for p in e.path) or e.validator for e in validator.iter_errors(present)
        ]
        if errors:
            bad[number] = sorted(str(e) for e in errors)
    return bad


@pytest.mark.parametrize(
    ("code", "count"), [("instrument-index", 40), ("line-list", 10), ("equipment-list", 10)]
)
def test_each_sample_extracts_and_passes_its_schema(code: str, count: int) -> None:
    schema = json.loads((FIXTURES / f"{code}@1.0.0.schema.json").read_text())
    result = extract(f"{code}@1.0.0.sample.csv")
    assert result.status == "ok" and result.problems == []
    assert result.columns == list(schema["properties"])
    assert len(result.rows) == count
    assert validate(code, result.rows) == {}


def test_the_invalid_variant_fails_on_exactly_one_row_and_names_the_field() -> None:
    result = extract("instrument-index@1.0.0.invalid.csv")
    assert result.status == "ok" and len(result.rows) == 40
    assert validate("instrument-index", result.rows) == {6: ["fail_action"]}
    assert result.rows[5]["tag_number"] == "47-XV-1006"


def test_a_persons_headers_are_mapped_to_the_schemas_names_by_the_aliases() -> None:
    schema = json.loads((FIXTURES / "instrument-index@1.0.0.schema.json").read_text())
    aliases = schema["x-throughline"]["header_aliases"]
    header_map = {alias: prop for prop, names in aliases.items() for alias in names}
    legacy = (
        "TAG NO,Service,Class,SIZE (IN),MATERIAL,MFR,FAIL,REMARKS\n"
        "47-FV-1001,Feed gas,ControlValve,4,SS316L,Acme Valves,FC,\n"
    )
    result = run(EXTRACTOR, "legacy.csv", "text/csv", legacy.encode(), {"header_map": header_map})
    assert result.columns == [
        "tag_number",
        "service",
        "tag_class",
        "size_in",
        "body_material",
        "manufacturer",
        "fail_action",
        "remarks",
    ]
    assert validate("instrument-index", result.rows) == {}
