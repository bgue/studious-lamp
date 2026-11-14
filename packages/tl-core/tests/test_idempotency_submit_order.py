"""P2-X1-S2: ``submit`` answers a filed key before the budget and the dry run."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, make_uow_factory, open_uow
from tl_core.auth import accounts
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.queries import find_account
from tl_core.modules import load_modules
from tl_core.proposals.types import ProposalView
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import BudgetExceededError, DuplicateKeyError
from tl_core.services.idempotency import MISMATCH_TEXT, IdempotencyMismatch
from tl_core.services.proposals import submit
from tl_core.services.records import handle_create_record
from tl_core.uow import UnitOfWork

KEY = "submit-order-key-1"
SCOPE = "project:P1"
AGENT = "agent:bot"


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


@pytest.fixture
def factory(db: DbTarget) -> Iterator[object]:
    for name in ("bot", "other"):  # an agent files only where it holds a module role (P2-X2)
        with open_uow(db) as uow:
            grant_filing(uow, name)
    made = make_uow_factory(db)
    try:
        yield made
    finally:
        made.dispose()


def command(
    agent: str = AGENT, *, record_key: str = "R-1", title: str = "A record", key: str | None = KEY
) -> CreateRecord:
    return CreateRecord(
        actor=agent, source="mcp:x", scope=SCOPE, record_type="core.Record",
        title=title, key=record_key, idempotency_key=key,
    )  # fmt: skip


def file(
    factory: object, cmd: CreateRecord, *, agent: str = AGENT, budget: int | None = 1
) -> ProposalView:
    return submit(
        factory,  # type: ignore[arg-type]
        tool="create_record",
        agent=agent,
        command=cmd,
        summary="Create a record",
        budget=budget,
    )


def count(db: DbTarget, sql: str) -> int:
    with open_uow(db, readonly=True) as uow:
        return int(uow.conn().execute(text(sql)).scalar_one())


EVENTS = "SELECT COUNT(*) FROM events"
PROPOSALS = "SELECT COUNT(*) FROM cur_proposals"


def test_a_retry_at_the_cap_returns_the_first_proposal(db: DbTarget, factory: object) -> None:
    first = file(factory, command())
    events = count(db, EVENTS)
    again = file(factory, command())  # budget 1 is used up
    assert again.proposal_id == first.proposal_id
    assert count(db, PROPOSALS) == 1
    assert count(db, EVENTS) == events


def test_a_retry_whose_dry_run_would_fail_returns_the_first_proposal(
    db: DbTarget, factory: object
) -> None:
    first = file(factory, command(record_key="R-9"), budget=5)
    with open_uow(db) as uow:
        handle_create_record(uow, command(record_key="R-9", title="Taken", key=None))
    events = count(db, EVENTS)
    with pytest.raises(DuplicateKeyError):  # a new key is refused by the dry run
        file(factory, command(record_key="R-9", key="other-key-2"), budget=5)
    again = file(factory, command(record_key="R-9"), budget=5)
    assert again.proposal_id == first.proposal_id
    assert count(db, EVENTS) == events


def test_a_changed_body_is_the_mismatch_refusal_before_budget_or_dry_run(
    db: DbTarget, factory: object
) -> None:
    file(factory, command())  # the cap is reached
    events = count(db, EVENTS)
    with pytest.raises(IdempotencyMismatch) as caught:
        file(factory, command(title="Another title"))
    assert str(caught.value) == MISMATCH_TEXT
    assert count(db, PROPOSALS) == 1 and count(db, EVENTS) == events


def test_without_a_key_the_budget_still_refuses_first(db: DbTarget, factory: object) -> None:
    file(factory, command(key=None))
    with pytest.raises(BudgetExceededError):
        file(factory, command(record_key="R-2", key=None))
    assert count(db, PROPOSALS) == 1


def test_another_agent_with_the_same_key_is_not_affected(db: DbTarget, factory: object) -> None:
    mine = file(factory, command())
    theirs = file(factory, command("agent:other"), agent="agent:other")
    assert theirs.proposal_id != mine.proposal_id
    assert theirs.agent == "agent:other"
    assert count(db, PROPOSALS) == 2
