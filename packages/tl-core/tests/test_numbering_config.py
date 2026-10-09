"""Numbering configuration: patterns, scope selection, reserved ranges, and the shipped file."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from tl_core.numbering.config import (
    NumberingConfigError,
    NumberingPattern,
    NumberingRegistry,
    get_numbering,
    load_numbering,
    parse_numbering,
    use_numbering,
)

FIXTURE = (
    Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "numbering" / "patterns.yaml"
)


def pattern(**overrides: object) -> NumberingPattern:
    data: dict[str, object] = {
        "id": "p1",
        "record_type": "core.Record",
        "template": "{project}-{type}-{seq:4}",
        "type_code": "REC",
    }
    data.update(overrides)
    return NumberingPattern.model_validate(data)


def test_defaults_are_gap_free_and_apply_everywhere() -> None:
    p = pattern()
    assert p.gap_free is True
    assert p.scope == "*"
    assert p.reserved == []
    assert p.compiled().fields == ("project", "type")


@pytest.mark.parametrize(
    "overrides",
    [
        {"template": "{project}-{type}"},  # no sequence
        {"type_code": "R-1"},
        {"type_code": ""},
        {"scope": "tenant"},
        {"scope": "project:"},
        {"reserved": [(0, 5)]},
        {"reserved": [(9, 5)]},
        {"id": ""},
        {"colour": "red"},
    ],
)
def test_invalid_patterns_are_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        pattern(**overrides)


@pytest.mark.parametrize("scope", ["*", "project:*", "company", "project:P123"])
def test_valid_scope_selectors(scope: str) -> None:
    assert pattern(scope=scope).scope == scope


def test_scope_specificity() -> None:
    assert pattern(scope="project:P1").matches_scope("project:P1") == 3
    assert pattern(scope="project:*").matches_scope("project:P1") == 2
    assert pattern(scope="*").matches_scope("project:P1") == 1
    assert pattern(scope="project:*").matches_scope("company") == 0
    assert pattern(scope="project:P2").matches_scope("project:P1") == 0
    assert pattern(scope="company").matches_scope("company") == 3


def test_find_prefers_the_most_specific_pattern_and_the_record_type() -> None:
    anywhere = pattern(id="anywhere", scope="*")
    any_project = pattern(id="any-project", scope="project:*")
    exact = pattern(id="exact", scope="project:P1")
    other_type = pattern(id="other", record_type="core.Other", scope="project:P1")
    registry = NumberingRegistry([anywhere, any_project, exact, other_type])
    found = registry.find("project:P1", "core.Record")
    assert found is not None and found.id == "exact"
    found = registry.find("project:P2", "core.Record")
    assert found is not None and found.id == "any-project"
    found = registry.find("company", "core.Record")
    assert found is not None and found.id == "anywhere"
    assert registry.find("project:P1", "nothing.Here") is None
    assert NumberingRegistry().find("company", "core.Record") is None


def test_find_takes_the_first_registered_on_a_tie() -> None:
    first = pattern(id="first", scope="project:*")
    second = pattern(id="second", scope="project:*")
    found = NumberingRegistry([first, second]).find("project:P1", "core.Record")
    assert found is first


def test_for_scope_lists_every_applicable_pattern() -> None:
    a = pattern(id="a", scope="project:*")
    b = pattern(id="b", scope="company", record_type="core.Other")
    registry = NumberingRegistry([a, b])
    assert [p.id for p in registry.for_scope("project:P1")] == ["a"]
    assert [p.id for p in registry.for_scope("company")] == ["b"]


def test_duplicate_ids_are_refused() -> None:
    registry = NumberingRegistry([pattern()])
    with pytest.raises(NumberingConfigError, match="already registered"):
        registry.add(pattern())
    assert registry.get("p1") is not None
    assert registry.get("zz") is None


def test_skip_reserved_walks_past_adjacent_ranges() -> None:
    p = pattern(reserved=[(1, 10), (11, 20), (30, 35)])
    assert p.skip_reserved(1) == 21
    assert p.skip_reserved(21) == 21
    assert p.skip_reserved(30) == 36
    assert pattern().skip_reserved(7) == 7


GOOD = """
patterns:
  - id: ncr
    record_type: core.Record
    scope: "project:*"
    template: "NCR-{project}-{seq:4}"
    type_code: NCR
    gap_free: false
    reserved: [[1, 99]]
"""


def test_parse_numbering() -> None:
    registry = parse_numbering(GOOD, source="n.yaml")
    only = registry.all()[0]
    assert (only.id, only.gap_free, only.reserved) == ("ncr", False, [(1, 99)])


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("id: [", r"^n\.yaml: invalid YAML"),
        ("- a", r"^n\.yaml: expected a mapping"),
        ("patterns: 3", r"^n\.yaml: expected a mapping"),
        ("patterns: []\nextra: 1", r"^n\.yaml: expected a mapping"),
        ("patterns:\n  - id: x", r"^n\.yaml: patterns\[0\]\.record_type"),
        (GOOD + GOOD.split("patterns:")[1], r"^n\.yaml: numbering pattern 'ncr' is already"),
    ],
)
def test_parse_numbering_errors_name_the_source(text: str, message: str) -> None:
    with pytest.raises(NumberingConfigError, match=message):
        parse_numbering(text, source="n.yaml")


def test_load_numbering_reports_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(NumberingConfigError, match=r"^gone\.yaml: cannot read file"):
        load_numbering(tmp_path / "gone.yaml")


def test_the_shipped_file_numbers_core_records() -> None:
    registry = load_numbering(FIXTURE)
    found = registry.find("project:P123", "core.Record")
    assert found is not None
    assert found.compiled().render({"project": "P123", "type": found.type_code}, 1) == (
        "P123-REC-0001"
    )
    assert registry.find("company", "core.Record") is None


def test_get_numbering_reads_the_schema_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TL_SCHEMA_DIR", str(tmp_path))
    assert get_numbering().all() == []  # no numbering/patterns.yaml there
    (tmp_path / "numbering").mkdir()
    (tmp_path / "numbering" / "patterns.yaml").write_text(GOOD, encoding="utf-8")
    assert [p.id for p in get_numbering().all()] == ["ncr"]


def test_use_numbering_overrides_and_restores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    custom = NumberingRegistry([pattern(id="custom")])
    before = [p.id for p in get_numbering().all()]
    with use_numbering(custom):
        assert [p.id for p in get_numbering().all()] == ["custom"]
    assert [p.id for p in get_numbering().all()] == before
