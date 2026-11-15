"""P2-X2-S2: the pending-queue cap (setting, viewer-filtered count, fixed refusal text)."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, make_uow_factory, open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.queries import find_account
from tl_core.integration.actor_access import viewer_of
from tl_core.modules import ConfidentialSource, load_modules
from tl_core.proposals.types import ProposalView
from tl_core.services import agent_scope
from tl_core.services.agent_scope import QUEUE_FULL_TEXT, pending_visible_count
from tl_core.services.agent_stop import StopAgent, handle_stop_agent
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import QueueFullError, RecordNotFoundError
from tl_core.services.links import AddLink
from tl_core.services.proposals import (
    accept_proposal,
    proposals_today,
    propose,
    reject_proposal,
    submit,
)
from tl_core.services.records import handle_create_record
from tl_core.services.settings import ChangeSetting, handle_change_setting

_AUTH = str(Path(__file__).resolve().parents[3] / "tests" / "auth")
if _AUTH not in sys.path:
    sys.path.insert(0, _AUTH)

from authworld import MovingClock, World  # noqa: E402

P1, P2 = "project:P1", "project:P2"
BOT, BOT2, NOGRANT = "agent:bot", "agent:bot2", "agent:nogrant"
ADA = "user:ada"
TABLE = "queue_cap_class"
KEY = "ai.agents.max_pending_per_project"
EVENTS = "SELECT COUNT(*) FROM events"
KEYS = "SELECT COUNT(*) FROM idempotency_key"


class Env:
    def __init__(self, db: DbTarget) -> None:
        self.db = db
        self.factory = make_uow_factory(db)
        self.world = World(db, self.factory, MovingClock())
        self.world.create("ada", roles=("admin",))
        self.world.create("bob", roles=("user",))
        self.world.create("gadmin", roles=("admin",))
        self.world.create("nogrant", kind="agent")
        for name in ("bot", "bot2"):
            self.world.create(name, kind="agent")
            self.grant(name)
        self.n = 0
        self.anchor = self.create_record("ANCHOR", P1)

    def grant(self, name: str) -> None:
        with self.factory() as uow:
            account = find_account(uow.conn(), username=name)
            assert account is not None
            targets = [(p, "*") for p in (P1, P2)]
            targets += [("company", s.name) for s in load_modules() if s.company_roles][:1]
            for project, module in targets:
                grant_module_role(
                    uow,
                    GrantModuleRole(
                        actor="user:gadmin", source="test", scope="company",
                        account_id=account.account_id, project=project, module=module,
                        role="user", reason="test",
                    ),
                )  # fmt: skip

    def create_record(self, key: str, scope: str = P1) -> str:
        with self.factory() as uow:
            made = handle_create_record(
                uow,
                CreateRecord(actor="user:bob", source="test", scope=scope,
                             record_type="core.Record", title=key, key=key),
            )  # fmt: skip
        return str(made.stream_id)

    def limit(self, value: int, layer: str = "project:P1") -> None:
        scope = layer if layer.startswith("project:") else "company"
        with self.factory() as uow:
            handle_change_setting(
                uow,
                ChangeSetting(actor=ADA, source="test", scope=scope, key=KEY, layer=layer,
                              value=value, reason="test", accept_risk=True),
            )  # fmt: skip

    def cmd(self, agent: str, scope: str, key: str | None = None) -> CreateRecord:
        self.n += 1
        return CreateRecord(
            actor=agent, source="mcp:x", scope=scope, record_type="core.Record",
            title=f"p{self.n}", key=f"K-{self.n}", idempotency_key=key,
        )  # fmt: skip

    def file(
        self, agent: str = BOT, scope: str = P1, *, key: str | None = None, budget: int = 500
    ) -> ProposalView:
        return submit(
            self.factory, tool="create_record", agent=agent, command=self.cmd(agent, scope, key),
            summary="Create a record", budget=budget,
        )  # fmt: skip

    def propose(self, agent: str = BOT, scope: str = P1) -> ProposalView:
        with self.factory() as uow:
            return propose(
                uow, tool="create_record", agent=agent, command=self.cmd(agent, scope),
                summary="Create a record", budget=500,
            )  # fmt: skip

    def file_link(self, to_id: str, agent: str = BOT) -> ProposalView:
        cmd = AddLink(actor=agent, source="mcp:x", scope=P1, from_id=self.anchor, to_id=to_id)
        return submit(
            self.factory, tool="link_records", agent=agent, command=cmd,
            summary="Link two records", budget=500,
        )  # fmt: skip

    def count(self, sql: str) -> int:
        return int(self.world.rows(sql)[0][0])

    def today(self, agent: str = BOT) -> int:
        with open_uow(self.db, readonly=True) as uow:
            return proposals_today(uow.conn(), agent)


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    return target


@pytest.fixture
def env(db: DbTarget) -> Iterator[Env]:
    made = Env(db)
    try:
        yield made
    finally:
        made.factory.dispose()


def refused(env: Env, how: str, agent: str = BOT, scope: str = P1) -> QueueFullError:
    with pytest.raises(QueueFullError) as caught:
        env.file(agent, scope) if how == "submit" else env.propose(agent, scope)
    return caught.value


def fill(env: Env, n: int, agent: str = BOT, scope: str = P1) -> list[ProposalView]:
    return [env.file(agent, scope) for _ in range(n)]


# 1. the limit ------------------------------------------------------------------------------------


def test_at_the_limit_refused_one_below_files(env: Env) -> None:
    env.limit(3)
    fill(env, 2)
    assert env.file().proposal_id  # the third: two pending, limit three
    refused(env, "submit")


def test_a_project_value_changes_that_project_only(env: Env) -> None:
    env.limit(1)  # P1 only
    env.file()
    refused(env, "submit")
    fill(env, 3, scope=P2)  # P2 keeps the default (100)


def test_company_scope_uses_the_company_value(env: Env) -> None:
    env.limit(1, "project:P1")  # a project value never governs the company queue
    env.limit(2, "company")
    fill(env, 2, scope="company")
    refused(env, "submit", scope="company")
    env.file()  # P1 is empty and its own limit is 1
    refused(env, "submit")


# 2. fixed text -----------------------------------------------------------------------------------


def test_text_is_fixed_and_carries_no_digit_or_id(env: Env) -> None:
    seen = []
    for project, agent, limit in ((P1, BOT, 1), (P2, BOT2, 2)):
        env.limit(limit, project)
        fill(env, limit, agent, project)
        err = refused(env, "submit", agent, project)
        seen.append(err)
    for err in seen:
        assert str(err) == QUEUE_FULL_TEXT
        assert err.args == (QUEUE_FULL_TEXT,)
        assert not re.search(r"\d", str(err) + repr(err.args))
        for needle in ("P1", "P2", "bot", "agent", "project"):
            assert needle not in str(err)


# 3. both entry points write nothing --------------------------------------------------------------


@pytest.mark.parametrize("how", ["submit", "propose"])
def test_refusal_writes_no_event_key_or_budget(env: Env, how: str) -> None:
    env.limit(1)
    env.file()
    events, keys, today = env.count(EVENTS), env.count(KEYS), env.today()
    with pytest.raises(QueueFullError):
        if how == "submit":
            env.file(key="k-refused-1")
        else:
            with env.factory() as uow:
                propose(
                    uow, tool="create_record", agent=BOT, summary="x", budget=500,
                    command=env.cmd(BOT, P1, "k-refused-1"),
                )  # fmt: skip
    assert (env.count(EVENTS), env.count(KEYS), env.today()) == (events, keys, today)


@pytest.mark.parametrize("how", ["submit", "propose"])
def test_both_entry_points_refuse(env: Env, how: str) -> None:
    env.limit(1)
    env.file()
    assert str(refused(env, how)) == QUEUE_FULL_TEXT


# 4. order ----------------------------------------------------------------------------------------


def test_stopped_agent_gets_the_stop_text(env: Env) -> None:
    env.limit(1)
    env.file()
    with env.factory() as uow:
        handle_stop_agent(uow, StopAgent(actor=ADA, source="test", scope="company", agent=BOT))
    with pytest.raises(ForbiddenError) as err:
        env.file()
    assert "stopped" in str(err.value) and "queue" not in str(err.value)


def test_agent_without_the_word_gets_the_filing_refusal(env: Env) -> None:
    env.limit(1)
    env.file()
    with pytest.raises(RecordNotFoundError):
        env.file(NOGRANT)


def test_replay_answers_when_the_queue_is_full(env: Env) -> None:
    env.limit(2)
    replayed = env.cmd(BOT, P1, "k-replay-1")
    first = submit(
        env.factory, tool="create_record", agent=BOT, command=replayed,
        summary="Create a record", budget=500,
    )  # fmt: skip
    env.file()
    refused(env, "submit")
    again = submit(
        env.factory, tool="create_record", agent=BOT,
        command=replayed, summary="Create a record", budget=500,
    )  # fmt: skip
    assert again.proposal_id == first.proposal_id


# 5. the viewer filter ----------------------------------------------------------------------------

READERS = {
    "person": cf.Viewer(actor="user:ctl", level=1, account="user:ctl"),
    "agent": cf.Viewer(actor=BOT, level=0, account=""),
}


def make_class_tables(db: DbTarget) -> None:
    with open_uow(db) as uow:
        uow.conn().execute(text(f"CREATE TABLE {TABLE} (id TEXT PRIMARY KEY, cls TEXT NOT NULL)"))
        uow.conn().execute(text(f"CREATE TABLE {TABLE}_clear (record_id TEXT, account TEXT)"))


@pytest.fixture
def classed(monkeypatch: pytest.MonkeyPatch, env: Env) -> Env:
    make_class_tables(env.db)
    source = ConfidentialSource(
        record_types=frozenset({"core.Record"}), table=TABLE, id_column="id", class_column="cls",
        clearance_table=f"{TABLE}_clear",
    )  # fmt: skip
    real = core_modules.confidential_sources
    monkeypatch.setattr(cf, "confidential_sources", lambda: [*real(), source])
    classify(env, env.anchor, "internal")
    return env


def classify(env: Env, record_id: str, cls: str) -> None:
    with open_uow(env.db) as uow:
        conn = uow.conn()
        conn.execute(text(f"DELETE FROM {TABLE} WHERE id = :i"), {"i": record_id})
        conn.execute(
            text(f"INSERT INTO {TABLE} (id, cls) VALUES (:i, :c)"), {"i": record_id, "c": cls}
        )


def test_a_hidden_proposal_is_not_counted_and_equals_a_world_without_it(
    classed: Env, new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch
) -> None:
    env = classed
    env.limit(3)
    hidden_id = env.create_record("H-1")
    classify(env, hidden_id, "internal")
    env.file_link(hidden_id)  # carries the record while it is readable
    classify(env, hidden_id, "restricted")
    fill(env, 2)
    assert env.file().proposal_id  # 2 visible + 1 hidden pending, limit 3: files
    refused(env, "submit")  # now 3 visible
    other_db = new_db()
    create_schema(other_db)
    make_class_tables(other_db)
    other = Env(other_db)
    try:
        other.limit(3)
        fill(other, 2)
        assert other.file().proposal_id  # the world where the hidden proposal never existed
        refused(other, "submit")
    finally:
        other.factory.dispose()


def test_visible_only_queue_counts_the_same_for_person_and_agent(classed: Env) -> None:
    env = classed
    fill(env, 2)
    with open_uow(env.db, readonly=True) as uow:
        counts = {r: pending_visible_count(uow.conn(), P1, v) for r, v in READERS.items()}
        assert counts == {"person": 2, "agent": 2}
        assert viewer_of(uow.conn(), BOT).level == 0


def test_the_filter_runs_over_every_row(classed: Env) -> None:
    env = classed
    env.limit(2)
    for i in range(3):
        rid = env.create_record(f"H-L{i}")
        classify(env, rid, "internal")
        env.file_link(rid)
        classify(env, rid, "restricted")
    env.file()  # three hidden rows must not make the queue look full
    assert env.file().proposal_id
    refused(env, "submit")


# 6. reopen, other scopes -------------------------------------------------------------------------


def test_accept_and_reject_reopen_the_queue(env: Env) -> None:
    env.limit(2)
    first, second = fill(env, 2)
    refused(env, "submit")
    with env.factory() as uow:
        accept_proposal(uow, proposal_id=first.proposal_id, by=ADA)
    env.file()
    refused(env, "submit")
    with env.factory() as uow:
        reject_proposal(uow, proposal_id=second.proposal_id, by=ADA, reason="no")
    env.file()
    refused(env, "submit")


def test_other_scopes_do_not_count(env: Env) -> None:
    env.limit(2)
    fill(env, 5, scope=P2)
    fill(env, 3, scope="company")
    fill(env, 1)
    assert env.file().proposal_id
    refused(env, "submit")


def test_the_cap_function_is_the_one_wired(env: Env) -> None:
    env.limit(1)
    env.file()
    with open_uow(env.db, readonly=True) as uow, pytest.raises(QueueFullError):
        agent_scope.check_queue_cap(uow.conn(), BOT, env.cmd(BOT, P1))


def test_submit_refuses_before_the_dry_run(env: Env) -> None:
    env.limit(1)
    env.file()
    ghost = "01J9Z6Q4W3X2Y1V0T9S8R7Q6PA"
    cmd = AddLink(actor=BOT, source="mcp:x", scope=P1, from_id=ghost, to_id=ghost)
    with pytest.raises(QueueFullError):  # not the dry run's "no record" answer
        submit(
            env.factory, tool="link_records", agent=BOT, command=cmd,
            summary="Link", budget=500,
        )  # fmt: skip
