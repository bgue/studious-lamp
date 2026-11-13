"""The API door and the table runner honour an idempotency key (P2-X1-S1).

``run_command`` and ``TableCommandRunner.run`` claim the key inside the open unit of work, around
the handler call only, and record the result ids before the transaction commits.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from harness import Harness
from sqlalchemy import text
from tl_api.commands import command_runner, command_spec, run_command
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from tl_core.auth.types import Principal
from tl_core.services.commands import CommandResult, CreateRecord
from tl_core.services.idempotency import IdempotencyMismatch

SCOPE = "project:P1"
KEY = "door-key-5d2e8b"


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


def principal() -> Principal:
    return Principal(
        actor="user:uma", account_id="01HZZZZZZZZZZZZZZZZZZZZZZZ", kind="person", roles=["user"],
        via="session",
    )  # fmt: skip


def create(key: str | None, record_key: str = "D-1") -> CreateRecord:
    return CreateRecord(
        actor="user:uma", source="test", scope=SCOPE, record_type="core.Record", title="T",
        key=record_key, idempotency_key=key,
    )  # fmt: skip


def scalar(harness: Harness, sql: str) -> int:
    with harness.backend(True) as uow:
        return int(uow.conn().execute(text(sql)).scalar_one())


def test_run_command_with_one_key_writes_once_and_replays(harness: Harness) -> None:
    spec = command_spec("CreateRecord")
    assert spec is not None
    calls: list[int] = []

    def counting(uow: Any, cmd: Any) -> CommandResult:
        calls.append(1)
        return spec.handler(uow, cmd)

    counted = dataclasses.replace(spec, handler=counting)
    ctx = harness.app.state.ctx
    first = run_command(ctx, counted, create(KEY), principal=principal(), guard=False)
    events = scalar(harness, "SELECT COUNT(*) FROM events")
    again = run_command(ctx, counted, create(KEY), principal=principal(), guard=False)
    assert len(calls) == 1 and scalar(harness, "SELECT COUNT(*) FROM events") == events
    assert again.stream_id == first.stream_id and again.key == "D-1"
    assert [e.event_id for e in again.events] == [e.event_id for e in first.events]
    assert scalar(harness, "SELECT COUNT(*) FROM idempotency_key") == 1


def test_run_command_with_another_body_is_the_fixed_refusal(harness: Harness) -> None:
    spec = command_spec("CreateRecord")
    assert spec is not None
    ctx = harness.app.state.ctx
    run_command(ctx, spec, create(KEY), principal=principal(), guard=False)
    events = scalar(harness, "SELECT COUNT(*) FROM events")
    with pytest.raises(IdempotencyMismatch) as caught:
        run_command(ctx, spec, create(KEY, "D-2"), principal=principal(), guard=False)
    assert KEY not in str(caught.value)
    assert scalar(harness, "SELECT COUNT(*) FROM events") == events


def test_a_refused_command_leaves_no_claim(harness: Harness) -> None:
    spec = command_spec("CreateRecord")
    assert spec is not None
    ctx = harness.app.state.ctx

    def refuse(uow: Any, cmd: Any) -> CommandResult:
        raise ValueError("refused")

    broken = dataclasses.replace(spec, handler=refuse)
    with pytest.raises(ValueError, match="refused"):
        run_command(ctx, broken, create(KEY), principal=principal(), guard=False)
    assert scalar(harness, "SELECT COUNT(*) FROM idempotency_key") == 0
    assert run_command(ctx, spec, create(KEY), principal=principal(), guard=False).key == "D-1"


def test_no_key_is_as_before(harness: Harness) -> None:
    spec = command_spec("CreateRecord")
    assert spec is not None
    run_command(harness.app.state.ctx, spec, create(None), principal=principal(), guard=False)
    assert scalar(harness, "SELECT COUNT(*) FROM idempotency_key") == 0


def test_the_table_runner_replays_a_key(harness: Harness) -> None:
    with harness.backend() as uow:  # the runner resolves the actor's access from the ledger
        accounts.create_account(
            uow, username="uma", display_name="Uma", kind="person", roles=["user"],
            password=prepare_password("correct horse battery", username="uma"), by="svc:test",
        )  # fmt: skip
    runner = command_runner()
    with harness.backend(False) as uow:
        first = runner.run(uow, create(KEY))
    events = scalar(harness, "SELECT COUNT(*) FROM events")
    with harness.backend(False) as uow:
        again = runner.run(uow, create(KEY))
    assert again.stream_id == first.stream_id
    assert scalar(harness, "SELECT COUNT(*) FROM events") == events
    with pytest.raises(IdempotencyMismatch), harness.backend(False) as uow:
        runner.run(uow, create(KEY, "D-2"))
