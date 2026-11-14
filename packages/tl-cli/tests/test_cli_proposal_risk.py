"""`tl proposal accept --accept-risk`: the person takes the risk of a dangerous setting (D3)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget, open_uow
from tl_cli.main import app
from tl_core import settings
from tl_core.auth import accounts
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.queries import find_account
from tl_core.modules import load_modules
from tl_core.services import proposals
from tl_core.services.settings import ChangeSetting
from tl_core.uow import UnitOfWork
from typer.testing import CliRunner

runner = CliRunner()
AGENT = "agent:triage"


PROJECTS = ("project:P123", "project:P1", "project:P2", "project:P999")


def grant_filing(uow: UnitOfWork, name: str, projects: tuple[str, ...] = PROJECTS) -> None:
    """The agent's account (role user) and an explicit ``user`` grant (P2-X2 S1).

    An agent files only where an admin granted it a module role; a role derived from the account
    role does not count."""
    conn = uow.conn()
    view = find_account(conn, username=name)
    if view is None:
        view = accounts.create_account(
            uow, username=name, display_name=name, kind="agent",
            roles=["user"], password=None, by="svc:test",
        )  # fmt: skip
    if find_account(conn, username="gadmin") is None:
        accounts.create_account(
            uow, username="gadmin", display_name="gadmin", kind="person",
            roles=["admin"], password=None, by="svc:test",
        )  # fmt: skip
    targets = [(p, "*") for p in projects]
    targets += [("company", s.name) for s in load_modules() if s.company_roles][:1]
    for project, module in targets:
        grant_module_role(
            uow,
            GrantModuleRole(
                actor="user:gadmin", source="test", scope="company", account_id=view.account_id,
                project=project, module=module, role="user", reason="test",
            ),
        )  # fmt: skip


def ensure_agent(db: str) -> None:
    """The agent's account (role user): an agent files only where it holds a module role."""
    with open_uow(db) as uow:
        grant_filing(uow, "triage")


@pytest.fixture
def env(
    new_db: Callable[[], DbTarget], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[dict[str, str]]:
    monkeypatch.delenv("TL_AGENT_DAILY_PROPOSALS", raising=False)
    values = {"TL_DB": str(new_db())}
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
        return open_uow(env["TL_DB"], readonly=readonly)

    ensure_agent(env["TL_DB"])
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
    with open_uow(env["TL_DB"], readonly=True) as uow:
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
        return open_uow(env["TL_DB"], readonly=readonly)

    ensure_agent(env["TL_DB"])
    pid = proposals.submit(
        factory, tool="propose_setting_change", agent=AGENT, command=command, summary="vim for bob"
    ).proposal_id
    shown = runner.invoke(app, ["proposal", "show", pid], env=env).stdout
    assert "owner bob" in shown.splitlines() and "current default" in shown.splitlines()
    listed = runner.invoke(app, ["proposal", "ls", "--company"], env=env).stdout
    assert "[" not in listed  # a normal-risk change carries no risk tag
