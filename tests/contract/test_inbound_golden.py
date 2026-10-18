"""Golden cases for the restricted mapping runtime (P1-I7-T08). Provided; do not edit.

``tests/golden/inbound/mappings.json`` holds payloads, JSONata expressions and the commands (or the
refusal) each must give. The file is the ticket's work: every category below needs at least the
number of cases listed in ``MINIMUM``. The runner also runs the shared runtime contract check, so a
runtime that drifts from the profile fails here before it fails a customer.

A case is ``{"name", "category", "expression", "payload", "status", "commands" | "problem_codes"}``
for an evaluation and ``{"name", "expression", "accepted"}`` (under ``"checks"``) for the profile
check alone. The expected values are worked out from the JSONata rules, never pasted from the
runtime's own answer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from tl_core.integration.contract import MappedCommand
from tl_core.integration.inbound.mapping import JsonataRestricted

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integration_contract import check_mapping_runtime_contract  # noqa: E402

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "inbound" / "mappings.json"
#: category -> least number of evaluation cases
MINIMUM = {
    "single": 3,  # one object out
    "many": 3,  # a list, or a path that maps each element
    "conditional": 3,  # a `?:` or a filter, with an empty result among them
    "functions": 5,  # allowed string, number, array and object functions
    "missing": 2,  # a field the payload does not have
    "invalid_output": 4,  # not commands: text, a number, an unlisted command, a server field
    "limit": 2,  # too many commands, a runaway expression
    "error": 1,  # an expression that does not parse
}
MINIMUM_CHECKS = {True: 4, False: 6}  # accepted expressions, refused expressions
STATUSES = {"ok", "invalid_output", "limit", "error"}

RUNTIME = JsonataRestricted()


def load() -> dict[str, Any]:
    return json.loads(GOLDEN.read_text("utf-8"))


def cases() -> list[dict[str, Any]]:
    return load()["cases"]


def checks() -> list[dict[str, Any]]:
    return load()["checks"]


def test_the_runtime_passes_the_shared_contract_checks() -> None:
    check_mapping_runtime_contract(RUNTIME)


def test_the_golden_file_covers_every_category_enough() -> None:
    found: dict[str, int] = {}
    for case in cases():
        found[case["category"]] = found.get(case["category"], 0) + 1
    assert set(found) <= set(MINIMUM), f"unknown categories: {set(found) - set(MINIMUM)}"
    for category, least in MINIMUM.items():
        assert found.get(category, 0) >= least, f"{category}: {found.get(category, 0)} of {least}"
    accepted = sum(1 for c in checks() if c["accepted"])
    refused = sum(1 for c in checks() if not c["accepted"])
    assert accepted >= MINIMUM_CHECKS[True] and refused >= MINIMUM_CHECKS[False]


def test_the_cases_are_well_formed_and_named_once() -> None:
    names = [c["name"] for c in cases()] + [c["name"] for c in checks()]
    assert len(names) == len(set(names)), "a case name is used twice"
    for case in cases():
        assert case["status"] in STATUSES, case["name"]
        assert isinstance(case["expression"], str) and "payload" in case, case["name"]
        if case["status"] == "ok":
            assert "commands" in case and "problem_codes" not in case, case["name"]
        else:
            assert case.get("problem_codes"), f"{case['name']} says which problem it expects"
            assert "commands" not in case, case["name"]
    assert any(c["status"] == "ok" and c["commands"] == [] for c in cases()), "an empty result"


@pytest.mark.parametrize("case", cases(), ids=lambda c: c["name"])
def test_each_case_gives_exactly_the_recorded_answer(case: dict[str, Any]) -> None:
    refused = RUNTIME.check(case["expression"])
    if case["status"] == "error" and refused:  # a syntax error may be caught by the check alone
        assert [p.code for p in refused] == case["problem_codes"]
        return
    assert refused == [], case["name"]
    outcome = RUNTIME.evaluate(case["expression"], case["payload"])
    assert outcome.status == case["status"], (case["name"], outcome.problems)
    if case["status"] == "ok":
        expected = [MappedCommand.model_validate(c) for c in case["commands"]]
        assert outcome.commands == expected
    else:
        assert outcome.commands == []
        assert [p.code for p in outcome.problems] == case["problem_codes"]


@pytest.mark.parametrize("check", checks(), ids=lambda c: c["name"])
def test_the_profile_accepts_and_refuses_as_recorded(check: dict[str, Any]) -> None:
    problems = RUNTIME.check(check["expression"])
    assert (problems == []) is check["accepted"], (check["name"], problems)
    if not check["accepted"]:
        assert [p.code for p in problems] == check["problem_codes"]


def test_the_same_case_gives_the_same_answer_twice() -> None:
    for case in [c for c in cases() if c["status"] == "ok"][:5]:
        first = RUNTIME.evaluate(case["expression"], case["payload"])
        assert RUNTIME.evaluate(case["expression"], case["payload"]) == first, case["name"]
