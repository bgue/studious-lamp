"""`tl schema hash|lint|validate` (P0-I2-T08). Copied into place by the ticket; do not edit."""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()
FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def run(*args: str, env: dict[str, str] | None = None) -> RunResult:
    return runner.invoke(app, list(args), env=env or {})


@pytest.fixture
def packages(tmp_path: Path) -> Path:
    target = tmp_path / "pkgs"
    shutil.copytree(FIXTURES, target)
    return target


def edit_yaml(path: Path, change: Callable[[dict[str, Any]], object]) -> None:
    data: dict[str, Any] = yaml.safe_load(path.read_text())
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_schema_group_is_listed() -> None:
    assert "schema" in run("--help").stdout
    helped = run("schema", "--help").stdout
    for name in ("hash", "lint", "validate"):
        assert name in helped


# --- hash --------------------------------------------------------------------------------------


def test_hash_prints_a_stable_hash_for_a_project() -> None:
    first = run("schema", "hash", "P123")
    assert first.exit_code == 0, first.output
    value = first.stdout.strip()
    assert HEX64.match(value)
    assert run("schema", "hash", "P123").stdout.strip() == value
    assert run("schema", "hash", "project:P123").stdout.strip() == value


def test_hash_differs_between_scopes() -> None:
    project = run("schema", "hash", "P123").stdout.strip()
    company = run("schema", "hash", "company").stdout.strip()
    assert HEX64.match(company) and company != project


def test_hash_changes_when_a_package_changes(packages: Path) -> None:
    before = run("schema", "hash", "P123", "--dir", str(packages)).stdout.strip()
    edit_yaml(
        packages / "x.P123@1.4.0.yaml",
        lambda d: d["extends"][0]["tighten"].update({"size_in": {"minimum": 1}}),
    )
    after = run("schema", "hash", "P123", "--dir", str(packages)).stdout.strip()
    assert HEX64.match(after) and after != before


def test_hash_reads_the_directory_from_the_environment(packages: Path) -> None:
    default = run("schema", "hash", "P123").stdout.strip()
    edit_yaml(
        packages / "prj.P123@1.0.0.yaml",
        lambda d: d["psets"]["shutdown_tie_in"].update({"label": "Tie-in"}),
    )
    changed = run("schema", "hash", "P123", env={"TL_SCHEMA_DIR": str(packages)})
    assert changed.exit_code == 0 and changed.stdout.strip() != default


def test_hash_of_an_unknown_project_is_an_error() -> None:
    result = run("schema", "hash", "P999")
    assert result.exit_code == 1
    assert "error:" in result.stderr and "P999" in result.stderr


def test_hash_reports_a_broken_package(packages: Path) -> None:
    (packages / "broken@1.0.0.yaml").write_text("package: [unclosed")
    result = run("schema", "hash", "P123", "--dir", str(packages))
    assert result.exit_code == 1 and result.stderr.startswith("error:")


def test_hash_reports_a_rule_violation(packages: Path) -> None:
    edit_yaml(
        packages / "x.P123@1.4.0.yaml",
        lambda d: d["extends"][0]["tighten"].update({"size_in": {"minimum": 0.1}}),
    )
    result = run("schema", "hash", "P123", "--dir", str(packages))
    assert result.exit_code == 1
    assert "loosen" in result.stderr


# --- lint --------------------------------------------------------------------------------------


def test_lint_prints_the_fixture_warning() -> None:
    result = run("schema", "lint")
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines == [
        "warning L004 co.acme.engineering@3.2.0 psets.valve_data.properties.body_material "
        "promoted property has no exact_mappings",
        "0 errors, 1 warnings",
    ]


def test_lint_fails_on_an_error(packages: Path) -> None:
    edit_yaml(
        packages / "prj.P123@1.0.0.yaml",
        lambda d: d["psets"]["shutdown_tie_in"].update({"applies_to": ["weld"]}),
    )
    result = run("schema", "lint", "--dir", str(packages))
    assert result.exit_code == 1
    assert any(line.startswith("error L007 prj.P123@1.0.0 ") for line in result.stdout.splitlines())
    assert result.stdout.splitlines()[-1] == "1 errors, 1 warnings"


def test_lint_reports_a_missing_directory(tmp_path: Path) -> None:
    result = run("schema", "lint", "--dir", str(tmp_path / "nope"))
    assert result.exit_code == 1 and result.stderr.startswith("error:")


# --- validate ----------------------------------------------------------------------------------


def test_validate_checks_every_scope() -> None:
    result = run("schema", "validate")
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert len(lines) == 2
    assert re.fullmatch(r"ok company [0-9a-f]{12}", lines[0])
    assert re.fullmatch(r"ok project:P123 [0-9a-f]{12}", lines[1])
    project_hash = run("schema", "hash", "P123").stdout.strip()
    assert lines[1].endswith(project_hash[:12])


def test_validate_can_name_scopes() -> None:
    result = run("schema", "validate", "P123")
    assert result.exit_code == 0
    assert [line.split()[:2] for line in result.stdout.splitlines()] == [["ok", "project:P123"]]


def test_validate_reports_a_failing_scope_and_checks_the_others(packages: Path) -> None:
    edit_yaml(
        packages / "x.P123@1.4.0.yaml",
        lambda d: d["extends"][0]["tighten"].update({"size_in": {"minimum": 0.1}}),
    )
    result = run("schema", "validate", "--dir", str(packages))
    assert result.exit_code == 1
    assert result.stdout.splitlines()[0].startswith("ok company ")
    assert "error: project:P123:" in result.stderr and "loosen" in result.stderr


def test_validate_checks_cross_package_references(packages: Path) -> None:
    edit_yaml(
        packages / "x.P123@1.4.0.yaml",
        lambda d: d["depends"].update({"co.acme.engineering": "9.9.9"}),
    )
    result = run("schema", "validate", "--dir", str(packages))
    assert result.exit_code == 1
    assert "9.9.9" in result.stderr
