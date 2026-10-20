"""Thread reads: the messages and participants of a record's thread (brief 21.5).

Every read loads the record through :func:`~tl_core.threads.visibility.readable_record` first, so a
thread is as visible as its record and a record the caller cannot read gives
``RecordNotFoundError``. A thread that does not exist yet reads as empty (no error), and
``enabled`` says whether the record may have one.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text

from tl_core import confidentiality
from tl_core.confidentiality import Viewer
from tl_core.integration.actor_access import viewer_of
from tl_core.integration.contract import RecordRef
from tl_core.threads.config import dispatch_enabled, threads_enabled
from tl_core.threads.contract import (
    READ_THREAD_MAX_PAGE,
    DispatchOutcome,
    ThreadMessageView,
)
from tl_core.threads.visibility import readable_record
from tl_core.uow import UnitOfWork
from tl_core.webhooks.rows import as_list, as_object, load_json

_MESSAGES = (
    "SELECT message_id, record_id, author, kind, body, mentions_json, record_refs_json, "
    "posted_at, edit_count, retracted, dispatch_json, seq FROM cur_thread_message "
    "WHERE record_id = :record_id"
)
_NEWEST_SQL = text(_MESSAGES + " ORDER BY seq DESC LIMIT :limit")
_BEFORE_SQL = text(_MESSAGES + " AND seq < :before ORDER BY seq DESC LIMIT :limit")
_PARTICIPANTS_SQL = text(
    "SELECT actor, reasons_json FROM cur_thread_participant WHERE record_id = :record_id "
    "ORDER BY first_seq, actor"
)
_THREAD_SQL = text("SELECT message_count FROM cur_thread WHERE record_id = :record_id")


class ThreadParticipant(BaseModel):
    actor: str
    reasons: list[str] = Field(default_factory=list[str])


class ThreadPage(BaseModel):
    """A page of a thread, oldest message first. ``next_before`` is the cursor of the older page."""

    record: RecordRef
    enabled: bool
    dispatch_enabled: bool
    message_count: int = 0
    participants: list[ThreadParticipant] = Field(default_factory=list[ThreadParticipant])
    messages: list[ThreadMessageView] = Field(default_factory=list[ThreadMessageView])
    next_before: int | None = None
    #: Sequence numbers of ``messages``, in the same order (the cursor for ``before``).
    seqs: list[int] = Field(default_factory=list[int])
    #: Kinds of ``messages`` (`message`, `dispatch`, `summary`, `reminder`), in the same order.
    kinds: list[str] = Field(default_factory=list[str])


def _view_of(row: Any) -> ThreadMessageView:
    dispatch = as_object(load_json(row.dispatch_json)) if row.dispatch_json is not None else None
    retracted = bool(row.retracted)
    return ThreadMessageView(
        message_id=row.message_id,
        record_id=row.record_id,
        author=row.author,
        body="" if retracted else row.body,
        posted_at=str(row.posted_at),
        edited=int(row.edit_count) > 0,
        retracted=retracted,
        mentions=[str(m) for m in as_list(load_json(row.mentions_json))],
        record_refs=[str(r) for r in as_list(load_json(row.record_refs_json))],
        dispatch=DispatchOutcome.model_validate(dispatch) if dispatch else None,
    )


def _unreadable_names(conn: Any, rows: list[Any], viewer: Viewer) -> set[str]:
    """The records that messages of this page tag, or that their dispatch cards name, which
    ``viewer`` must not read. A thread's reader may read its record and still not a tagged one."""
    ids: set[str] = set()
    for row in rows:
        ids.update(str(r) for r in as_list(load_json(row.record_refs_json)))
        if row.dispatch_json is not None:
            ids.update(confidentiality.payload_record_ids(row.dispatch_json))
    return confidentiality.hidden_among(conn, sorted(ids), viewer)


def _view(row: Any, hidden: set[str] | None = None) -> ThreadMessageView:
    view = _view_of(row)
    if not hidden:
        return view
    view.record_refs = [r for r in view.record_refs if r not in hidden]
    if row.dispatch_json is not None and (
        confidentiality.payload_record_ids(row.dispatch_json) & hidden
    ):
        view.dispatch = None  # the card names a record this reader may not read
    return view


def read_thread(
    uow: UnitOfWork,
    record_id: str,
    *,
    actor: str,
    scope: str | None = None,
    limit: int = 50,
    before_seq: int | None = None,
) -> ThreadPage:
    """The newest ``limit`` messages (at most ``READ_THREAD_MAX_PAGE``) before ``before_seq``.

    Raises ``RecordNotFoundError`` when the record is not there or not readable by ``actor``.
    """
    record = readable_record(uow, record_id, actor=actor, scope=scope)
    conn = uow.conn()
    enabled = threads_enabled(conn, record.scope, record.record_type)
    if not enabled:  # switched off: nothing is shown, and nothing is said about what is stored
        return ThreadPage(
            record=record.ref(),
            enabled=False,
            dispatch_enabled=dispatch_enabled(conn, record.scope),
        )
    size = max(1, min(int(limit), READ_THREAD_MAX_PAGE))
    params: dict[str, Any] = {"record_id": record_id, "limit": size + 1}
    if before_seq is not None:
        params["before"] = before_seq
    rows = list(conn.execute(_NEWEST_SQL if before_seq is None else _BEFORE_SQL, params).all())
    older = len(rows) > size
    rows = list(reversed(rows[:size]))
    total = conn.execute(_THREAD_SQL, {"record_id": record_id}).first()
    hidden = _unreadable_names(conn, rows, viewer_of(conn, actor))
    return ThreadPage(
        record=record.ref(),
        enabled=True,
        dispatch_enabled=dispatch_enabled(conn, record.scope),
        message_count=0 if total is None else int(total.message_count),
        participants=[
            ThreadParticipant(
                actor=str(p.actor), reasons=[str(r) for r in as_list(load_json(p.reasons_json))]
            )
            for p in conn.execute(_PARTICIPANTS_SQL, {"record_id": record_id}).all()
        ],
        messages=[_view(row, hidden) for row in rows],
        seqs=[int(row.seq) for row in rows],
        kinds=[str(row.kind) for row in rows],
        next_before=int(rows[0].seq) if older and rows else None,
    )
