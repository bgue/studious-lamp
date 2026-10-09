"""`tl record create` without --key takes the key from the numbering pattern (P0-I3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_cli.main import app
from typer.testing import CliRunner
from typer.testing import Result as RunResult

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    schema = tmp_path / "schema"
    (schema / "numbering").mkdir(parents=True)
    (schema / "numbering" / "patterns.yaml").write_text(
        """
patterns:
  - id: core.Record
    record_type: core.Record
    scope: "project:*"
    template: "{project}-{type}-{discipline}-{seq:4}"
    type_code: REC
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("TL_SCHEMA_DIR", str(schema))
    values = {"TL_DB": str(tmp_path / "tl.db")}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    return values


def run(env: dict[str, str], *args: str) -> RunResult:
    return runner.invoke(app, list(args), env=env)


def test_create_without_a_key_prints_the_allocated_key(env: dict[str, str]) -> None:
    result = run(
        env,
        "record",
        "create",
        "--project",
        "P123",
        "--title",
        "NCR",
        "--segment",
        "discipline=PIP",
    )
    assert result.exit_code == 0, result.output
    assert "key P123-REC-PIP-0001" in result.stdout
    again = run(
        env,
        "record",
        "create",
        "--project",
        "P123",
        "--title",
        "Two",
        "--segment",
        "discipline=PIP",
    )
    assert "key P123-REC-PIP-0002" in again.stdout


def test_the_allocated_key_can_be_shown(env: dict[str, str]) -> None:
    run(
        env,
        "record",
        "create",
        "--project",
        "P123",
        "--title",
        "NCR",
        "--segment",
        "discipline=ELE",
    )
    shown = run(env, "record", "show", "--project", "P123", "P123-REC-ELE-0001")
    assert shown.exit_code == 0, shown.output
    assert "title: NCR" in shown.stdout


def test_a_missing_segment_is_reported(env: dict[str, str]) -> None:
    result = run(env, "record", "create", "--project", "P123", "--title", "NCR")
    assert result.exit_code == 1
    assert "discipline" in result.output


def test_a_malformed_segment_is_reported(env: dict[str, str]) -> None:
    result = run(
        env, "record", "create", "--project", "P123", "--title", "NCR", "--segment", "oops"
    )
    assert result.exit_code == 1
    assert "NAME=VALUE" in result.output


def test_an_explicit_key_still_works(env: dict[str, str]) -> None:
    result = run(env, "record", "create", "--project", "P123", "--title", "x", "--key", "K-1")
    assert result.exit_code == 0, result.output
    assert "key K-1" in result.stdout
