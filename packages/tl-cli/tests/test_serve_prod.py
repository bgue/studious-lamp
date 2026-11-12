"""`tl serve` bind rule (P2-REL-S2): the help line and the refusal outside a deployment."""

from __future__ import annotations

import pytest
from tl_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("TL_TOKENS", "TL_DB", "TL_NODE_KIND"):
        monkeypatch.delenv(name, raising=False)


def test_serve_help_shows_the_rule_in_one_line() -> None:
    result = runner.invoke(app, ["serve", "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if "TL_ENV=prod" in line]
    assert lines and any("--insecure-dev" in line for line in lines)


def test_a_non_loopback_host_without_tl_env_exits_2_with_the_new_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TL_ENV", raising=False)
    result = runner.invoke(app, ["serve", "--host", "0.0.0.0"])
    assert result.exit_code == 2
    text = result.output
    assert "TLS proxy" in text and "TL_ENV" in text and "Phase 0" not in text
