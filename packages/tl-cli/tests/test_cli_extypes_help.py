"""`tl types --help` reads as help for a person, not as implementation notes (P0-I8)."""

from __future__ import annotations

import pytest
from tl_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()
LEAKS = (
    "``",
    "_service_errors",
    "_fail",
    "registry.",
    "sync_lines",
    "open_uow",
    "make_object_store",
)
COMMANDS = [
    [],
    ["sync"],
    ["ls"],
    ["show"],
    ["validate"],
    ["lock"],
    ["deprecate"],
    ["watch"],
    ["quarantine"],
    ["quarantine", "ls"],
    ["quarantine", "recheck"],
]


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: " ".join(c) or "types")
def test_help_names_no_internal_function(command: list[str]) -> None:
    result = runner.invoke(app, ["types", *command, "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    for leak in LEAKS:
        assert leak not in result.stdout, f"{leak!r} in `tl types {' '.join(command)} --help`"
