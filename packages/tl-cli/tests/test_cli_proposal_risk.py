"""`tl proposal accept --accept-risk`: the person takes the risk of a dangerous setting (D3)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_adapters.sqlite.uow import open_uow
from tl_cli.main import app
from tl_core import settings
from tl_core.services import proposals
from tl_core.services.settings import ChangeSetting
from typer.testing import CliRunner

runner = CliRunner()
AGENT = "agent:triage"


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    monkeypatch.delenv("TL_AGENT_DAILY_PROPOSALS", raising=False)
    values = {"TL_DB": str(tmp_path / "tl.db")}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    yield values


def propose(env: dict[str, str]) -> str:
    command = ChangeSetting(
        actor=AGENT,
        source="mcp:triage",
        scope="company",
        key="webhooks.egress.allowlist",
        layer="company",
        value=["hub.example.com"],
        reason="partner hub",
    )

    def factory(readonly: bool = False):  # type: ignore[no-untyped-def]
        return open_uow(Path(env["TL_DB"]), readonly=readonly)

    return proposals.submit(
        factory, tool="propose_setting_change", agent=AGENT, command=command, summary="Allow hub"
    ).proposal_id


def test_a_dangerous_proposal_needs_the_flag_and_stays_pending(env: dict[str, str]) -> None:
    pid = propose(env)
    refused = runner.invoke(app, ["proposal", "accept", pid], env=env)
    assert refused.exit_code == 1 and "accept the risk" in refused.stderr
    pending = runner.invoke(app, ["proposal", "ls", "--company"], env=env)
    assert pid in pending.stdout  # still in the queue
    done = runner.invoke(app, ["proposal", "accept", pid, "--accept-risk"], env=env)
    assert done.exit_code == 0 and done.stdout.startswith(f"accepted {pid}")
    with open_uow(Path(env["TL_DB"]), readonly=True) as uow:
        assert settings.value_of(uow.conn(), "webhooks.egress.allowlist") == ["hub.example.com"]


def test_ls_and_show_tell_the_person_what_a_setting_proposal_changes(env: dict[str, str]) -> None:
    pid = propose(env)
    listed = runner.invoke(app, ["proposal", "ls", "--company"], env=env)
    assert listed.stdout.strip().endswith("Allow hub  [dangerous]")
    shown = runner.invoke(app, ["proposal", "show", pid], env=env).stdout.splitlines()
    tail = shown[shown.index("setting webhooks.egress.allowlist at company") :]
    assert tail == [
        "setting webhooks.egress.allowlist at company",
        "current []",
        "proposed [hub.example.com]",
        "risk dangerous",
        "effect live",
    ]


def test_a_user_layer_proposal_names_whose_preference_it_changes(env: dict[str, str]) -> None:
    command = ChangeSetting(
        actor=AGENT,
        source="mcp:triage",
        scope="company",
        key="ui.tui.keymap",
        layer="user:bob",
        value="vim",
    )

    def factory(readonly: bool = False):  # type: ignore[no-untyped-def]
        return open_uow(Path(env["TL_DB"]), readonly=readonly)

    pid = proposals.submit(
        factory, tool="propose_setting_change", agent=AGENT, command=command, summary="vim for bob"
    ).proposal_id
    shown = runner.invoke(app, ["proposal", "show", pid], env=env).stdout
    assert "owner bob" in shown.splitlines() and "current default" in shown.splitlines()
    listed = runner.invoke(app, ["proposal", "ls", "--company"], env=env).stdout
    assert "[" not in listed  # a normal-risk change carries no risk tag
