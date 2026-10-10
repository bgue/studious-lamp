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


def test_a_dangerous_proposal_needs_the_flag(env: dict[str, str]) -> None:
    refused = runner.invoke(app, ["proposal", "accept", propose(env)], env=env)
    assert refused.exit_code == 1 and "RiskNotAcceptedError" in refused.stderr
    pid = propose(env)
    done = runner.invoke(app, ["proposal", "accept", pid, "--accept-risk"], env=env)
    assert done.exit_code == 0 and done.stdout.startswith(f"accepted {pid}")
    with open_uow(Path(env["TL_DB"]), readonly=True) as uow:
        assert settings.value_of(uow.conn(), "webhooks.egress.allowlist") == ["hub.example.com"]
