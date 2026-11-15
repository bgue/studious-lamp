"""P2-X2-S3: the agent stop switch (commands, filing and accept checks, filtered reads)."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, make_uow_factory, open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.auth import accounts
from tl_core.auth.errors import AccountNotFoundError, ForbiddenError
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.queries import find_account
from tl_core.modules import ConfidentialSource
from tl_core.proposals.types import ProposalView
from tl_core.services import agent_stop
from tl_core.services.agent_stop import (
    ADMIN_ONLY_TEXT,
    STOPPED_TEXT,
    UNKNOWN_TEXT,
    AgentStopResult,
    ResumeAgent,
    StopAgent,
    handle_resume_agent,
    handle_stop_agent,
    held_count,
    is_stopped,
    list_stopped,
    require_not_stopped,
)
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.links import AddLink
from tl_core.services.proposals import accept_or_fail, accept_proposal, propose, submit
from tl_core.services.records import handle_create_record

_AUTH = str(Path(__file__).resolve().parents[3] / "tests" / "auth")
if _AUTH not in sys.path:
    sys.path.insert(0, _AUTH)

from authworld import MovingClock, World  # noqa: E402

SCOPE = "project:P1"
BOT = "agent:bot"
ADA = "user:ada"
TABLE = "agent_stop_class"
EVENT_SQL = "SELECT seq, event_id, event_type, stream_id, actor, payload FROM events ORDER BY seq"


class Env:
    def __init__(self, db: DbTarget, *, bare: bool = False) -> None:
        self.db = db
        self.factory = make_uow_factory(db)
        self.world = World(db, self.factory, MovingClock())
        self.world.create("ada", roles=("admin",))
        self.world.create("bob", roles=("user",))
        self.world.create("gadmin", roles=("admin",))
        self.world.create("bot", kind="agent")
        self.world.create("idle", kind="agent")
        for agent in ("bot", "idle"):  # P2-X2 S1: an agent files only on an explicit grant
            self.grant_filing(agent)
        self.n = 0
        self.anchor = "" if bare else self.create_record("ANCHOR")

    def grant_filing(self, name: str) -> None:
        with self.factory() as uow:
            account = find_account(uow.conn(), username=name)
            assert account is not None
            grant_module_role(
                uow,
                GrantModuleRole(
                    actor="user:gadmin", source="test", scope="company",
                    account_id=account.account_id, project=SCOPE, module="*",
                    role="user", reason="test",
                ),
            )  # fmt: skip

    def stop(
        self, actor: str = ADA, agent: str = BOT, reason: str | None = None
    ) -> AgentStopResult:
        with self.factory() as uow:
            return handle_stop_agent(
                uow,
                StopAgent(actor=actor, source="test", scope="company", agent=agent, reason=reason),
            )

    def resume(self, actor: str = ADA, agent: str = BOT) -> AgentStopResult:
        with self.factory() as uow:
            return handle_resume_agent(
                uow, ResumeAgent(actor=actor, source="test", scope="company", agent=agent)
            )

    def create_record(self, key: str) -> str:
        with self.factory() as uow:
            made = handle_create_record(
                uow,
                CreateRecord(actor="user:bob", source="test", scope=SCOPE,
                             record_type="core.Record", title=key, key=key),
            )  # fmt: skip
        return str(made.stream_id)

    def file(self, agent: str = BOT, *, key: str | None = None, budget: int = 50) -> ProposalView:
        self.n += 1
        cmd = CreateRecord(
            actor=agent, source="mcp:x", scope=SCOPE, record_type="core.Record",
            title=f"p{self.n}", key=key or f"K-{self.n}",
        )  # fmt: skip
        return submit(
            self.factory, tool="create_record", agent=agent, command=cmd,
            summary="Create a record", budget=budget,
        )  # fmt: skip

    def file_link(self, agent: str, from_id: str, to_id: str) -> ProposalView:
        cmd = AddLink(actor=agent, source="mcp:x", scope=SCOPE, from_id=from_id, to_id=to_id)
        return submit(
            self.factory, tool="link_records", agent=agent, command=cmd,
            summary="Link two records", budget=50,
        )  # fmt: skip

    def accept(self, proposal_id: str) -> ProposalView:
        with self.factory() as uow:
            return accept_proposal(uow, proposal_id=proposal_id, by=ADA)

    def held(self, agent: str) -> int:
        with self.factory(readonly=True) as uow:
            return held_count(uow.conn(), agent, cf.Viewer(actor=ADA, level=1, account=ADA))

    def rows(self, sql: str, **params: object) -> list[tuple[object, ...]]:
        return self.world.rows(sql, **params)

    def events(self) -> list[tuple[object, ...]]:
        return self.rows(EVENT_SQL)

    def types(self) -> list[str]:
        return [str(r[2]) for r in self.events() if str(r[2]).startswith("Agent.")]

    def status(self, proposal_id: str) -> str:
        return str(
            self.rows("SELECT status FROM cur_proposals WHERE proposal_id = :p", p=proposal_id)[0][
                0
            ]
        )


@pytest.fixture
def env(db: DbTarget) -> Iterator[Env]:
    made = Env(db)
    try:
        yield made
    finally:
        made.factory.dispose()


# 1. stop holds filing and accept; resume lifts both; nothing is rewritten -------------------------


def test_stop_refuses_filing_and_accept_and_resume_lifts_both(env: Env) -> None:
    pending = env.file()
    before = env.events()
    assert env.stop(reason="wrong packages").changed is True
    with pytest.raises(ForbiddenError) as filing:
        env.file()
    assert str(filing.value) == STOPPED_TEXT
    with pytest.raises(ForbiddenError) as accept:
        env.accept(pending.proposal_id)
    assert str(accept.value) == STOPPED_TEXT
    assert env.status(pending.proposal_id) == "pending"  # held, not rejected
    assert env.resume().changed is True
    env.file()  # filing is open again
    assert env.accept(pending.proposal_id).status == "accepted"
    assert env.types() == ["Agent.Stopped", "Agent.Resumed"]
    assert env.events()[: len(before)] == before  # nothing before was rewritten


def test_accept_or_fail_of_a_stopped_agent_is_a_plain_refusal_and_the_proposal_stays_held(
    env: Env,
) -> None:
    pending = env.file()
    other = env.file()
    env.stop()
    before, held = env.events(), env.held(BOT)
    assert held == 2
    with pytest.raises(ForbiddenError) as refused:
        accept_or_fail(env.factory, proposal_id=pending.proposal_id, by=ADA)
    assert str(refused.value) == STOPPED_TEXT
    assert env.events() == before  # no Proposal.Failed, nothing appended
    assert env.status(pending.proposal_id) == env.status(other.proposal_id) == "pending"
    assert env.held(BOT) == held
    env.resume()
    assert accept_or_fail(env.factory, proposal_id=pending.proposal_id, by=ADA).status == "accepted"


def test_submit_of_a_stopped_agent_is_refused_before_the_dry_run(env: Env) -> None:
    env.file()
    ghost = "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA"
    with pytest.raises(RecordNotFoundError):  # a running agent learns from the dry run
        env.file_link(BOT, ghost, ghost)
    env.stop()
    with pytest.raises(ForbiddenError) as err:  # a stopped one never gets that far
        env.file_link(BOT, ghost, ghost)
    assert str(err.value) == STOPPED_TEXT


def test_propose_is_refused_before_the_budget(env: Env) -> None:
    env.file()
    env.stop()
    with env.factory() as uow, pytest.raises(ForbiddenError) as err:
        propose(
            uow, tool="create_record", agent=BOT, summary="x", budget=0,
            command=CreateRecord(actor=BOT, source="mcp:x", scope=SCOPE,
                                 record_type="core.Record", title="t", key="Z-1"),
        )  # fmt: skip
    assert str(err.value) == STOPPED_TEXT  # not the budget text: the stop check runs first


def test_the_stop_is_per_agent(env: Env) -> None:
    env.file()
    env.stop()
    env.file("agent:idle")  # another agent still files


def test_the_stop_event_carries_ids_and_a_short_reason(env: Env) -> None:
    env.file()
    env.stop(reason="why")
    env.resume()
    rows = [r for r in env.events() if str(r[2]).startswith("Agent.")]
    assert [str(r[2]) for r in rows] == ["Agent.Stopped", "Agent.Resumed"]
    assert all(str(r[3]).startswith("account:") and r[4] == ADA for r in rows)
    assert '"reason":"why"' in str(rows[0][5]).replace(" ", "")
    assert "reason" not in str(rows[1][5])


def test_account_commands_still_work_after_a_stop(env: Env) -> None:
    env.file()
    env.stop()
    env.resume()
    bot_id = str(env.rows("SELECT account_id FROM cur_account WHERE username = 'bot'")[0][0])
    version = int(
        str(env.rows("SELECT version FROM cur_account WHERE account_id = :a", a=bot_id)[0][0])
    )
    head = int(str(env.rows("SELECT MAX(stream_version) FROM events WHERE stream_id = :s",
                        s=f"account:{bot_id}")[0][0]))  # fmt: skip
    assert version == head  # the stop events moved the account row's version with the stream
    with env.factory() as uow:
        accounts.disable(uow, account_id=bot_id, by=ADA, reason=None)


# 2. who may stop -----------------------------------------------------------------------------


def test_an_agent_actor_cannot_stop_or_resume(env: Env) -> None:
    env.file()
    for actor in ("agent:bot", "agent:idle", "agent:ada"):  # agent:ada borrows the admin's name
        with pytest.raises(ForbiddenError) as err:
            env.stop(actor=actor)
        assert str(err.value) == ADMIN_ONLY_TEXT
    env.stop()
    with pytest.raises(ForbiddenError):
        env.resume(actor="agent:bot")
    assert is_stopped_now(env)


def is_stopped_now(env: Env) -> bool:
    with open_uow(env.db, readonly=True) as uow:
        return is_stopped(uow.conn(), BOT)


def test_a_non_admin_person_cannot_stop_or_resume(env: Env) -> None:
    env.file()
    with pytest.raises(ForbiddenError):
        env.stop(actor="user:bob")
    env.stop()
    with pytest.raises(ForbiddenError):
        env.resume(actor="user:bob")
    assert is_stopped_now(env)


def test_an_unknown_actor_cannot_stop(env: Env) -> None:
    with pytest.raises(ForbiddenError):
        env.stop(actor="user:nobody")


def test_an_admin_can_and_a_double_stop_or_resume_writes_nothing(env: Env) -> None:
    env.file()
    assert env.resume().changed is False  # running: quiet no-op
    assert env.types() == []
    assert env.stop().changed is True
    again = env.stop()
    assert again.changed is False and again.events == []
    assert env.resume().changed is True
    assert env.resume().changed is False
    assert env.types() == ["Agent.Stopped", "Agent.Resumed"]


# 3 (restop after resume appends again) ----------------------------------------------------------


def test_a_second_stop_after_a_resume_stops_again(env: Env) -> None:
    env.file()
    env.stop()
    env.resume()
    assert env.stop().changed is True
    assert is_stopped_now(env)
    assert env.types() == ["Agent.Stopped", "Agent.Resumed", "Agent.Stopped"]


# 5. is_stopped alone agrees with require_not_stopped ---------------------------------------------


def test_is_stopped_is_callable_alone_and_agrees_with_require(env: Env) -> None:
    env.file()
    for stopped in (False, True, False):
        if stopped:
            env.stop()
        elif env.types():
            env.resume()
        with open_uow(env.db, readonly=True) as uow:
            conn = uow.conn()
            assert is_stopped(conn, BOT) is stopped
            if stopped:
                with pytest.raises(ForbiddenError):
                    require_not_stopped(conn, BOT)
            else:
                require_not_stopped(conn, BOT)
            assert is_stopped(conn, "agent:never-heard-of") is False
    assert agent_stop.is_stopped.__module__ == "tl_core.services.agent_stop"


# 6. unknown agents: one text, no oracle ----------------------------------------------------------


@pytest.mark.parametrize("agent", ["agent:idle", "agent:ghost", "agent:", "ghost", "user:bob", ""])
def test_an_unknown_or_never_filed_agent_is_refused_with_one_text(env: Env, agent: str) -> None:
    env.file()
    with pytest.raises(AccountNotFoundError) as stop:
        env.stop(agent=agent)
    with pytest.raises(AccountNotFoundError) as resume:
        env.resume(agent=agent)
    assert str(stop.value) == str(resume.value) == UNKNOWN_TEXT
    assert env.types() == []


# 4. held_count and list_stopped as five kinds of reader ------------------------------------------

READERS = {
    "user": cf.Viewer(actor="user:bob", level=0, account="user:bob"),
    "controller": cf.Viewer(actor="user:ctl", level=1, account="user:ctl"),
    "admin": cf.Viewer(actor=ADA, level=1, account=ADA),
    "named": cf.Viewer(actor="user:amy", level=0, account="user:amy"),
    "agent": cf.Viewer(actor=BOT, level=0, account=""),
}
READS = {"restricted": {"controller", "admin"}, "privileged": {"named"}}


def make_class_tables(db: DbTarget) -> None:
    with open_uow(db) as uow:
        uow.conn().execute(text(f"CREATE TABLE {TABLE} (id TEXT PRIMARY KEY, cls TEXT NOT NULL)"))
        uow.conn().execute(text(f"CREATE TABLE {TABLE}_clear (record_id TEXT, account TEXT)"))


@pytest.fixture
def classed(monkeypatch: pytest.MonkeyPatch, env: Env) -> Iterator[Env]:
    make_class_tables(env.db)
    source = ConfidentialSource(
        record_types=frozenset({"core.Record"}), table=TABLE, id_column="id", class_column="cls",
        clearance_table=f"{TABLE}_clear",
    )  # fmt: skip
    real = core_modules.confidential_sources
    monkeypatch.setattr(cf, "confidential_sources", lambda: [*real(), source])
    classify(env, env.anchor, "internal")
    yield env


def classify(env: Env, record_id: str, cls: str) -> None:
    with open_uow(env.db) as uow:
        conn = uow.conn()
        conn.execute(text(f"DELETE FROM {TABLE} WHERE id = :i"), {"i": record_id})
        conn.execute(
            text(f"INSERT INTO {TABLE} (id, cls) VALUES (:i, :c)"), {"i": record_id, "c": cls}
        )
        conn.execute(text(f"DELETE FROM {TABLE}_clear"))
        conn.execute(
            text(f"INSERT INTO {TABLE}_clear (record_id, account) VALUES (:i, 'user:amy')"),
            {"i": record_id},
        )


def held_as(env: Env, reader: str, agent: str = BOT) -> int:
    with open_uow(env.db, readonly=True) as uow:
        return held_count(uow.conn(), agent, READERS[reader])


def stopped_as(env: Env, reader: str, *, limit: int = 200) -> list[agent_stop.StoppedAgent]:
    with open_uow(env.db, readonly=True) as uow:
        return list_stopped(uow.conn(), READERS[reader], limit=limit)


@pytest.mark.parametrize("cls", ["restricted", "privileged"])
def test_a_hidden_record_in_a_held_proposal_is_not_counted(classed: Env, cls: str) -> None:
    env = classed
    plain = env.file()
    hidden_id = env.create_record("H-1")
    classify(env, hidden_id, "internal")
    carrying = env.file_link(BOT, env.anchor, hidden_id)
    env.stop()
    for reader in READERS:  # readable while internal: everyone counts 2
        assert held_as(env, reader) == 2
    classify(env, hidden_id, cls)
    for reader in READERS:
        want = 2 if reader in READS[cls] else 1
        assert held_as(env, reader) == want, reader
        assert [a.held for a in stopped_as(env, reader)] == [want], reader
        assert hidden_id not in str(stopped_as(env, reader))
    assert plain.proposal_id and carrying.proposal_id


def test_counts_equal_a_world_where_the_record_never_existed(
    classed: Env, new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch
) -> None:
    env = classed
    env.file()
    hidden_id = env.create_record("H-2")
    classify(env, hidden_id, "internal")
    env.file_link(BOT, env.anchor, hidden_id)
    env.stop()
    classify(env, hidden_id, "restricted")
    from tl_adapters.db import create_schema

    other_db = new_db()
    create_schema(other_db)
    make_class_tables(other_db)
    other = Env(other_db, bare=True)
    try:
        other.file()  # the same world without the hidden record or its proposal
        other.stop()
        for reader in ("user", "agent", "named"):
            with open_uow(other.db, readonly=True) as uow:
                never = held_count(uow.conn(), BOT, READERS[reader])
                listed = [a.held for a in list_stopped(uow.conn(), READERS[reader])]
            assert (held_as(env, reader), [a.held for a in stopped_as(env, reader)]) == (
                never,
                listed,
            )
    finally:
        other.factory.dispose()


def test_the_filter_runs_before_the_limit(classed: Env) -> None:
    env = classed
    env.file()  # oldest and plainly readable
    hidden_ids = []
    for i in range(3):
        rid = env.create_record(f"H-L{i}")
        classify_open(env, rid)
        hidden_ids.append(rid)
        env.file_link(BOT, env.anchor, rid)
    env.stop()
    for rid in hidden_ids:
        classify(env, rid, "restricted")
    assert held_as(env, "user") == 1  # three hidden rows do not eat the count
    assert [a.held for a in stopped_as(env, "user", limit=1)] == [1]
    assert held_as(env, "controller") == 4


def classify_open(env: Env, rid: str) -> None:
    classify(env, rid, "internal")


def test_list_stopped_names_stopped_agents_only(classed: Env) -> None:
    env = classed
    env.file()
    env.file("agent:idle")
    env.stop()
    listed = stopped_as(env, "user")
    assert [(a.agent, a.stopped_by, a.held) for a in listed] == [(BOT, ADA, 1)]
    env.resume()
    assert stopped_as(env, "user") == []
