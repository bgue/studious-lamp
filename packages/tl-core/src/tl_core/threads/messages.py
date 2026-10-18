"""Post, edit and retract a thread message (brief 21.5; FANOUT D9).

A thread is the ledger stream ``thread:<record id>`` (stream type ``core.Thread``, the record's
scope), created by the first message, so messages never change the record's version. These
commands are the public ones: they never dispatch, even when the body starts with ``/``
(``PostThreadMessage`` is a message; a slash command goes through the planner and
``DispatchFromThread``). The server-written kinds (``dispatch``, ``summary``, ``reminder``) are
posted by :func:`post_message`, a Python-only function no client reaches.

``CommandResult.stream_id`` is the thread stream, ``key`` the message id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import field_validator
from sqlalchemy import text

from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError
from tl_core.services.feed import parse_post
from tl_core.services.queries import record_history
from tl_core.threads.config import threads_enabled
from tl_core.threads.contract import (
    MAX_MESSAGE_CHARS,
    THREAD_MESSAGE_EDITED,
    THREAD_MESSAGE_POSTED,
    THREAD_MESSAGE_RETRACTED,
    THREAD_STREAM_PREFIX,
    THREAD_STREAM_TYPE,
)
from tl_core.threads.errors import (
    MessageNotEditableError,
    MessageRetractedError,
    NotMessageAuthorError,
    ThreadMessageNotFoundError,
    ThreadsDisabledError,
)
from tl_core.threads.visibility import ThreadRecord, readable_record
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

MAX_REASON_CHARS = 1_000

_THREAD_VERSION_SQL = text("SELECT version FROM cur_thread WHERE record_id = :record_id")
_MESSAGE_SQL = text(
    "SELECT message_id, record_id, scope, author, kind, body, retracted FROM cur_thread_message "
    "WHERE message_id = :message_id"
)


def thread_stream_id(record_id: str) -> str:
    """The ledger stream of a record's thread."""
    return f"{THREAD_STREAM_PREFIX}{record_id}"


def _clean_body(value: str) -> str:
    if not value.strip():
        raise ValueError("body must not be blank")
    if len(value) > MAX_MESSAGE_CHARS:
        raise ValueError(f"body must be at most {MAX_MESSAGE_CHARS} characters")
    if any(ch == "\x7f" or (ch < " " and ch not in "\t\n\r") for ch in value):
        raise ValueError("body must not contain control characters")
    return value


class PostThreadMessage(Command):
    """Post ``body`` to the thread of ``record_id`` as ``actor`` (person or agent).

    It never dispatches: a body that starts with ``/`` is stored as the text it is.
    """

    record_id: str
    body: str

    @field_validator("body")
    @classmethod
    def _body_is_usable(cls, value: str) -> str:
        return _clean_body(value)


class EditThreadMessage(Command):
    """Replace the body of the author's own message."""

    record_id: str
    message_id: str
    body: str

    @field_validator("body")
    @classmethod
    def _body_is_usable(cls, value: str) -> str:
        return _clean_body(value)


class RetractThreadMessage(Command):
    """Retract the author's own message; a tombstone stays."""

    record_id: str
    message_id: str
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason_given(cls, value: str) -> str:
        if not value.strip() or len(value) > MAX_REASON_CHARS:
            raise ValueError(f"reason must be 1 to {MAX_REASON_CHARS} characters")
        return value


@dataclass(frozen=True)
class MessageRow:
    message_id: str
    record_id: str
    scope: str
    author: str
    kind: str
    body: str
    retracted: bool


def thread_version(uow: UnitOfWork, record_id: str) -> int:
    """The version of the record's thread stream; 0 before its first message."""
    row = uow.conn().execute(_THREAD_VERSION_SQL, {"record_id": record_id}).first()
    return 0 if row is None else int(row.version)


def load_message(uow: UnitOfWork, record_id: str, message_id: str, scope: str) -> MessageRow:
    """A message of this record's thread; another thread's or scope's reads as absent."""
    row = uow.conn().execute(_MESSAGE_SQL, {"message_id": message_id}).first()
    if row is None or row.record_id != record_id or row.scope != scope:
        raise ThreadMessageNotFoundError(
            f"no message {message_id!r} in the thread of {record_id!r}"
        )
    return MessageRow(
        message_id=row.message_id,
        record_id=row.record_id,
        scope=row.scope,
        author=row.author,
        kind=row.kind,
        body=row.body,
        retracted=bool(row.retracted),
    )


def detect(uow: UnitOfWork, scope: str, body: str) -> tuple[list[str], list[str]]:
    """``(mentions, record_refs)`` of a body, each without repeats.

    Mentions are as typed without the sigil; record references are record ids found with the
    feed's key detection (``#KEY``). Nothing here links anything.
    """
    tags = parse_post(uow, scope, body)
    mentions = list(dict.fromkeys(tag.text for tag in tags if tag.kind == "mention"))
    refs = list(
        dict.fromkeys(tag.record_id for tag in tags if tag.kind == "record" and tag.record_id)
    )
    return mentions, refs


