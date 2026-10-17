"""The document schema fixtures (P1-I3B-T13): valid schemas, samples that pass, one that fails."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "schema" / "fixtures" / "document-schemas"
STANDARDS = ROOT / "schema" / "fixtures" / "standards" / "co.acme.standards@1.0.0.yaml"
CODES = ["instrument-index", "line-list", "equipment-list"]


def schema_of(code: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{code}@1.0.0.schema.json").read_text(encoding="utf-8"))


def rows_of(name: str) -> list[dict[str, str]]:
    """The rows of a sample as the pipeline hands them to validation: empty cells left out."""
    with (FIXTURES / name).open(newline="", encoding="utf-8") as handle:
        return [{k: v for k, v in row.items() if v != ""} for row in csv.DictReader(handle)]


def header_of(name: str) -> list[str]:
    with (FIXTURES / name).open(newline="", encoding="utf-8") as handle:
        return next(csv.reader(handle))


def failing_rows(code: str, name: str) -> dict[int, list[str]]:
    validator = Draft202012Validator(schema_of(code))
    found: dict[int, list[str]] = {}
    for number, row in enumerate(rows_of(name), start=1):
        errors = sorted(validator.iter_errors(row), key=lambda e: list(e.path))
        if errors:
            found[number] = [".".join(str(p) for p in e.path) or e.validator for e in errors]  # type: ignore[misc]
    return found


@pytest.mark.parametrize("code", CODES)
def test_the_schema_is_a_valid_json_schema_with_its_identity(code: str) -> None:
    schema = schema_of(code)
    Draft202012Validator.check_schema(schema)
    block = schema["x-throughline"]
    assert (block["code"], block["version"]) == (code, "1.0.0")
    assert schema["$id"] == f"urn:throughline:document-schema:{code}:1.0.0"
    assert schema["type"] == "object" and schema["additionalProperties"] is False
    assert (FIXTURES / block["sample"]).is_file()


@pytest.mark.parametrize("code", CODES)
def test_every_property_is_text_so_a_row_validates_as_extracted(code: str) -> None:
    for name, prop in schema_of(code)["properties"].items():
        assert prop["type"] == "string", name
        if prop.get("x-tl-type") == "decimal":
            assert "pattern" in prop, name


@pytest.mark.parametrize("code", CODES)
def test_the_sample_uses_the_schemas_property_names_and_passes(code: str) -> None:
    schema = schema_of(code)
    assert header_of(f"{code}@1.0.0.sample.csv") == list(schema["properties"])
    assert failing_rows(code, f"{code}@1.0.0.sample.csv") == {}


@pytest.mark.parametrize("code", CODES)
def test_the_unique_keys_and_the_aliases_name_real_properties(code: str) -> None:
    schema = schema_of(code)
    block = schema["x-throughline"]
    properties = set(schema["properties"])
    assert set(block["unique"]) <= properties
    assert set(block["header_aliases"]) <= properties
    target = block["target"]
    if target is not None:
        assert {target["key"], target["title"], target["class"]} <= properties
    for key in block["unique"]:
        values = [row[key] for row in rows_of(f"{code}@1.0.0.sample.csv")]
        assert len(values) == len(set(values)), key


@pytest.mark.parametrize("code", CODES)
def test_an_alias_is_not_claimed_by_two_properties(code: str) -> None:
    seen: dict[str, str] = {}
    for prop, aliases in schema_of(code)["x-throughline"]["header_aliases"].items():
        for alias in aliases:
            key = re.sub(r"[\W_]+", "_", alias.lower()).strip("_")
            assert seen.setdefault(key, prop) == prop, alias


def test_the_instrument_index_sample_is_the_forty_tag_demo() -> None:
    rows = rows_of("instrument-index@1.0.0.sample.csv")
    assert len(rows) == 40
    assert {r["area"] for r in rows} == {"47", "10", "20"}
    assert len({r["tag_class"] for r in rows}) == 10  # every class of the schema is used


def test_the_instrument_index_numbers_class_and_area_fit_the_acme_standards() -> None:
    standards = yaml.safe_load(STANDARDS.read_text(encoding="utf-8"))
    areas = {v["code"] for v in standards["code_lists"]["Area"]["values"]}
    mnemonics = {m["code"] for m in standards["mnemonics"]}
    class_of = {m: c["code"] for c in standards["tag_classes"] for m in c["mnemonics"]}
    template = re.compile(r"^(?P<area>[0-9]+)-(?P<mnemonic>[A-Z]+)-(?P<seq>[0-9]{4})$")
    for name in ("instrument-index", "equipment-list"):
        key, kind = (
            ("tag_number", "tag_class")
            if name == "instrument-index"
            else (
                "equipment_tag",
                "equipment_class",
            )
        )
        for row in rows_of(f"{name}@1.0.0.sample.csv"):
            found = template.match(row[key])
            assert found is not None, row[key]
            assert found["area"] in areas and found["area"] == row["area"], row[key]
            assert found["mnemonic"] in mnemonics, row[key]
            assert class_of[found["mnemonic"]] == row[kind], row[key]


def test_the_invalid_variant_fails_on_exactly_one_row_in_one_field() -> None:
    good = rows_of("instrument-index@1.0.0.sample.csv")
    bad = rows_of("instrument-index@1.0.0.invalid.csv")
    assert len(bad) == 40
    changed = [n for n, (a, b) in enumerate(zip(good, bad, strict=True), start=1) if a != b]
    assert changed == [6]
    assert failing_rows("instrument-index", "instrument-index@1.0.0.invalid.csv") == {
        6: ["fail_action"]
    }
    assert bad[5]["tag_number"] == "47-XV-1006" and bad[5]["fail_action"] == "OPEN"


@pytest.mark.parametrize(
    ("row", "field"),
    [
        ({"tag_number": "47-FV-001", "tag_class": "ControlValve", "service": "x"}, "tag_number"),
        ({"tag_number": "47-FV-1001", "tag_class": "Valve", "service": "x"}, "tag_class"),
        ({"tag_number": "47-FV-1001", "tag_class": "ControlValve"}, "required"),
        (
            {"tag_number": "47-FV-1001", "tag_class": "ControlValve", "service": "x", "size": "4"},
            "additionalProperties",
        ),
        (
            {
                "tag_number": "47-FV-1001",
                "tag_class": "ControlValve",
                "service": "x",
                "size_in": "4 in",
            },
            "size_in",
        ),
        (
            {"tag_number": "47-FV-1001", "tag_class": "ControlValve", "service": "x", "area": "7"},
            "area",
        ),
    ],
)
def test_the_instrument_index_schema_refuses_these_rows(row: dict[str, str], field: str) -> None:
    errors = list(Draft202012Validator(schema_of("instrument-index")).iter_errors(row))
    assert len(errors) == 1
    assert (".".join(str(p) for p in errors[0].path) or errors[0].validator) == field


def test_a_row_with_only_the_required_columns_passes() -> None:
    row = {"tag_number": "47-FV-1001", "tag_class": "ControlValve", "service": "Feed"}
    assert not list(Draft202012Validator(schema_of("instrument-index")).iter_errors(row))
