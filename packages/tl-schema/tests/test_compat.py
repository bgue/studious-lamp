"""The schema-evolution guard: additive change passes; each breaking kind fails with one line."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from tl_schema import compat

BASE: compat.Baseline = {
    "Thing.Made": {
        "1": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "id": {"type": "string", "pattern": "^a+$", "format": "uuid"},
                "kind": {"type": "string", "enum": ["a", "b"]},
                "n": {"type": "integer", "minimum": 0, "maximum": 10},
                "note": {"type": ["string", "null"]},
                "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            },
            "required": ["id"],
        }
    }
}


def _mutate(fn: Any) -> compat.Baseline:
    new = copy.deepcopy(BASE)
    fn(new["Thing.Made"]["1"])
    return new


def test_committed_baseline_matches_generated_schemas() -> None:
    assert compat.diff(compat.load_baseline(), compat.current_schemas()) == []


def test_identical_passes() -> None:
    assert compat.diff(BASE, copy.deepcopy(BASE)) == []


def test_additive_changes_pass() -> None:
    def grow(s: dict[str, Any]) -> None:
        s["properties"]["extra"] = {"type": "string"}
        s["properties"]["kind"]["enum"].append("c")
        s["properties"]["n"]["maximum"] = 20
        s["properties"]["n"]["minimum"] = -1
        del s["properties"]["id"]["pattern"]
        s["properties"]["tags"]["maxItems"] = 9
        s["properties"]["note"]["type"] = ["string", "null", "integer"]

    new = _mutate(grow)
    new["Other.Made"] = {"1": {"type": "object", "properties": {}}}
    new["Thing.Made"]["2"] = {"type": "object", "properties": {}}
    assert compat.diff(BASE, new) == []


CASES: list[tuple[str, Any, str]] = [
    ("removed property", lambda s: s["properties"].pop("note"), "property 'note' removed"),
    (
        "type changed",
        lambda s: s["properties"]["n"].update(type="string"),
        "payload.n: type changed",
    ),
    (
        "format changed",
        lambda s: s["properties"]["id"].update(format="date"),
        "payload.id: format changed",
    ),
    (
        "became required",
        lambda s: s["required"].append("note"),
        "property 'note' became required",
    ),
    (
        "new required property",
        lambda s: (s["properties"].update(z={"type": "string"}), s["required"].append("z")),
        "property 'z' added as required",
    ),
    (
        "enum value removed",
        lambda s: s["properties"]["kind"].update(enum=["a"]),
        "payload.kind: enum tightened",
    ),
    (
        "pattern changed",
        lambda s: s["properties"]["id"].update(pattern="^b+$"),
        "payload.id: pattern",
    ),
    (
        "pattern added",
        lambda s: s["properties"]["kind"].update(pattern="^x$"),
        "payload.kind: pattern",
    ),
    (
        "upper bound tightened",
        lambda s: s["properties"]["n"].update(maximum=5),
        "payload.n: maximum tightened",
    ),
    (
        "lower bound tightened",
        lambda s: s["properties"]["n"].update(minimum=1),
        "payload.n: minimum tightened",
    ),
    (
        "bound added",
        lambda s: s["properties"]["tags"].update(minItems=1),
        "payload.tags: minItems tightened",
    ),
    (
        "nested type changed",
        lambda s: s["properties"]["tags"]["items"].update(type="integer"),
        "payload.tags[]: type changed",
    ),
]


@pytest.mark.parametrize(("name", "fn", "expect"), CASES, ids=[c[0] for c in CASES])
def test_breaking_change_fails_with_one_line(name: str, fn: Any, expect: str) -> None:
    lines = compat.diff(BASE, _mutate(fn))
    assert len(lines) == 1, lines
    assert lines[0].startswith("Thing.Made v1: ")
    assert expect in lines[0]


def test_removed_event_type_and_version_fail() -> None:
    assert compat.diff(BASE, {}) == ["Thing.Made: event type removed"]
    assert compat.diff(BASE, {"Thing.Made": {}}) == ["Thing.Made v1: schema version removed"]


def test_update_refuses_non_additive(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "base.json"
    path.write_text(compat.dumps(BASE), encoding="utf-8")
    monkeypatch.setattr(compat, "BASELINE_PATH", path)
    monkeypatch.setattr(compat, "current_schemas", lambda: {})
    assert compat.main(["--update"]) == 1
    assert compat.load_baseline(path) == BASE
    assert "Thing.Made: event type removed" in capsys.readouterr().err


def test_update_writes_additive(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "base.json"
    path.write_text(compat.dumps(BASE), encoding="utf-8")
    grown = _mutate(lambda s: s["properties"].update(extra={"type": "string"}))
    monkeypatch.setattr(compat, "BASELINE_PATH", path)
    monkeypatch.setattr(compat, "current_schemas", lambda: grown)
    assert compat.main(["--update"]) == 0
    assert compat.load_baseline(path) == grown
