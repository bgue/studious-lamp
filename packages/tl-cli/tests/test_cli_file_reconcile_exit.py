"""`tl file reconcile` exit codes on a clean store (P0-I4-B).

CliRunner returns an exception on the result instead of raising it, so a test that only checks
"nothing changed" would pass against a command that crashes. This one asserts the exit code.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tl_adapters.db import DbTarget
from tl_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


def test_an_empty_ledger_and_store_reconcile_with_exit_zero(
    new_db: Callable[[], DbTarget], tmp_path: Path
) -> None:
    env = {
        "TL_DB": str(new_db()),
        "TL_OBJECT_ROOT": str(tmp_path / "objects"),
        "TL_ENV": "dev",
    }
    assert runner.invoke(app, ["init"], env=env).exit_code == 0
    for args in (["file", "reconcile"], ["file", "reconcile", "--verify"]):
        result = runner.invoke(app, args, env=env)
        assert result.exit_code == 0, result.output
        assert result.exception is None
        assert "checked 0" in result.stdout.splitlines()
