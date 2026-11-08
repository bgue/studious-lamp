"""`tl --version` prints the release version from the installed tl-cli metadata (P2-REL-T01)."""

from __future__ import annotations

import re
from importlib.metadata import version

from tl_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


def test_version_flag_prints_the_package_metadata_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0, result.output
    assert result.output == f"throughline {version('tl-cli')}\n"
    assert re.fullmatch(r"throughline \d+\.\d+\.\d+\n", result.output)


def test_version_flag_does_not_need_a_subcommand_or_a_ledger() -> None:
    result = runner.invoke(app, ["--db", "/nonexistent/dir/tl.db", "--version"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("throughline ")
