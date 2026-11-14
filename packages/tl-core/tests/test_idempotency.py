"""Idempotency keys (P2-X1-S1): one key, one write; no leak; the claim is transactional."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.ledger import Event
from tl_core.modules import ConfidentialSource, ModuleSpec, use_modules
from tl_core.services import idempotency
from tl_core.services.commands import Command, CommandResult, CreateRecord, UpdateRecord
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.idempotency import (
    IdempotencyInProgress,
    IdempotencyMismatch,
    InvalidIdempotencyKeyError,
    Replay,
)
from tl_core.services.proposals import propose
from tl_core.services.records import create_module_record, handle_create_record
from tl_core.uow import UnitOfWork

KEY = "retry-key-7f3a9c1e"
SCOPE = "project:P1"


def make(
    key: str | None = KEY, *, record_key: str = "K-1", actor: str = "user:ann", **more: Any
) -> CreateRecord:
    return CreateRecord(
        actor=actor, source="test", scope=SCOPE, record_type="core.Record", title="A record",
        key=record_key, idempotency_key=key, **more,
    )  # fmt: skip


def run(uow: UnitOfWork, cmd: CreateRecord, viewer: cf.Viewer | None = None) -> CommandResult:
    """What the API door does around a handler, with the same helper calls."""
    replay = idempotency.check(uow.conn(), cmd.actor, cmd.idempotency_key, "CreateRecord", cmd)
    if replay is not None:
        return idempotency.replay_result(uow.conn(), replay, viewer)
    result = handle_create_record(uow, cmd)
    idempotency.record(
        uow.conn(), cmd.actor, cmd.idempotency_key, idempotency.result_ids_of(result)
    )
    return result


def count(db: DbTarget, sql: str) -> int:
    with open_uow(db, readonly=True) as uow:
        return int(uow.conn().execute(text(sql)).scalar_one())


EVENTS = "SELECT COUNT(*) FROM events"
KEYS = "SELECT COUNT(*) FROM idempotency_key"


def test_same_key_twice_returns_the_first_answer_and_one_event_set(db: DbTarget) -> None:
    with open_uow(db) as uow:
        first = run(uow, make())
    after_first = count(db, EVENTS)
    with open_uow(db) as uow:
        second = run(uow, make())
    assert second.stream_id == first.stream_id
    assert second.key == first.key == "K-1"
    assert second.version == first.version
    assert [e.event_id for e in second.events] == [e.event_id for e in first.events]
    assert count(db, EVENTS) == after_first and count(db, KEYS) == 1


def test_a_retry_may_change_correlation_and_causation_ids(db: DbTarget) -> None:
    with open_uow(db) as uow:
        first = run(uow, make())
    with open_uow(db) as uow:
        again = run(uow, make(correlation_id="other", causation_id="x"))
    assert again.stream_id == first.stream_id


@pytest.mark.parametrize("change", ["body", "command"])
def test_same_key_with_another_body_or_command_is_refused_and_writes_nothing(
    db: DbTarget, change: str
) -> None:
    with open_uow(db) as uow:
        run(uow, make())
    events, keys = count(db, EVENTS), count(db, KEYS)
    with pytest.raises(IdempotencyMismatch) as caught, open_uow(db) as uow:
        if change == "body":
            run(uow, make(record_key="K-2"))
        else:
            idempotency.check(uow.conn(), "user:ann", KEY, "VoidRecord", make())
    assert str(caught.value) == idempotency.MISMATCH_TEXT and KEY not in str(caught.value)
    assert count(db, EVENTS) == events and count(db, KEYS) == keys


def test_another_actor_with_the_same_key_neither_sees_nor_collides(db: DbTarget) -> None:
    with open_uow(db) as uow:
        mine = run(uow, make())
    with open_uow(db) as uow:
        theirs = run(uow, make(record_key="K-2", actor="user:bob"))  # not a mismatch, not a replay
    assert theirs.stream_id != mine.stream_id and count(db, KEYS) == 2
    with open_uow(db) as uow:  # and each still replays its own
        assert run(uow, make(record_key="K-2", actor="user:bob")).stream_id == theirs.stream_id
        assert run(uow, make()).stream_id == mine.stream_id


def test_the_claim_rolls_back_with_a_failed_command(db: DbTarget) -> None:
    class Boom(Exception): ...

    with pytest.raises(Boom), open_uow(db) as uow:
        run(uow, make())
        raise Boom
    assert count(db, KEYS) == 0 and count(db, EVENTS) == 0
    with open_uow(db) as uow:  # the key is free again
        assert run(uow, make()).key == "K-1"


def test_a_none_key_behaves_as_before(db: DbTarget) -> None:
    with open_uow(db) as uow:
        assert idempotency.check(uow.conn(), "user:ann", None, "CreateRecord", make(None)) is None
        run(uow, make(None))
    assert count(db, KEYS) == 0 and count(db, EVENTS) == 1


@pytest.mark.parametrize("key", ["k" * 129, "clé-retry", "", "with space", "line\nbreak"])
def test_a_bad_key_is_refused_without_the_key_in_the_text(db: DbTarget, key: str) -> None:
    with pytest.raises(ValidationError) as model:
        make(key)
    assert not key or (key not in str(model.value) and repr(key) not in str(model.value))
    with pytest.raises(InvalidIdempotencyKeyError) as helper, open_uow(db) as uow:
        idempotency.check(uow.conn(), "user:ann", key, "CreateRecord", make(None))
    assert not key or key not in str(helper.value)
    assert count(db, KEYS) == 0


def test_the_longest_key_is_accepted(db: DbTarget) -> None:
    with open_uow(db) as uow:
        run(uow, make("k" * 128))
    assert count(db, KEYS) == 1


def test_two_threads_with_one_key_write_once(db: DbTarget) -> None:
    barrier = threading.Barrier(2)

    def attempt() -> object:
        barrier.wait(timeout=10)
        try:
            with open_uow(db) as uow:
                return run(uow, make())
        except (IdempotencyInProgress, IdempotencyMismatch) as exc:
            return exc

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(lambda _: attempt(), range(2)))
    results = [o for o in outcomes if isinstance(o, CommandResult)]
    others = [o for o in outcomes if not isinstance(o, CommandResult)]
    assert len(results) >= 1
    assert all(isinstance(o, IdempotencyInProgress) for o in others)  # never another error
    assert {r.stream_id for r in results} == {results[0].stream_id}
    assert count(db, EVENTS) == len(results[0].events) and count(db, KEYS) == 1


def test_an_unrecorded_claim_seen_from_another_connection_is_in_progress(db: DbTarget) -> None:
    with open_uow(db) as uow:  # a caller that claimed and never recorded, committed
        idempotency.check(uow.conn(), "user:ann", KEY, "CreateRecord", make())
    with pytest.raises(IdempotencyInProgress) as caught, open_uow(db) as uow:
        idempotency.check(uow.conn(), "user:ann", KEY, "CreateRecord", make())
    assert str(caught.value) == idempotency.IN_PROGRESS_TEXT and KEY not in str(caught.value)


# --- the replay is read again through the viewer filter ---------------------------------------

ITEM = "vault.Item"
SOURCE = ConfidentialSource(
    record_types=frozenset({ITEM}), table="cur_vault_item", id_column="id", class_column="klass"
)


class VaultProjector:
    name = "vault"
    handles = frozenset({"Vault.Never"})

    def ddl(self, dialect: str) -> list[str]:
        return ["CREATE TABLE IF NOT EXISTS cur_vault_item (id TEXT PRIMARY KEY, klass TEXT)"]

    def apply(self, conn: Connection, event: Event) -> None:
        return None

    def reset(self, conn: Connection) -> None:
        return None


@pytest.fixture
def vault() -> Iterator[None]:
    spec = ModuleSpec(
        name="vault", record_types=frozenset({ITEM}), projectors=lambda: [VaultProjector()],
        confidential=(SOURCE,),
    )  # fmt: skip
    with use_modules([spec]):
        yield


def test_a_replay_of_an_id_the_viewer_can_no_longer_see_answers_as_absent(
    db: DbTarget, vault: None
) -> None:
    from tl_adapters.db import create_schema

    create_schema(db)  # the vault table
    viewer = cf.Viewer(actor="user:ann", level=0, account="user:ann")
    with open_uow(db) as uow:
        made = create_module_record(
            uow, Command(actor="user:ann", source="test", scope=SCOPE), record_type=ITEM,
            title="vault item", key="V-1",
        )  # fmt: skip
        uow.conn().execute(
            text("INSERT INTO cur_vault_item (id, klass) VALUES (:i, 'internal')"),
            {"i": made.stream_id},
        )
        assert idempotency.check(uow.conn(), "user:ann", KEY, "Make", {"a": 1}) is None
        idempotency.record(uow.conn(), "user:ann", KEY, idempotency.result_ids_of(made))
    with open_uow(db) as uow:  # visible: the replay answers
        replay = idempotency.check(uow.conn(), "user:ann", KEY, "Make", {"a": 1})
        assert isinstance(replay, Replay)
        assert idempotency.replay_result(uow.conn(), replay, viewer).stream_id == made.stream_id
    with open_uow(db) as uow:  # the clearance drops
        uow.conn().execute(text("UPDATE cur_vault_item SET klass = 'restricted'"))
    with open_uow(db) as uow:
        replay = idempotency.check(uow.conn(), "user:ann", KEY, "Make", {"a": 1})
        assert isinstance(replay, Replay)
        with pytest.raises(RecordNotFoundError) as hidden:
            idempotency.replay_result(uow.conn(), replay, viewer)
        with pytest.raises(RecordNotFoundError) as absent:
            cf.require_visible(uow.conn(), made.stream_id, viewer)
    assert str(hidden.value) == str(absent.value) == f"no record {made.stream_id!r}"


# --- the key is never logged ------------------------------------------------------------------


def test_the_key_is_in_no_log_record_and_no_error_text(
    db: DbTarget, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "never-log-this-key-0451"
    texts: list[str] = []
    with (
        caplog.at_level(logging.DEBUG, logger="tl_core"),
        caplog.at_level(logging.DEBUG, logger="tl_api"),
    ):
        with open_uow(db) as uow:
            run(uow, make(secret))
        with open_uow(db) as uow:
            run(uow, make(secret))
        for bad in (
            lambda uow: run(uow, make(secret, record_key="K-9")),
            lambda uow: idempotency.check(
                uow.conn(), "user:ann", secret + "é", "CreateRecord", make(None)
            ),
        ):
            try:
                with open_uow(db) as uow:
                    bad(uow)
            except Exception as exc:  # noqa: BLE001
                texts.append(str(exc) + repr(exc))
    assert len(texts) == 2
    assert all(secret not in t for t in texts)
    assert all(secret not in r.getMessage() and secret not in str(r.args) for r in caplog.records)


# --- propose -----------------------------------------------------------------------------------


def file_proposal(db: DbTarget, key: str | None, title: str = "A record") -> str:
    with open_uow(db) as uow:
        view = propose(
            uow, tool="create_record", agent="agent:bot",
            command=CreateRecord(
                actor="agent:bot", source="mcp:bot", scope=SCOPE, record_type="core.Record",
                title=title, key="K-5", idempotency_key=key,
            ),
            summary="Create K-5",
        )  # fmt: skip
    return view.proposal_id


def test_propose_with_one_key_files_one_proposal_row(db: DbTarget) -> None:
    first = file_proposal(db, KEY)
    again = file_proposal(db, KEY)
    assert again == first
    assert count(db, "SELECT COUNT(*) FROM cur_proposals") == 1
    assert count(db, KEYS) == 1
    # the stored command never carries the key
    assert count(db, f"SELECT COUNT(*) FROM events WHERE payload LIKE '%{KEY}%'") == 0


def test_propose_with_a_new_body_under_the_same_key_is_refused(db: DbTarget) -> None:
    file_proposal(db, KEY)
    with pytest.raises(IdempotencyMismatch):
        file_proposal(db, KEY, title="Another")
    assert count(db, "SELECT COUNT(*) FROM cur_proposals") == 1


def test_propose_without_a_key_files_each_time(db: DbTarget) -> None:
    a, b = file_proposal(db, None), file_proposal(db, None)
    assert a != b and count(db, "SELECT COUNT(*) FROM cur_proposals") == 2 and count(db, KEYS) == 0


def test_body_hash_ignores_the_three_ids_and_nothing_else() -> None:
    base = idempotency.body_hash(make())
    assert idempotency.body_hash(make(None, correlation_id="c", causation_id="d")) == base
    assert idempotency.body_hash(make(description="B")) != base
    assert idempotency.body_hash({"b": 1, "a": 2}) == idempotency.body_hash({"a": 2, "b": 1})


def test_expected_version_is_out_of_the_hash_and_the_other_fields_stay_in() -> None:
    def update(version: int, value: int = 1) -> UpdateRecord:
        return UpdateRecord(
            actor="user:ann", source="test", scope=SCOPE, stream_id="01J0000000000000000000000A",
            expected_version=version, changes={"size_in": value},
        )  # fmt: skip

    base = idempotency.body_hash(update(3))
    assert idempotency.body_hash(update(4)) == base  # resolved at call time, not request content
    assert idempotency.body_hash(update(3, value=2)) != base


def test_a_proposal_wrapped_command_drops_expected_version_from_the_hash() -> None:
    from tl_core.services.idempotency import body_hash

    base = {
        "tool": "update_psets",
        "summary": "s",
        "command": {"name": "UpdateRecord", "expected_version": 3, "x": 1},
    }
    moved = {
        "tool": "update_psets",
        "summary": "s",
        "command": {"name": "UpdateRecord", "expected_version": 4, "x": 1},
    }
    other = {
        "tool": "update_psets",
        "summary": "s",
        "command": {"name": "UpdateRecord", "expected_version": 3, "x": 2},
    }
    assert body_hash(base) == body_hash(moved)
    assert body_hash(base) != body_hash(other)
