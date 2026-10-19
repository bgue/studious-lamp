"""The MCP server is identified by an agent token that is checked on every call (P1-I0-T10)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from mcp_harness import McpHarness
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_api.auth import Forbidden
from tl_core.auth import accounts, sessions
from tl_core.auth.errors import ForbiddenError, InvalidCredentialsError
from tl_core.auth.password import prepare_password
from tl_core.auth.provider import RoleAuthorizer
from tl_core.auth.tokens import token_kind
from tl_core.auth.types import Principal
from tl_mcp.identity import (
    MCP_ACTIONS,
    AgentTokenError,
    resolve_agent,
    token_authorizer,
    token_from_env,
)
from tl_mcp.main import main, parse_args
from tl_mcp.server import build_server

try:
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # pragma: no cover
    from mcp.server.mcpserver import ToolError  # type: ignore[attr-defined,no-redef]

GOOD = "correct horse battery"


class Setup:
    """A ledger with a person, an agent `triage` and its token."""

    def __init__(self, root: Path) -> None:
        self.harness = McpHarness.build(root)
        self.factory: SqliteUowFactory = self.harness.factory
        with self.factory(False) as uow:
            self.admin = accounts.create_account(
                uow, username="boss", display_name="Boss", kind="person", roles=["admin"],
                password=prepare_password(GOOD), by="svc:test",
            )  # fmt: skip
            self.bot = accounts.create_account(
                uow, username="triage", display_name="Triage", kind="agent", roles=["user"],
                password=None, by="svc:test",
            )  # fmt: skip
            view, self.token = accounts.issue_agent_token(
                uow, account_id=self.bot.account_id, label="t",
                expires_at=datetime.now(UTC) + timedelta(days=1), by="svc:test",
            )  # fmt: skip
            self.token_id = view.token_id
        _, self.session = sessions.sign_in(self.factory, username="boss", password=GOOD)

    def revoke(self) -> None:
        with self.factory(False) as uow:
            accounts.revoke_agent_token(uow, token_id=self.token_id, by="user:boss", reason=None)

    def disable_agent(self) -> None:
        with self.factory(False) as uow:
            accounts.disable(uow, account_id=self.bot.account_id, by="user:boss", reason=None)

    def close(self) -> None:
        self.harness.close()


@pytest.fixture
def world(tmp_path: Path):  # type: ignore[no-untyped-def]
    built = Setup(tmp_path)
    yield built
    built.close()


# --- reading the token ---------------------------------------------------------------------------


def test_the_token_comes_from_the_environment_only() -> None:
    token = "tla_" + "x" * 43
    assert token_from_env({"TL_AGENT_TOKEN": f"  {token}\n"}) == token
    with pytest.raises(AgentTokenError, match="set TL_AGENT_TOKEN"):
        token_from_env({})
    with pytest.raises(AgentTokenError, match="set TL_AGENT_TOKEN"):
        token_from_env({"TL_AGENT_TOKEN": "   "})


def test_a_persons_session_token_or_garbage_is_refused_before_any_database_is_opened() -> None:
    for bad in ("tls_" + "x" * 43, "hello", "tla", "Bearer tla_x"):
        with pytest.raises(AgentTokenError, match="must be an agent token") as raised:
            token_from_env({"TL_AGENT_TOKEN": bad})
        if len(bad) > 10:  # the text never carries the token
            assert bad not in str(raised.value)


# --- resolving the agent -------------------------------------------------------------------------


def test_a_valid_token_names_the_agent(world: Setup) -> None:
    principal = resolve_agent(world.factory, world.token)
    assert principal.actor == "agent:triage" and principal.kind == "agent"
    assert principal.via == "agent_token"


def test_a_session_token_is_not_an_agent_token_even_when_it_is_valid(world: Setup) -> None:
    assert token_kind(world.session) == "session"
    with pytest.raises(AgentTokenError) as raised:
        resolve_agent(world.factory, world.session)
    assert world.session not in str(raised.value)


@pytest.mark.parametrize("how", ["revoke", "disable_agent", "unknown"])
def test_a_token_that_is_dead_is_refused_at_start(world: Setup, how: str) -> None:
    token = "tla_" + "z" * 43 if how == "unknown" else world.token
    if how != "unknown":
        getattr(world, how)()
    with pytest.raises(AgentTokenError, match="invalid, expired or revoked") as raised:
        resolve_agent(world.factory, token)
    assert token not in str(raised.value)


# --- the per-call check --------------------------------------------------------------------------


def test_the_hook_allows_an_agent_its_mcp_actions(world: Setup) -> None:
    hook = token_authorizer(world.factory, world.token)
    hook("agent:triage", "mcp.search_records", "scope:project%3AP123")
    hook("agent:triage", "mcp.resource.schema", "schema:x")


@pytest.mark.parametrize("action", ["admin.accounts.list", "record.write", "command.CreateRecord"])
def test_the_hook_refuses_everything_but_mcp_actions_by_default(world: Setup, action: str) -> None:
    hook = token_authorizer(world.factory, world.token)
    with pytest.raises(ForbiddenError):
        hook("agent:triage", action, "x")


def test_a_revoked_token_stops_working_at_the_next_call_not_the_next_start(world: Setup) -> None:
    hook = token_authorizer(world.factory, world.token)
    hook("agent:triage", "mcp.search_records", "x")
    world.revoke()
    with pytest.raises(InvalidCredentialsError, match="invalid or expired token"):
        hook("agent:triage", "mcp.search_records", "x")


def test_a_disabled_agent_stops_at_the_next_call(world: Setup) -> None:
    hook = token_authorizer(world.factory, world.token)
    world.disable_agent()
    with pytest.raises(InvalidCredentialsError):
        hook("agent:triage", "mcp.get_record", "x")


def test_a_hook_for_another_actor_is_refused(world: Setup) -> None:
    hook = token_authorizer(world.factory, world.token)
    with pytest.raises(Forbidden, match="no longer belongs"):
        hook("agent:someone-else", "mcp.search_records", "x")


# --- the allow-list: no prefix rule ---------------------------------------------------------------

RESOURCE_URIS = (
    "tl://record/project:P123/K-1",
    "tl://schema/project:P123/core.Record",
    "tl://relations",
    "tl://lake/schema",
    "tl://types",
    "tl://types/co.acme.LiftPlan",
)


def test_every_registered_tool_and_resource_is_decided_and_nothing_stale_is_listed(
    tmp_path: Path,
) -> None:
    seen: list[str] = []

    def record(actor: str, action: str, resource: str) -> None:
        seen.append(action)
        raise Forbidden("recording")

    harness = McpHarness.build(tmp_path, authorize_hook=record)
    try:
        tools = {f"mcp.{t.name}" for t in asyncio.run(harness.server.list_tools())}
        for uri in RESOURCE_URIS:
            with pytest.raises(Exception, match="not allowed"):
                harness.read(uri)
    finally:
        harness.close()
    resources = set(seen)
    assert resources and all(a.startswith("mcp.resource.") for a in resources)
    assert tools | resources == MCP_ACTIONS, sorted((tools | resources) ^ MCP_ACTIONS)


def test_a_new_tool_is_closed_to_agents_until_it_is_listed(world: Setup) -> None:
    hook = token_authorizer(world.factory, world.token)
    for action in ("mcp.brand_new", "mcp.resource.brand_new", "mcp."):
        with pytest.raises(ForbiddenError, match="not open to agents"):
            hook("agent:triage", action, "x")
    hook("agent:triage", "mcp.search_records", "x")


def test_the_api_side_authorizer_never_opens_mcp_actions_to_an_agent() -> None:
    agent = Principal(
        actor="agent:x", account_id="a", kind="agent", roles=["user"], via="agent_token"
    )
    with pytest.raises(ForbiddenError):
        RoleAuthorizer().authorize(agent, "mcp.search_records", "x")


# --- the server end to end -----------------------------------------------------------------------


def test_a_tool_call_works_with_the_token_and_fails_cleanly_after_revocation(world: Setup) -> None:
    world.harness.create_record("K-1")
    server = build_server(
        world.factory,
        actor="agent:triage",
        authorize_hook=token_authorizer(world.factory, world.token),
        lake_dir=Path(world.harness.db).parent / "lake",
    )
    harness = McpHarness(world.harness.db, world.factory, server)
    assert harness.call("search_records", scope="project:P123")
    world.revoke()
    with pytest.raises(ToolError, match="invalid or expired token") as raised:
        harness.call("search_records", scope="project:P123")
    assert world.token not in str(raised.value)
    with pytest.raises(Exception, match="invalid or expired token"):
        harness.read("tl://relations")


# --- the entry point -----------------------------------------------------------------------------


def test_actor_is_no_longer_an_option_and_says_what_to_do(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TL_AGENT_TOKEN", "tla_" + "a" * 43)
    assert main(["--actor", "agent:triage", "--db", str(tmp_path / "x.db")]) == 2
    err = capsys.readouterr().err
    assert (
        "--actor was removed" in err and "TL_AGENT_TOKEN" in err and "tl admin token issue" in err
    )
    assert "--actor" not in parse_args([]).__dict__ or parse_args([]).actor is None


def test_the_entry_point_needs_a_token_and_a_ledger_and_a_live_token(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    world = Setup(tmp_path)
    try:
        db = str(world.harness.db)
        monkeypatch.delenv("TL_AGENT_TOKEN", raising=False)
        assert main(["--db", db]) == 2
        assert "set TL_AGENT_TOKEN" in capsys.readouterr().err
        monkeypatch.setenv("TL_AGENT_TOKEN", world.session)
        assert main(["--db", db]) == 2
        err = capsys.readouterr().err
        assert "must be an agent token" in err and world.session not in err
        monkeypatch.setenv("TL_AGENT_TOKEN", world.token)
        assert main(["--db", str(tmp_path / "none.db")]) == 2
        assert "tl init" in capsys.readouterr().err
        world.revoke()
        assert main(["--db", db]) == 2
        err = capsys.readouterr().err
        assert "invalid, expired or revoked" in err and world.token not in err
    finally:
        world.close()


def test_write_mode_is_refused_before_the_token_is_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TL_AGENT_TOKEN", raising=False)
    assert main(["--db", str(tmp_path / "x.db"), "--tool-mode", "create_record=write"]) == 2
    assert "human gate" in capsys.readouterr().err


def test_no_agent_action_is_a_controlling_act(world: Setup) -> None:
    """ADR-0013: an agent proposes and never controls, and no list can open a `control.*` action."""
    from tl_core.auth.provider import AGENT_ACTIONS

    assert not [a for a in AGENT_ACTIONS | MCP_ACTIONS if a.startswith(("control.", "admin."))]
    hook = token_authorizer(world.factory, world.token)
    for action in (
        "control.command.IssueRevision",
        "control.command.IssueTransmittal",
        "control.command.OverrideReviewOutcome",
    ):
        with pytest.raises(ForbiddenError):
            hook("agent:triage", action, "x")
