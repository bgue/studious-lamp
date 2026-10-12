"""`tl tag create|show|ls|reclassify|rename|split|merge` on a temporary ledger (P1-I1-T09b)."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
from tl_adapters.db import DbTarget
from tl_cli.main import app
from tl_mod_engineering.testing import seed_registry
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """A fresh ledger with the registry seeded (area list, mnemonics, the tag pattern, classes)."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    target = new_db()
    values = {"TL_DB": str(target)}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    seed_registry(target)
    return values


def run(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    result = runner.invoke(app, list(args), env=env)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert (result.exit_code == 0) is ok, result.output
    return result


def tag(env: dict[str, str], *args: str, ok: bool = True) -> RunResult:
    return run(env, "tag", *args, ok=ok)


def make(env: dict[str, str], number: str, *more: str) -> RunResult:
    return tag(env, "create", number, "--project", "P123", *more)


def ls(env: dict[str, str], *more: str) -> list[str]:
    return tag(env, "ls", "--project", "P123", *more).stdout.splitlines()


# --- create --------------------------------------------------------------------------------------


def test_create_prints_the_tag_its_segments_and_what_is_missing(env: dict[str, str]) -> None:
    result = make(env, "47-FV-1001", "--class", "ControlValve", "--service", "Feed gas control")
    lines = result.stdout.splitlines()
    assert lines[0].startswith("created ") and len(lines[0].split()[1]) == 26
    assert lines[1:7] == [
        "tag 47-FV-1001",
        "class ControlValve",
        "segments area=47 mnemonic=FV seq=1001",
        "number_status ok",
        "conformance nonconformant",
        "issue nonconformant psets.valve_data class_required: "
        "Valve data is required by the record's class and has no values",
    ]
    assert lines[7].startswith("issue warning psets.valve_data.manufacturer required_in_state")


def test_a_number_that_breaks_the_pattern_is_refused_with_each_problem(
    env: dict[str, str],
) -> None:
    result = make_fail(env, "47-XX-1")
    err = result.stderr.splitlines()
    assert err[0].startswith("error: tag number '47-XX-1': the sequence '1' must be written with 4")
    assert "  - seq: the sequence '1' must be written with 4 digits, like 0001 (error)" in err
    assert "  - mnemonic: 'XX' is not a registered mnemonic (error)" in err
    assert ls(env) == []


def make_fail(env: dict[str, str], number: str, *more: str) -> RunResult:
    return tag(env, "create", number, "--project", "P123", *more, ok=False)


def test_allow_violation_stores_the_number_as_a_violation(env: dict[str, str]) -> None:
    result = make(env, "LEGACY-7", "--allow-violation")
    assert "number_status violation" in result.stdout.splitlines()
    assert "segments -" in result.stdout.splitlines()
    shown = tag(env, "show", "LEGACY-7", "--project", "P123").stdout
    assert "violation error number: 'LEGACY-7' does not fit the pattern" in shown


def test_values_given_with_pset_are_written_and_can_make_the_tag_conform(
    env: dict[str, str],
) -> None:
    result = make(
        env,
        "47-FV-1001",
        "--class",
        "ControlValve",
        "--pset",
        "valve_data.size_in=4",
        "--pset",
        "valve_data.manufacturer=Acme",
    )
    assert "conformance ok" in result.stdout.splitlines()
    assert "issue" not in result.stdout
    assert (
        'psets: {"valve_data":{"manufacturer":"Acme","size_in":4}}'
        in tag(env, "show", "47-FV-1001", "--project", "P123").stdout
    )


@pytest.mark.parametrize("bad", ["size_in=4", "valve_data=4", "valve_data.x.fat=1", "prj.p.q=1"])
def test_a_pset_option_must_name_a_standard_property(env: dict[str, str], bad: str) -> None:
    result = make_fail(env, "47-FV-1001", "--class", "ControlValve", "--pset", bad)
    assert "error: expected PSET.PROPERTY=VALUE" in result.stderr
    assert ls(env) == []


def test_create_refuses_an_unknown_class_and_a_duplicate_number(env: dict[str, str]) -> None:
    assert "no active tag class 'Nope'" in make_fail(env, "47-FV-1001", "--class", "Nope").stderr
    make(env, "47-FV-1001")
    assert "already used" in make_fail(env, "47-FV-1001").stderr


def test_the_project_option_is_required(env: dict[str, str]) -> None:
    result = runner.invoke(app, ["tag", "create", "47-FV-1001"], env=env)
    assert result.exit_code == 2


# --- show and ls ---------------------------------------------------------------------------------


def test_show_prints_every_part_of_a_tag(env: dict[str, str]) -> None:
    make(env, "47-FV-1001", "--class", "ControlValve", "--service", "Feed gas control")
    lines = tag(env, "show", "47-FV-1001", "--project", "P123").stdout.splitlines()
    fields = dict(
        line.split(": ", 1)
        for line in lines
        if ": " in line and not line.startswith(("issue", "violation"))
    )
    assert fields["number"] == "47-FV-1001" and fields["title"] == "Feed gas control"
    assert (fields["class"], fields["status"], fields["area"]) == ("ControlValve", "-", "47")
    assert (fields["mnemonic"], fields["sequence"], fields["pattern"]) == ("FV", "1001", "tag")
    assert (fields["number_status"], fields["origin"], fields["conformance"]) == (
        "ok",
        "created",
        "nonconformant",
    )
    assert fields["segments"] == "area=47 mnemonic=FV seq=1001"
    assert any(
        line.startswith("issue nonconformant psets.valve_data class_required") for line in lines
    )
    assert lines[-1] == "psets: {}"


def test_show_an_unknown_tag_is_an_error(env: dict[str, str]) -> None:
    result = tag(env, "show", "47-FV-9999", "--project", "P123", ok=False)
    assert "error: no tag '47-FV-9999' in project 'P123'" in result.stderr


def test_ls_lists_by_number_and_filters(env: dict[str, str]) -> None:
    make(env, "47-FV-1002", "--class", "ControlValve", "--service", "Fuel gas")
    make(env, "47-FV-1001", "--class", "ControlValve")
    make(env, "10-PT-0001")
    make(env, "LEGACY-1", "--allow-violation")
    assert ls(env) == [
        "10-PT-0001  -  -  ok  10-PT-0001",
        "47-FV-1001  ControlValve  -  nonconformant  47-FV-1001",
        "47-FV-1002  ControlValve  -  nonconformant  Fuel gas",
        "LEGACY-1  -  -  ok  LEGACY-1",
    ]
    assert [x.split("  ")[0] for x in ls(env, "--class", "ControlValve")] == [
        "47-FV-1001",
        "47-FV-1002",
    ]
    assert [x.split("  ")[0] for x in ls(env, "--mnemonic", "PT")] == ["10-PT-0001"]
    assert [x.split("  ")[0] for x in ls(env, "--area", "47", "--limit", "1")] == ["47-FV-1001"]
    assert [x.split("  ")[0] for x in ls(env, "--number-status", "violation")] == ["LEGACY-1"]
    assert ls(env, "--status", "Design") == []


def test_ls_json_prints_a_list_of_objects(env: dict[str, str]) -> None:
    make(env, "47-FV-1001", "--class", "ControlValve", "--service", "Fuel gas")
    (item,) = json.loads(tag(env, "ls", "--project", "P123", "--json").stdout)
    assert item == {
        "number": "47-FV-1001",
        "class_code": "ControlValve",
        "status": None,
        "conformance": "nonconformant",
        "title": "Fuel gas",
        "number_status": "ok",
    }


# --- changes -------------------------------------------------------------------------------------


def test_reclassify_moves_the_tag_to_another_class(env: dict[str, str]) -> None:
    make(env, "47-FV-1001")
    result = tag(
        env,
        "reclassify",
        "47-FV-1001",
        "--project",
        "P123",
        "--class",
        "ControlValve",
        "--reason",
        "Actuator added",
    )
    assert result.stdout.splitlines() == [
        "reclassified 47-FV-1001 - -> ControlValve",
        "conformance nonconformant",
    ]
    again = tag(
        env,
        "reclassify",
        "47-FV-1001",
        "--project",
        "P123",
        "--class",
        "ControlValve",
        "--reason",
        "x",
        ok=False,
    )
    assert "already of class ControlValve" in again.stderr


def test_rename_leaves_the_old_tag_out_of_the_default_list(env: dict[str, str]) -> None:
    make(env, "47-FV-1001", "--class", "ControlValve", "--service", "Feed gas")
    result = tag(
        env, "rename", "47-FV-1001", "47-FV-1002", "--project", "P123", "--reason", "P&ID rev 3"
    )
    assert result.stdout.splitlines()[0] == "renamed 47-FV-1001 -> 47-FV-1002"
    assert [x.split("  ")[0] for x in ls(env)] == ["47-FV-1002"]
    both = ls(env, "--all")
    assert [x.split("  ")[0] for x in both] == ["47-FV-1001", "47-FV-1002"]
    assert both[0].split("  ")[2] == "Superseded"
    gone = tag(
        env, "rename", "47-FV-1001", "47-FV-1009", "--project", "P123", "--reason", "x", ok=False
    )
    assert "Superseded" in gone.stderr


def test_split_and_merge(env: dict[str, str]) -> None:
    make(env, "47-FV-1001", "--class", "ControlValve")
    result = tag(
        env,
        "split",
        "47-FV-1001",
        "47-FV-1002",
        "47-FV-1003",
        "--project",
        "P123",
        "--reason",
        "two valves",
    )
    assert result.stdout.splitlines()[0] == "split 47-FV-1001 -> 47-FV-1002, 47-FV-1003"
    assert sum(1 for line in result.stdout.splitlines() if line.startswith("created ")) == 2
    merged = tag(
        env,
        "merge",
        "47-FV-1002",
        "47-FV-1003",
        "--into",
        "47-FV-1004",
        "--project",
        "P123",
        "--reason",
        "one again",
    )
    assert merged.stdout.splitlines()[0] == "merged 47-FV-1002, 47-FV-1003 -> 47-FV-1004"
    assert [x.split("  ")[0] for x in ls(env)] == ["47-FV-1004"]


def test_a_change_to_an_unknown_tag_is_an_error(env: dict[str, str]) -> None:
    for args in (
        ("rename", "NOPE-1", "47-FV-1002", "--reason", "x"),
        ("split", "NOPE-1", "47-FV-1002", "47-FV-1003", "--reason", "x"),
        ("reclassify", "NOPE-1", "--class", "ControlValve", "--reason", "x"),
    ):
        result = tag(env, *args[:1], *args[1:], "--project", "P123", ok=False)
        assert "error: no tag 'NOPE-1' in project 'P123'" in result.stderr
