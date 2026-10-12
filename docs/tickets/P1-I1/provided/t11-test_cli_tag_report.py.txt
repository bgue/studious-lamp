"""`tl tag report summary|missing|violations` on a temporary ledger (P1-I1-T11)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from tl_adapters.db import DbTarget, open_uow
from tl_cli.main import app
from tl_mod_engineering.handlers.tags import CreateTag, handle_create_tag
from tl_mod_engineering.testing import seed_registry
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    target = new_db()
    values = {"TL_DB": str(target)}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    seed_registry(target)
    tags: tuple[tuple[str, dict[str, Any]], ...] = (
        ("47-FV-1001", {"class_code": "ControlValve"}),
        (
            "47-FV-1002",
            {
                "class_code": "ControlValve",
                "psets": {"valve_data": {"size_in": 4, "manufacturer": "Acme"}},
            },
        ),
        ("10-PT-0001", {}),
        ("47-FV-1005", {"class_code": "ManualValve"}),
        ("LEGACY-1", {"pattern_policy": "record"}),
    )
    with open_uow(target) as uow:
        for number, more in tags:
            handle_create_tag(
                uow,
                CreateTag(
                    actor="user:dev", source="test", scope="project:P123", number=number, **more
                ),
            )
    return values


def report(env: dict[str, str], *args: str) -> RunResult:
    result = runner.invoke(app, ["tag", "report", *args, "--project", "P123"], env=env)
    assert result.exception is None, result.exception
    assert result.exit_code == 0, result.output
    return result


def test_summary_prints_one_line_per_class_and_state(env: dict[str, str]) -> None:
    assert report(env, "summary").stdout.splitlines() == [
        "- - tags=2 ok=2 warning=0 nonconformant=0".replace(" ", "  "),
        "ControlValve  -  tags=2  ok=1  warning=0  nonconformant=1",
        "ManualValve  -  tags=1  ok=0  warning=0  nonconformant=1",
    ]


def test_summary_json_is_a_list_of_objects(env: dict[str, str]) -> None:
    data = json.loads(report(env, "summary", "--json").stdout)
    assert data[1] == {
        "class_code": "ControlValve",
        "status": None,
        "tags": 2,
        "ok": 1,
        "warning": 0,
        "nonconformant": 1,
    }


def test_missing_lists_each_tag_with_what_it_lacks(env: dict[str, str]) -> None:
    lines = report(env, "missing").stdout.splitlines()
    assert lines[0] == "47-FV-1001  ControlValve  -"
    assert lines[1].startswith("  nonconformant psets.valve_data class_required: ")
    assert lines[2].startswith("  warning psets.valve_data.manufacturer required_in_state: ")
    assert [line for line in lines if not line.startswith(" ")] == [
        "47-FV-1001  ControlValve  -",
        "47-FV-1005  ManualValve  -",
    ]


def test_missing_can_be_narrowed_to_a_level_and_printed_as_json(env: dict[str, str]) -> None:
    soft = report(env, "missing", "--level", "warning").stdout.splitlines()
    assert all("nonconformant" not in line for line in soft)
    data = json.loads(report(env, "missing", "--json").stdout)
    assert [item["number"] for item in data] == ["47-FV-1001", "47-FV-1005"]
    assert data[0]["issues"][0] == {
        "path": "psets.valve_data",
        "rule": "class_required",
        "level": "nonconformant",
        "message": "Valve data is required by the record's class and has no values",
    }


def test_violations_lists_the_numbers_that_break_the_pattern(env: dict[str, str]) -> None:
    lines = report(env, "violations").stdout.splitlines()
    assert lines[0] == "LEGACY-1  violation"
    assert lines[1].startswith("  error number: 'LEGACY-1' does not fit the pattern")
    assert len(lines) == 2
    with_warnings = report(env, "violations", "--warnings").stdout.splitlines()
    assert with_warnings[0] == "47-FV-1005  ok"
    assert with_warnings[1].startswith("  warning mnemonic: 'FV' does not usually identify")


def test_a_project_with_no_tags_prints_nothing(env: dict[str, str]) -> None:
    result = runner.invoke(app, ["tag", "report", "summary", "--project", "P999"], env=env)
    assert result.exit_code == 0 and result.stdout == ""
