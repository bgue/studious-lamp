"""JSON Schema projection of form answers (P2-FORMS T01; ADR-0031).

The property test is the agreement check: for each field of each fixture template, the projected
schema accepts a one-answer list exactly when ``validate_answers`` returns no problem.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from tl_core.forms.jsonschema import to_json_schema
from tl_core.forms.rules import validate_answers

REPO = Path(__file__).resolve().parents[3]
TEMPLATES = REPO / "schema" / "fixtures" / "forms" / "templates"
FIXTURES: list[Path] = sorted(TEMPLATES.rglob("*.yaml"))
ULID = "01HZX3K9Q7M2N4P5R6S8T0V1WA"


def _load(path: Path) -> tuple[list[dict[str, Any]], int]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    fields: list[dict[str, Any]] = data["fields"]
    return fields, int(data["format_version"])


def _reversed(field: dict[str, Any]) -> dict[str, Any]:
    return dict(reversed(list(field.items())))


def _f(fid: str, kind: str, **kw: Any) -> dict[str, Any]:
    """A question with the nine format 1 keys; keyword arguments override or add keys."""
    base: dict[str, Any] = {
        "id": fid,
        "text": f"field {fid}",
        "kind": kind,
        "required": True,
        "unit": None,
        "min": None,
        "max": None,
        "choices": None,
        "fails_when": None,
    }
    base.update(kw)
    return base


def _samples(field: dict[str, Any]) -> list[Any]:
    kind = field["kind"]
    if kind == "yes_no_na":
        return ["yes", "maybe"]
    if kind == "number":
        return [3, 2.5, "3", True]
    if kind == "text":
        return ["x", 5, "x" * 1001]
    if kind == "choice":
        return [field["choices"][0], "zzz"]
    if kind == "multi":
        first = field["choices"][0]
        return [[first], ["zzz"], [first, first], []]
    if kind == "date":
        return ["2026-02-03", "2026-13-40"]
    if kind == "photo":
        return [[ULID], [], [ULID, ULID], ["short"]]
    raise AssertionError(f"no samples for kind {kind!r}")


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_projects_to_a_valid_schema_independent_of_key_order(path: Path) -> None:
    fields, fmt = _load(path)
    schema = to_json_schema(fields, fmt)
    Draft202012Validator.check_schema(schema)
    reordered = to_json_schema([_reversed(f) for f in fields], fmt)
    assert json.dumps(schema, sort_keys=True) == json.dumps(reordered, sort_keys=True)


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_schema_agrees_with_validate_answers_for_every_field(path: Path) -> None:
    fields, fmt = _load(path)
    mismatches: list[str] = []
    checked = 0
    for field in fields:
        bare = copy.deepcopy(field)
        bare.pop("visible_when", None)
        schema = to_json_schema([bare], fmt)
        validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
        for value in _samples(bare):
            for note in (None, "n" * 301):
                answer = {"q": bare["id"], "value": value, "note": note}
                by_schema = validator.is_valid([answer])
                by_rules = validate_answers([bare], [answer], fmt=fmt, partial=True) == []
                checked += 1
                if by_schema != by_rules:
                    mismatches.append(f"{bare['id']} value={value!r} note-len={len(note or '')}")
    assert checked > 0
    assert mismatches == []


def test_format_1_fields_project_without_section_keys() -> None:
    fields = [
        _f("q1", "yes_no_na", fails_when="no"),
        _f("q2", "number", min=0, max=9, fails_when="out_of_range", unit="bar"),
    ]
    schema = to_json_schema(fields, 1)
    Draft202012Validator.check_schema(schema)
    assert "x-section" not in json.dumps(schema)
    assert "x-help" not in json.dumps(schema)
    assert "x-visible-when" not in json.dumps(schema)


def test_unknown_format_is_refused() -> None:
    with pytest.raises(ValueError):
        to_json_schema([_f("q1", "yes_no_na")], 3)


def test_bad_kind_is_refused() -> None:
    with pytest.raises(ValueError):
        to_json_schema([_f("q1", "signature")], 1)


def test_answer_for_unknown_question_is_refused() -> None:
    validator = Draft202012Validator(
        to_json_schema([_f("q1", "yes_no_na")], 1),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    assert validator.is_valid([{"q": "q1", "value": "yes", "note": None}])
    assert not validator.is_valid([{"q": "q9", "value": "yes", "note": None}])


def test_answer_with_extra_key_is_refused() -> None:
    validator = Draft202012Validator(
        to_json_schema([_f("q1", "yes_no_na")], 1),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    assert not validator.is_valid([{"q": "q1", "value": "yes", "note": None, "extra": 1}])
