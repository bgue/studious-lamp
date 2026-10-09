"""`tl pset` turns service and schema failures into `error:` lines (review follow-up)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_cli import pset as pset_module
from tl_cli.main import app
from tl_core.services.errors import RecordNotFoundError
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    env = {"TL_DB": str(tmp_path / "tl.db")}
    assert runner.invoke(app, ["init"], env=env).exit_code == 0
    created = runner.invoke(
        app, ["record", "create", "--project", "P123", "--key", "V-1", "--title", "V"], env=env
    )
    assert created.exit_code == 0, created.output
    return env


def test_get_reports_a_service_error_raised_by_conformance(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object) -> None:
        raise RecordNotFoundError("record vanished")

    monkeypatch.setattr(pset_module, "conformance", boom)
    result = runner.invoke(app, ["pset", "get", "--project", "P123", "V-1"], env=env)
    assert result.exit_code == 1
    assert result.stderr.startswith("error: record vanished")


def test_set_and_get_report_a_broken_package_directory(env: dict[str, str], tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "bad@1.0.0.yaml").write_text("package: [")
    env = {**env, "TL_SCHEMA_DIR": str(broken)}
    for args in (
        ["pset", "set", "--project", "P123", "V-1", "valve_data", "size_in=4"],
        ["pset", "get", "--project", "P123", "V-1"],
    ):
        result = runner.invoke(app, args, env=env)
        assert result.exit_code == 1, result.output
        assert result.stderr.startswith("error:")
