"""P2-X1-S2: ``submit`` answers a filed key before the budget and the dry run."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, make_uow_factory, open_uow
from tl_core.proposals.types import ProposalView
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import BudgetExceededError, DuplicateKeyError
from tl_core.services.idempotency import MISMATCH_TEXT, IdempotencyMismatch
from tl_core.services.proposals import submit
from tl_core.services.records import handle_create_record

KEY = "submit-order-key-1"
SCOPE = "project:P1"
AGENT = "agent:bot"


@pytest.fixture
def factory(db: DbTarget) -> Iterator[object]:
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
