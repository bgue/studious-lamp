"""`tl link trace` against a temporary ledger (P0-I3; brief 7.5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
PROJECT = ("--project", "P123")


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    values = {"TL_DB": str(tmp_path / "tl.db")}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    return values


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


@pytest.fixture
def chain(env: dict[str, str]) -> dict[str, str]:
    """A -references-> B -requires-> C, and D -references-> A. Returns title -> key."""
    keys: dict[str, str] = {}
    for title in "ABCD":
        out = run(env, "record", "create", *PROJECT, "--title", title).stdout
        keys[title] = next(line.split()[1] for line in out.splitlines() if line.startswith("key "))
    for source, target, *relation in (("A", "B"), ("B", "C", "requires"), ("D", "A")):
        extra = ["--relation", relation[0]] if relation else []
        result = run(env, "link", "add", *PROJECT, keys[source], keys[target], *extra)
        assert result.exit_code == 0, result.output
    return keys


def trace(env: dict[str, str], key: str, *extra: str) -> RunResult:
    return run(env, "link", "trace", *PROJECT, key, *extra)


def test_trace_shows_both_directions_as_an_indented_tree(
    env: dict[str, str], chain: dict[str, str]
) -> None:
    result = trace(env, chain["A"])
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == [
        f"{chain['A']}  A",
        f"  references: {chain['B']}  B",
        f"    requires: {chain['C']}  C",
        f"  referenced by: {chain['D']}  D",
    ]


def test_direction_and_depth_limit_the_tree(env: dict[str, str], chain: dict[str, str]) -> None:
    out_only = trace(env, chain["A"], "--direction", "out").stdout.splitlines()
    assert out_only == [
        f"{chain['A']}  A",
        f"  references: {chain['B']}  B",
        f"    requires: {chain['C']}  C",
    ]
    in_only = trace(env, chain["A"], "--direction", "in", "--depth", "1").stdout.splitlines()
    assert in_only == [f"{chain['A']}  A", f"  referenced by: {chain['D']}  D"]
    assert trace(env, chain["A"], "--depth", "0").stdout.splitlines() == [
        f"{chain['A']}  A  +2 more"
    ]


def test_a_broken_link_is_marked(env: dict[str, str], chain: dict[str, str]) -> None:
    listing = run(env, "link", "list", *PROJECT, chain["B"]).stdout.splitlines()
    link_id = next(
        line for line in listing if "requires" in line and line.startswith("out")
    ).split()[-1]
    flagged = run(env, "link", "flag", *PROJECT, link_id, "--status", "broken", "--reason", "gone")
    assert flagged.exit_code == 0, flagged.output
    lines = trace(env, chain["A"], "--direction", "out").stdout.splitlines()
    assert lines[-1].endswith("C  ✗ broken")


def test_errors(env: dict[str, str], chain: dict[str, str]) -> None:
    bad = trace(env, chain["A"], "--direction", "sideways")
    assert bad.exit_code == 1
    assert "error: --direction must be out, in or both, not 'sideways'" in bad.stderr
    missing = trace(env, "NOPE-1")
    assert missing.exit_code == 1
    assert "error: no record with key 'NOPE-1' in project 'P123'" in missing.stderr
