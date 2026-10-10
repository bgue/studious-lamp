"""``tl sim`` is mounted on the root app with its six subcommands."""

from __future__ import annotations

from tl_cli.main import app
from typer.testing import CliRunner


def test_tl_sim_lists_its_subcommands() -> None:
    result = CliRunner().invoke(app, ["sim", "--help"])
    assert result.exit_code == 0 and result.exception is None
    for name in ("create", "advance", "inject", "status", "assert", "run", "seed"):
        assert name in result.stdout
