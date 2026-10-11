"""`tl config import` answers a file it cannot read with an error line, not a traceback."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path) -> Iterator[dict[str, str]]:
    values = {"TL_DB": str(tmp_path / "tl.db")}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    yield values


def test_a_file_that_is_not_utf8_is_a_clean_error(env: dict[str, str], tmp_path: Path) -> None:
    path = tmp_path / "latin.yaml"
    path.write_bytes(b"settings: {}\n# caf\xe9\n")
    result = runner.invoke(app, ["config", "import", str(path), "--company"], env=env)
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == f"error: {path} is not UTF-8 text\n"


def test_a_directory_is_a_clean_error(env: dict[str, str], tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "import", str(tmp_path), "--company"], env=env)
    assert result.exit_code != 0  # typer refuses a directory (dir_okay=False) before the command
    assert "Traceback" not in result.output
