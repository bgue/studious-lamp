"""A replay passes the filter and redaction ``/events`` applies (P2-X1-S3, SR-X1 F1)."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.intent import Intent, IntentRef, intent_scope, redact_for_viewer
from tl_core.ledger import Event
from tl_core.modules import ConfidentialSource
from tl_core.services import idempotency
from tl_core.services.commands import CommandResult, CreateRecord
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import handle_create_record
from tl_core.uow import UnitOfWork

ACTOR = "user:ann"
SCOPE = "project:P1"
KEY = "replay-filter-key-1"
TABLE = "replay_filter_class"
VIEWER = cf.Viewer(actor=ACTOR, level=0, account=ACTOR)


@pytest.fixture
def classed(monkeypatch: pytest.MonkeyPatch, db: DbTarget) -> Iterator[None]:
    with open_uow(db) as uow:
        uow.conn().execute(text(f"CREATE TABLE {TABLE} (id TEXT PRIMARY KEY, cls TEXT NOT NULL)"))
    source = ConfidentialSource(
        record_types=frozenset({"core.Record"}), table=TABLE, id_column="id", class_column="cls"
    )
    real = core_modules.confidential_sources
    monkeypatch.setattr(cf, "confidential_sources", lambda: [*real(), source])
    yield


def set_class(db: DbTarget, record_id: str, cls: str) -> None:
    with open_uow(db) as uow:
        uow.conn().execute(text(f"DELETE FROM {TABLE} WHERE id = :i"), {"i": record_id})
        uow.conn().execute(
            text(f"INSERT INTO {TABLE} (id, cls) VALUES (:i, :c)"), {"i": record_id, "c": cls}
        )


def new_record(db: DbTarget, key: str, intent: Intent | None = None) -> CommandResult:
    with open_uow(db) as uow:
        made = handle_create_record(
            uow,
            CreateRecord(
                actor=ACTOR,
                source="test",
                scope=SCOPE,
                record_type="core.Record",
                title=f"title {key}",
                key=key,
                intent=intent,
            ),  # fmt: skip
        )
    set_class(db, str(made.stream_id), "internal")
    return made


def keyed[C: CreateRecord | AddLink](
    db: DbTarget, name: str, cmd: C, handler: Callable[[UnitOfWork, C], CommandResult]
) -> CommandResult:
    with open_uow(db) as uow:
        assert idempotency.check(uow.conn(), ACTOR, KEY, name, cmd) is None
        result = handler(uow, cmd)
        idempotency.record(uow.conn(), ACTOR, KEY, idempotency.result_ids_of(result))
    return result


def replay(db: DbTarget, name: str, cmd: object) -> CommandResult:
    with open_uow(db) as uow:
        found = idempotency.check(uow.conn(), ACTOR, KEY, name, cmd)
        assert isinstance(found, idempotency.Replay)
        return idempotency.replay_result(uow.conn(), found, VIEWER)


def events_view(db: DbTarget, ids: list[str]) -> list[Event]:
    """What ``/events`` shows this viewer for these event ids."""
    with open_uow(db, readonly=True) as uow:
        raw = [e for e in uow.ledger.read_after(0, limit=1000) if e.event_id in set(ids)]
        return redact_for_viewer(uow.conn(), cf.filter_events(uow.conn(), raw, VIEWER), VIEWER)


def link_cmd(a: str, b: str) -> AddLink:
    return AddLink(actor=ACTOR, source="test", scope=SCOPE, from_id=a, to_id=b, idempotency_key=KEY)


def test_a_replayed_link_does_not_name_a_record_the_viewer_lost(
    db: DbTarget, classed: None
) -> None:
    a, b = new_record(db, "A-1"), new_record(db, "B-1")
    cmd = link_cmd(str(a.stream_id), str(b.stream_id))
    first = keyed(db, "AddLink", cmd, handle_add_link)
    assert str(b.stream_id) in str(first.events[0].payload)
    set_class(db, str(b.stream_id), "privileged")
    again = replay(db, "AddLink", cmd)
    ids = [str(e.event_id) for e in first.events]
    assert again.events == events_view(db, ids)
    assert str(b.stream_id) not in str(again.events)
    with open_uow(db, readonly=True) as uow:  # the viewer cannot read B on /events either
        with pytest.raises(RecordNotFoundError):
            cf.require_visible(uow.conn(), str(b.stream_id), VIEWER)
    assert again.stream_id == first.stream_id  # A's own stream still answers


def test_a_replay_naming_only_readable_records_is_unchanged(db: DbTarget, classed: None) -> None:
    a, b = new_record(db, "A-2"), new_record(db, "B-2")
    cmd = link_cmd(str(a.stream_id), str(b.stream_id))
    first = keyed(db, "AddLink", cmd, handle_add_link)
    again = replay(db, "AddLink", cmd)
    assert again.events == first.events
    assert [e.model_dump_json() for e in again.events] == [
        e.model_dump_json() for e in first.events
    ]
    assert (again.stream_id, again.version, again.key) == (
        first.stream_id,
        first.version,
        first.key,
    )


def test_a_replay_whose_own_stream_became_hidden_answers_as_absent(
    db: DbTarget, classed: None
) -> None:
    cmd = CreateRecord(
        actor=ACTOR, source="test", scope=SCOPE, record_type="core.Record", title="own",
        key="OWN-1", idempotency_key=KEY,
    )  # fmt: skip
    first = keyed(db, "CreateRecord", cmd, handle_create_record)
    set_class(db, str(first.stream_id), "privileged")
    with pytest.raises(RecordNotFoundError) as hidden:
        replay(db, "CreateRecord", cmd)
    assert str(hidden.value) == f"no record {str(first.stream_id)!r}"


def test_a_replayed_intent_ref_to_a_hidden_record_is_redacted_as_events_does(
    db: DbTarget, classed: None
) -> None:
    b = new_record(db, "B-4")
    intent = Intent(
        why="because", next=[IntentRef(command="UpdateRecord", target=str(b.stream_id))]
    )
    cmd = CreateRecord(
        actor=ACTOR, source="test", scope=SCOPE, record_type="core.Record", title="with intent",
        key="C-4", intent=intent, idempotency_key=KEY,
    )  # fmt: skip
    with intent_scope(intent):
        first = keyed(db, "CreateRecord", cmd, handle_create_record)
    set_class(db, str(first.stream_id), "internal")
    assert str(b.stream_id) in str(first.events[0].intent)
    set_class(db, str(b.stream_id), "privileged")
    again = replay(db, "CreateRecord", cmd)
    assert str(b.stream_id) not in str(again.events[0].intent)
    assert again.events == events_view(db, [str(e.event_id) for e in first.events])
