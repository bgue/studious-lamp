"""`tl pset set|get` (P0-I2-T08b). Copied into place by the ticket; do not edit."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    env = {"TL_DB": str(tmp_path / "tl.db")}
    assert run(env, "init").exit_code == 0
    created = run(
        env, "record", "create", "--project", "P123", "--key", "V-0001", "--title", "Valve 1"
    )
    assert created.exit_code == 0, created.output
    return env


def psets_of(result: RunResult) -> object:
    line = next(line for line in result.stdout.splitlines() if line.startswith("psets: "))
    return json.loads(line.removeprefix("psets: "))


def test_set_prints_three_lines_and_get_shows_the_values(env: dict[str, str]) -> None:
    result = run(
        env,
        "pset",
        "set",
        "--project",
        "P123",
        "V-0001",
        "valve_data",
        "size_in=4",
        "manufacturer=Acme",
    )
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert re.fullmatch(r"set [0-9A-Z]{26}", lines[0])
    assert lines[1:] == ["version 2", "conformance ok"]

    got = run(env, "pset", "get", "--project", "P123", "V-0001")
    assert got.exit_code == 0, got.output
    out = got.stdout.splitlines()
    assert out[0] == "key: V-0001" and out[1] == "version: 2"
    stored = out[2].removeprefix("effective_schema_hash: ")
    assert HEX64.match(stored)
    assert stored == run(env, "schema", "hash", "P123").stdout.strip()
    assert out[3] == "conformance: ok"
    assert psets_of(got) == {"valve_data": {"size_in": 4, "manufacturer": "Acme"}}


def test_values_are_parsed_as_json_when_possible(env: dict[str, str]) -> None:
    assert (
        run(
            env,
            "pset",
            "set",
            "--project",
            "P123",
            "V-0001",
            "valve_data",
            "size_in=4.5",
            "manufacturer=Acme Valves",
        ).exit_code
        == 0
    )
    assert (
        run(
            env,
            "pset",
            "set",
            "--project",
            "P123",
            "V-0001",
            "prj.shutdown_tie_in",
            "--layer",
            "project",
            "approved=true",
            "window=SD-2027-03",
        ).exit_code
        == 0
    )
    got = run(env, "pset", "get", "--project", "P123", "V-0001")
    assert psets_of(got) == {
        "valve_data": {"size_in": 4.5, "manufacturer": "Acme Valves"},
        "prj": {"shutdown_tie_in": {"approved": True, "window": "SD-2027-03"}},
    }


def test_custom_section_values(env: dict[str, str]) -> None:
    result = run(
        env,
        "pset",
        "set",
        "--project",
        "P123",
        "V-0001",
        "valve_data",
        "--layer",
        "custom",
        "x.fat_witness_by=client",
    )
    assert result.exit_code == 0, result.output
    got = run(env, "pset", "get", "--project", "P123", "V-0001", "valve_data")
    assert psets_of(got) == {"x": {"fat_witness_by": "client"}}


def test_a_missing_advisory_property_shows_a_warning(env: dict[str, str]) -> None:
    result = run(env, "pset", "set", "--project", "P123", "V-0001", "valve_data", "size_in=4")
    assert result.stdout.splitlines()[-1] == "conformance warning"
    got = run(env, "pset", "get", "--project", "P123", "V-0001")
    lines = got.stdout.splitlines()
    assert "conformance: warning" in lines
    assert (
        "issue warning required_in_state psets.valve_data.manufacturer Manufacturer is required"
        in lines
    )


def test_get_of_a_missing_section_is_an_empty_object(env: dict[str, str]) -> None:
    got = run(env, "pset", "get", "--project", "P123", "V-0001", "valve_data")
    assert got.exit_code == 0
    assert psets_of(got) == {}
    assert "effective_schema_hash: -" in got.stdout.splitlines()
    assert "conformance: ok" in got.stdout.splitlines()


@pytest.mark.parametrize(
    "args",
    [
        ["pset", "set", "--project", "P123", "NOPE-1", "valve_data", "size_in=4"],
        ["pset", "get", "--project", "P123", "NOPE-1"],
        ["pset", "set", "--project", "P123", "V-0001", "valve_data", "size_in"],
        ["pset", "set", "--project", "P123", "V-0001", "valve_data", "=4"],
        ["pset", "set", "--project", "P123", "V-0001", "valve_data", "size_in=four"],
        ["pset", "set", "--project", "P123", "V-0001", "valve_data", "nope=1"],
        ["pset", "set", "--project", "P123", "V-0001", "no_such_pset", "a=1"],
        ["pset", "set", "--project", "P123", "V-0001", "valve_data", "x.a=1"],
        [
            "pset",
            "set",
            "--project",
            "P123",
            "V-0001",
            "valve_data",
            "--layer",
            "bogus",
            "size_in=4",
        ],
        ["pset", "set", "--project", "P123", "V-0001", "enrich.ai", "a=1"],
    ],
)
def test_failures_exit_one_with_an_error_line(env: dict[str, str], args: list[str]) -> None:
    result = run(env, *args)
    assert result.exit_code == 1, result.output
    assert result.stderr.startswith("error:")


def test_repeated_identical_values_are_refused(env: dict[str, str]) -> None:
    args = ["pset", "set", "--project", "P123", "V-0001", "valve_data", "size_in=4"]
    assert run(env, *args).exit_code == 0
    again = run(env, *args)
    assert again.exit_code == 1 and again.stderr.startswith("error:")


def test_pset_group_is_listed() -> None:
    assert "pset" in runner.invoke(app, ["--help"]).stdout


def test_null_unsets_a_value(env: dict[str, str]) -> None:
    assert (
        run(
            env,
            "pset",
            "set",
            "--project",
            "P123",
            "V-0001",
            "valve_data",
            "size_in=4",
            "manufacturer=Acme",
        ).exit_code
        == 0
    )
    cleared = run(env, "pset", "set", "--project", "P123", "V-0001", "valve_data", "size_in=null")
    assert cleared.exit_code == 0, cleared.output
    got = run(env, "pset", "get", "--project", "P123", "V-0001")
    assert psets_of(got) == {"valve_data": {"manufacturer": "Acme"}}