def post_message(
    uow: UnitOfWork,
    *,
    record: ThreadRecord,
    actor: str,
    source: str,
    body: str,
    kind: str = "message",
    message_id: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    check_enabled: bool = True,
) -> CommandResult:
    """Append ``Thread.MessagePosted`` for ``record`` (the caller has already read the record).

    ``check_enabled`` is false only for the messages the server writes itself on a thread that
    already exists (a reminder falling due). The first message of a record also carries the
    record's creator, who joins the participants.
    """
    if check_enabled and not threads_enabled(uow.conn(), record.scope, record.record_type):
        raise ThreadsDisabledError(
            f"threads are not switched on for {record.record_type} records in {record.scope}"
        )
    message = message_id or new_ulid()
    mentions, refs = detect(uow, record.scope, body)
    version = thread_version(uow, record.id)
    payload: dict[str, Any] = {
        "message_id": message,
        "record_id": record.id,
        "author": actor,
        "body": body,
        "mentions": mentions,
        "record_refs": refs,
        "kind": kind,
    }
    if version == 0:
        history = record_history(uow, record.id)
        if history:
            payload["record_creator"] = history[0].actor
    result = uow.append(
        stream_id=thread_stream_id(record.id),
        stream_type=THREAD_STREAM_TYPE,
        scope=record.scope,
        expected_version=version,
        events=[NewEvent(event_type=THREAD_MESSAGE_POSTED, payload=payload)],
        actor=actor,
        source=source,
        correlation_id=correlation_id or new_ulid(),
        causation_id=causation_id,
    )
    return CommandResult(
        stream_id=thread_stream_id(record.id),
        key=message,
        version=result.new_version,
        events=list(result.events),
    )


def handle_post_thread_message(uow: UnitOfWork, cmd: PostThreadMessage) -> CommandResult:
    """Post a message. Raises ``RecordNotFoundError`` (no such record in the scope, or not
    readable) and ``ThreadsDisabledError``."""
    record = readable_record(uow, cmd.record_id, actor=cmd.actor, scope=cmd.scope)
    return post_message(
        uow,
        record=record,
        actor=cmd.actor,
        source=cmd.source,
        body=cmd.body,
        correlation_id=cmd.correlation_id,
        causation_id=cmd.causation_id,
    )


def _own_live_message(uow: UnitOfWork, cmd: EditThreadMessage | RetractThreadMessage) -> MessageRow:
    readable_record(uow, cmd.record_id, actor=cmd.actor, scope=cmd.scope)
    message = load_message(uow, cmd.record_id, cmd.message_id, cmd.scope)
    if message.author != cmd.actor:
        raise NotMessageAuthorError(f"only the author ({message.author}) can change this message")
    if message.retracted:
        raise MessageRetractedError(f"message {cmd.message_id!r} was retracted")
    if message.kind != "message":
        raise MessageNotEditableError(
            f"a {message.kind} message belongs to the history of the thread and is not changed"
        )
    return message


def handle_edit_thread_message(uow: UnitOfWork, cmd: EditThreadMessage) -> CommandResult:
    """Replace the author's body; the earlier text stays in the ledger.

    Raises ``ThreadMessageNotFoundError``, ``NotMessageAuthorError``, ``MessageRetractedError``,
    ``MessageNotEditableError`` and ``NoChangesError`` (same body).
    """
    message = _own_live_message(uow, cmd)
    if message.body == cmd.body:
        raise NoChangesError(f"the body of message {cmd.message_id!r} is already that text")
    mentions, refs = detect(uow, cmd.scope, cmd.body)
    result = uow.append(
        stream_id=thread_stream_id(cmd.record_id),
        stream_type=THREAD_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=thread_version(uow, cmd.record_id),
        events=[
            NewEvent(
                event_type=THREAD_MESSAGE_EDITED,
                payload={
                    "message_id": cmd.message_id,
                    "record_id": cmd.record_id,
                    "body": cmd.body,
                    "mentions": mentions,
                    "record_refs": refs,
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=thread_stream_id(cmd.record_id),
        key=cmd.message_id,
        version=result.new_version,
        events=list(result.events),
    )


def handle_retract_thread_message(uow: UnitOfWork, cmd: RetractThreadMessage) -> CommandResult:
    """Retract the author's message; the projection keeps a tombstone."""
    _own_live_message(uow, cmd)
    result = uow.append(
        stream_id=thread_stream_id(cmd.record_id),
        stream_type=THREAD_STREAM_TYPE,
        scope=cmd.scope,
        expected_version=thread_version(uow, cmd.record_id),
        events=[
            NewEvent(
                event_type=THREAD_MESSAGE_RETRACTED,
                payload={
                    "message_id": cmd.message_id,
                    "record_id": cmd.record_id,
                    "reason": cmd.reason.strip(),
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=thread_stream_id(cmd.record_id),
        key=cmd.message_id,
        version=result.new_version,
        events=list(result.events),
    )


__all__ = [
    "EditThreadMessage",
    "MessageRow",
    "PostThreadMessage",
    "RetractThreadMessage",
    "detect",
    "handle_edit_thread_message",
    "handle_post_thread_message",
    "handle_retract_thread_message",
    "load_message",
    "post_message",
    "thread_stream_id",
    "thread_version",
]
