"""`tl schema reload` records Schema.EffectiveChanged events (P0-I2)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    packages = tmp_path / "pkgs"
    shutil.copytree(FIXTURES, packages)
    env = {"TL_DB": str(tmp_path / "tl.db"), "TL_SCHEMA_DIR": str(packages)}
    assert runner.invoke(app, ["init"], env=env).exit_code == 0
    return env


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


def test_reload_records_once_then_reports_unchanged(env: dict[str, str]) -> None:
    first = run(env, "schema", "reload")
    assert first.exit_code == 0, first.output
    lines = first.stdout.splitlines()
    assert [line.split()[:2] for line in lines] == [
        ["recorded", "company"],
        ["recorded", "project:P123"],
    ]
    assert run(env, "schema", "reload").stdout.strip() == "unchanged"
    tail = run(env, "events", "tail", "--project", "P123", "-n", "5")
    assert "Schema.EffectiveChanged" in tail.stdout


def test_reload_records_an_edit(env: dict[str, str]) -> None:
    run(env, "schema", "reload")
    path = Path(env["TL_SCHEMA_DIR"]) / "x.P123@1.4.0.yaml"
    path.write_text(path.read_text().replace("Shutdown window reference", "Shutdown window ref"))
    again = run(env, "schema", "reload")
    assert [line.split()[:2] for line in again.stdout.splitlines()] == [
        ["recorded", "project:P123"]
    ]


def test_reload_reports_a_broken_package_directory(env: dict[str, str]) -> None:
    (Path(env["TL_SCHEMA_DIR"]) / "broken@1.0.0.yaml").write_text("package: [")
    result = run(env, "schema", "reload")
    assert result.exit_code == 1 and result.stderr.startswith("error:")
