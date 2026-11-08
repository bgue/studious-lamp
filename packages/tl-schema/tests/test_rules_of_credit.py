"""Rules of credit as package content (P2-I5 S1): the section, its bounds and lint rule L008."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from tl_schema.lint import lint_documents
from tl_schema.packages import FORBIDDEN_TEXT, PackageDoc
from tl_schema.registry import PackageError, load_package, parse_package

REPO = Path(__file__).resolve().parents[3]
PACKAGE = REPO / "schema" / "fixtures" / "packages" / "co.acme.awp@1.1.0.yaml"


def _doc(rules: list[dict[str, Any]]) -> str:
    return yaml.safe_dump(
        {
            "package": "co.acme.awp",
            "version": "1.1.0",
            "kind": "company",
            "description": "Rules of credit under test.",
            "rules_of_credit": rules,
        }
    )


def _rule(weights: list[int], commodity: str = "piping", evidence: str = "manual") -> dict[str, Any]:
    steps = [{"name": f"Step {i}", "weight": w, "evidence": evidence} for i, w in enumerate(weights)]
    return {"commodity": commodity, "kind": "scope_item", "steps": steps}


def _messages(doc: PackageDoc) -> list[str]:
    return [i.message for i in lint_documents([doc]) if i.severity == "error"]


def test_shipped_package_lints_clean_and_piping_sums_to_100() -> None:
    doc = load_package(PACKAGE)
    assert _messages(doc) == []
    piping = next(r for r in doc.rules_of_credit if r.commodity == "piping")
    assert [s.weight for s in piping.steps] == [30, 60, 10]
    assert [r.commodity for r in doc.rules_of_credit] == ["piping", "weld", "bolted_joint"]
    codes = {name: [v.code for v in cl.values] for name, cl in doc.code_lists.items()}
    assert "Interface" in codes["ConstraintType"]
    assert codes["MissReason"][0] == "Constraint" and len(codes["MissReason"]) == 8


def test_weights_not_summing_to_100_are_refused_with_the_fixed_message() -> None:
    doc = parse_package(_doc([_rule([30, 60, 20])]), source="t")
    assert _messages(doc) == ["rules_of_credit: weights of piping do not sum to 100"]
    assert _messages(parse_package(_doc([_rule([99])]), source="t")) != []
    assert _messages(parse_package(_doc([_rule([100])]), source="t")) == []
    assert _messages(parse_package(_doc([_rule([50, 51])]), source="t")) != []


@pytest.mark.parametrize(
    "rule",
    [
        _rule([0, 100]),
        _rule([101]),
        _rule([100], evidence="scope_state:"),
        _rule([100], evidence="whatever"),
        _rule([100], commodity="Piping"),
        {"commodity": "x", "kind": "pipe", "steps": [{"name": "a", "weight": 100, "evidence": "manual"}]},
        {"commodity": "x", "kind": "weld", "steps": []},
        {**_rule([100]), "extra": 1},
    ],
)
def test_malformed_entries_are_refused(rule: dict[str, Any]) -> None:
    with pytest.raises(PackageError):
        parse_package(_doc([rule]), source="t")


def test_bounds_name_length_entries_and_steps() -> None:
    long_name = _rule([100])
    long_name["steps"][0]["name"] = "n" * 41
    with pytest.raises(PackageError):
        parse_package(_doc([long_name]), source="t")
    ok_name = _rule([100])
    ok_name["steps"][0]["name"] = "n" * 40
    parse_package(_doc([ok_name]), source="t")
    many = [_rule([100], commodity=f"c{i}") for i in range(41)]
    with pytest.raises(PackageError):
        parse_package(_doc(many), source="t")
    parse_package(_doc(many[:40]), source="t")
    with pytest.raises(PackageError):
        parse_package(_doc([_rule([100]), _rule([100])]), source="t")


@pytest.mark.parametrize("mark", ["‮", "‏", "\x00", "\x85"])
def test_direction_marks_and_control_characters_are_refused(mark: str) -> None:
    rule = _rule([100])
    rule["steps"][0]["name"] = f"a{mark}b"
    with pytest.raises(PackageError):
        parse_package(_doc([rule]), source="t")


def test_forbidden_text_matches_the_core_pattern() -> None:
    from tl_core.text import FORBIDDEN_TEXT as CORE

    assert FORBIDDEN_TEXT.pattern == CORE.pattern


def test_a_package_without_the_section_is_unchanged() -> None:
    doc = parse_package(_doc([]).replace("rules_of_credit: []\n", ""), source="t")
    assert doc.rules_of_credit == [] and _messages(doc) == []
