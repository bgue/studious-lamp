"""An agent actor cannot run a `tl config` write command (P0-I8 decision D3)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import typer
from tl_cli.actors import refuse_agent
from tl_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def env(tmp_path: Path) -> Iterator[dict[str, str]]:
    values = {"TL_DB": str(tmp_path / "tl.db")}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    yield values


def test_a_person_or_a_service_passes_and_an_agent_is_stopped() -> None:
    assert refuse_agent("user:dev") == "user:dev"
    assert refuse_agent("svc:importer") == "svc:importer"
    with pytest.raises(typer.Exit) as stopped:
        refuse_agent("agent:triage")
    assert stopped.value.exit_code == 1


@pytest.mark.parametrize(
    "args",
    [
        ["set", "feed.reactions.enabled", "false", "--company"],
        ["reset", "feed.reactions.enabled", "--company"],
        ["lock", "feed.reactions.enabled", "--reason", "r"],
        ["revert", "feed.reactions.enabled", "--layer", "company", "--seq", "1"],
    ],
)
def test_every_write_command_refuses_an_agent_actor(env: dict[str, str], args: list[str]) -> None:
    result = runner.invoke(app, ["config", *args, "--actor", "agent:triage"], env=env)
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.startswith("error: agent_must_propose: ")
    assert "propose" in result.stderr


def test_import_refuses_an_agent_actor(env: dict[str, str], tmp_path: Path) -> None:
    document = tmp_path / "in.yaml"
    document.write_text("settings: {}\n", encoding="utf-8")
    result = runner.invoke(
        app, ["config", "import", str(document), "--company", "--actor", "agent:x"], env=env
    )
    assert result.exit_code == 1 and result.stderr.startswith("error: agent_must_propose: ")
