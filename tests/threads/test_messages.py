"""Thread messages: post, edit, retract, the projections and the reads (P1-I7 WS-B, S1)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from thread_world import P1, make_record, put_setting
from tl_adapters.db import DbTarget, open_uow, rebuild_projections
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_core.threads.contract import THREAD_STREAM_TYPE
from tl_core.threads.errors import (
    MessageNotEditableError,
    MessageRetractedError,
    NotMessageAuthorError,
    ThreadMessageNotFoundError,
    ThreadsDisabledError,
)
from tl_core.threads.messages import (
    EditThreadMessage,
    PostThreadMessage,
    RetractThreadMessage,
    handle_edit_thread_message,
    handle_post_thread_message,
    handle_retract_thread_message,
    post_message,
    thread_stream_id,
)
from tl_core.threads.queries import read_thread
from tl_core.threads.visibility import readable_record


def post(db: DbTarget, record_id: str, body: str, actor: str = "user:rgarcia") -> Any:
    cmd = PostThreadMessage(actor=actor, source="test", scope=P1, record_id=record_id, body=body)
    with open_uow(db) as uow:
        return handle_post_thread_message(uow, cmd)


def page(db: DbTarget, record_id: str, **kw: Any) -> Any:
    with open_uow(db, readonly=True) as uow:
        return read_thread(uow, record_id, actor="user:x", **kw)


def sql(db: DbTarget, query: str, **params: Any) -> list[Any]:
    with open_uow(db, readonly=True) as uow:
        return list(uow.conn().execute(text(query), params).all())


def test_the_first_message_creates_the_thread_stream_without_touching_the_record(
    db: DbTarget,
) -> None:
    rid = make_record(db, "REC-1")
    before = sql(db, "SELECT version FROM cur_core_record WHERE id = :i", i=rid)[0].version
    result = post(db, rid, "Flanges short for W019")
    assert result.stream_id == thread_stream_id(rid) == f"thread:{rid}"
    assert result.version == 1 and result.key
    event = result.events[0]
    assert event.event_type == "Thread.MessagePosted" and event.stream_type == THREAD_STREAM_TYPE
    assert event.scope == P1
    assert event.payload["record_creator"] == "user:creator"
    assert sql(db, "SELECT version FROM cur_core_record WHERE id = :i", i=rid)[0].version == before
    second = post(db, rid, "More")
    assert second.version == 2 and "record_creator" not in second.events[0].payload


def test_mentions_and_keys_are_detected_and_kept(db: DbTarget) -> None:
    rid = make_record(db, "P123-REC-0001")
    other = make_record(db, "P123-REC-0002")
    post(db, rid, "see #P123-REC-0002 and #P123-REC-0002 @lchen @party:acme-nde @lchen #nope")
    message = page(db, rid).messages[0]
    assert message.mentions == ["lchen", "party:acme-nde"]
    assert message.record_refs == [other]


def test_the_page_lists_oldest_first_with_participants_and_a_cursor(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    for i in range(5):
        post(db, rid, f"m{i} @lchen", actor="user:a" if i % 2 else "user:b")
    first = page(db, rid, limit=2)
    assert [m.body for m in first.messages] == ["m3 @lchen", "m4 @lchen"]
    assert first.next_before is not None and first.message_count == 5
    older = page(db, rid, limit=2, before_seq=first.seqs[0])
    assert [m.body for m in older.messages] == ["m1 @lchen", "m2 @lchen"]
    last = page(db, rid, limit=2, before_seq=older.seqs[0])
    assert [m.body for m in last.messages] == ["m0 @lchen"] and last.next_before is None
    people = {p.actor: p.reasons for p in first.participants}
    assert people == {
        "user:creator": ["creator"],
        "user:b": ["author"],
        "user:lchen": ["mentioned"],
        "user:a": ["author"],
    }
    assert first.enabled and first.dispatch_enabled


def test_edit_and_retract_are_the_authors_and_leave_history(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    mid = post(db, rid, "first").key
    assert mid is not None

    def edit(actor: str, body: str) -> Any:
        cmd = EditThreadMessage(
            actor=actor, source="t", scope=P1, record_id=rid, message_id=mid, body=body
        )
        with open_uow(db) as uow:
            return handle_edit_thread_message(uow, cmd)

    def retract(actor: str) -> Any:
        cmd = RetractThreadMessage(
            actor=actor, source="t", scope=P1, record_id=rid, message_id=mid, reason="oops"
        )
        with open_uow(db) as uow:
            return handle_retract_thread_message(uow, cmd)

    with pytest.raises(NotMessageAuthorError):
        edit("user:other", "hijack")
    with pytest.raises(NoChangesError):
        edit("user:rgarcia", "first")
    edit("user:rgarcia", "second @kpatel")
    shown = page(db, rid).messages[0]
    assert shown.body == "second @kpatel" and shown.edited and shown.mentions == ["kpatel"]
    with pytest.raises(NotMessageAuthorError):
        retract("user:other")
    retract("user:rgarcia")
    shown = page(db, rid).messages[0]
    assert shown.retracted and shown.body == ""
    with pytest.raises(MessageRetractedError):
        edit("user:rgarcia", "again")
    with pytest.raises(MessageRetractedError):
        retract("user:rgarcia")
    kinds = [r.event_type for r in sql(db, "SELECT event_type FROM events ORDER BY seq")]
    assert kinds[-3:] == ["Thread.MessagePosted", "Thread.MessageEdited", "Thread.MessageRetracted"]


def test_a_message_of_another_thread_or_scope_reads_as_absent(db: DbTarget) -> None:
    a, b = make_record(db, "REC-A"), make_record(db, "REC-B")
    mid = post(db, a, "mine").key
    assert mid is not None
    cmd = EditThreadMessage(
        actor="user:rgarcia", source="t", scope=P1, record_id=b, message_id=mid, body="x"
    )
    with open_uow(db) as uow, pytest.raises(ThreadMessageNotFoundError):
        handle_edit_thread_message(uow, cmd)


def test_system_messages_are_history_not_editable(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    with open_uow(db) as uow:
        record = readable_record(uow, rid, actor="user:a")
        mid = post_message(
            uow, record=record, actor="user:a", source="thread:x", body="/hold", kind="dispatch"
        ).key
    cmd = EditThreadMessage(
        actor="user:a", source="t", scope=P1, record_id=rid, message_id=str(mid), body="x"
    )
    with open_uow(db) as uow, pytest.raises(MessageNotEditableError):
        handle_edit_thread_message(uow, cmd)


def test_a_slash_message_is_only_a_message(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    post(db, rid, "/raise record Something")
    assert [r.event_type for r in sql(db, "SELECT event_type FROM events")].count(
        "Record.Created"
    ) == 1  # the record of the test, nothing raised
    assert page(db, rid).messages[0].body == "/raise record Something"


def test_threads_need_the_switch_and_the_type(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    put_setting(db, "threads.enabled_types", [])
    with pytest.raises(ThreadsDisabledError):
        post(db, rid, "hello")
    put_setting(db, "threads.enabled_types", ["core.Record"])
    put_setting(db, "threads.enabled", False)
    with pytest.raises(ThreadsDisabledError):
        post(db, rid, "hello")
    put_setting(db, "threads.enabled", False, layer="company")
    put_setting(db, "threads.enabled", True, layer="project:P123")
    assert post(db, rid, "hello").version == 1  # the project switch wins
    assert page(db, rid).enabled


def test_a_record_of_another_scope_or_none_gives_the_record_not_found(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    cmd = PostThreadMessage(
        actor="user:a", source="t", scope="project:OTHER", record_id=rid, body="x"
    )
    with open_uow(db) as uow, pytest.raises(RecordNotFoundError):
        handle_post_thread_message(uow, cmd)
    with open_uow(db, readonly=True) as uow, pytest.raises(RecordNotFoundError):
        read_thread(uow, "nope", actor="user:a")


def test_the_body_is_checked_by_the_command() -> None:
    for body in ("", "   ", "x" * 10_001, "bell\x07"):
        with pytest.raises(ValidationError):
            PostThreadMessage(actor="u", source="t", scope=P1, record_id="r", body=body)
    PostThreadMessage(actor="u", source="t", scope=P1, record_id="r", body="a\tb\nc")
    with pytest.raises(ValidationError):
        PostThreadMessage(actor="u", source="t", scope=P1, record_id="r", body="a\x00b")


def test_a_rebuild_gives_the_same_rows(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    mid = post(db, rid, "one @lchen").key
    post(db, rid, "two")
    retract = RetractThreadMessage(
        actor="user:rgarcia", source="t", scope=P1, record_id=rid, message_id=str(mid), reason="r"
    )
    with open_uow(db) as uow:
        handle_retract_thread_message(uow, retract)
    tables = ("cur_thread", "cur_thread_message", "cur_thread_participant")
    before = {t: sorted(map(tuple, sql(db, f"SELECT * FROM {t}"))) for t in tables}
    rebuild_projections(db)
    after = {t: sorted(map(tuple, sql(db, f"SELECT * FROM {t}"))) for t in tables}
    assert before == after and before["cur_thread_message"]


def test_a_switched_off_thread_shows_nothing_and_takes_no_post_edit_or_retract(
    db: DbTarget,
) -> None:
    rid = make_record(db, "REC-1")
    made = post(db, rid, "hello")
    assert len(page(db, rid).messages) == 1
    put_setting(db, "threads.enabled", False)
    shown = page(db, rid)
    assert not shown.enabled and shown.messages == [] and shown.participants == []
    assert shown.message_count == 0 and shown.next_before is None
    with pytest.raises(ThreadsDisabledError):
        post(db, rid, "again")
    for handler, cmd in (
        (
            handle_edit_thread_message,
            EditThreadMessage(
                actor="user:rgarcia",
                source="t",
                scope=P1,
                record_id=rid,
                message_id=made.key,
                body="changed",
            ),
        ),
        (
            handle_retract_thread_message,
            RetractThreadMessage(
                actor="user:rgarcia",
                source="t",
                scope=P1,
                record_id=rid,
                message_id=made.key,
                reason="typo",
            ),
        ),
    ):
        with open_uow(db) as uow, pytest.raises(ThreadsDisabledError):
            handler(uow, cmd)  # type: ignore[operator]
    put_setting(db, "threads.enabled", True)
    assert [m.body for m in page(db, rid).messages] == ["hello"]  # the ledger kept it
