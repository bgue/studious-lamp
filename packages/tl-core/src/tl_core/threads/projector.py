"""ThreadProjector: ``Thread.*`` events into ``cur_thread``, ``cur_thread_message`` and
``cur_thread_participant`` (brief 21.5).

Deterministic: every value comes from the event. A participant is the record's creator (first
message), an author, a mentioned person or a dispatcher. A mention is stored as typed, with
``user:`` in front when it has no namespace (``jsmith`` is ``user:jsmith``, ``crew:P-07`` stays
as it is); nothing here reads another projection.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.ledger import Event, iso_utc
from tl_core.threads.contract import (
    THREAD_DISPATCHED,
    THREAD_EVENT_TYPES,
    THREAD_MESSAGE_EDITED,
    THREAD_MESSAGE_POSTED,
    THREAD_MESSAGE_RETRACTED,
)
from tl_core.webhooks.rows import as_list, dumps, load_json

_INSERT_THREAD = text(
    "INSERT INTO cur_thread (record_id, scope, message_count, created_by, created_at, "
    "last_message_at, last_seq, version) VALUES (:record_id, :scope, 1, :created_by, :at, :at, "
    ":seq, :version)"
)
_BUMP_THREAD = text(
    "UPDATE cur_thread SET message_count = message_count + 1, last_message_at = :at, "
    "last_seq = :seq, version = :version WHERE record_id = :record_id"
)
_TOUCH_THREAD = text(
    "UPDATE cur_thread SET last_seq = :seq, version = :version WHERE record_id = :record_id"
)
_INSERT_MESSAGE = text(
    "INSERT INTO cur_thread_message (message_id, record_id, scope, seq, author, kind, body, "
    "mentions_json, record_refs_json, posted_at, edit_count, retracted) VALUES (:message_id, "
    ":record_id, :scope, :seq, :author, :kind, :body, :mentions, :record_refs, :at, 0, :no)"
)
_EDIT_MESSAGE = text(
    "UPDATE cur_thread_message SET body = :body, mentions_json = :mentions, "
    "record_refs_json = :record_refs, edit_count = edit_count + 1 "
    "WHERE message_id = :message_id AND retracted = :no"
)
_RETRACT_MESSAGE = text(
    "UPDATE cur_thread_message SET body = '', retracted = :yes, retract_reason = :reason "
    "WHERE message_id = :message_id"
)
_DISPATCH_MESSAGE = text(
    "UPDATE cur_thread_message SET dispatch_json = :dispatch WHERE message_id = :message_id"
)
_PARTICIPANT = text(
    "SELECT reasons_json FROM cur_thread_participant WHERE participant_row_id = :row_id"
)
_INSERT_PARTICIPANT = text(
    "INSERT INTO cur_thread_participant (participant_row_id, record_id, actor, reasons_json, "
    "first_seq) VALUES (:row_id, :record_id, :actor, :reasons, :seq)"
)
_UPDATE_PARTICIPANT = text(
    "UPDATE cur_thread_participant SET reasons_json = :reasons WHERE participant_row_id = :row_id"
)


def participant_of(mention: str) -> str:
    """The actor string a mention stands for: ``user:`` is added to a name without a namespace."""
    return mention if ":" in mention else f"user:{mention}"


class ThreadProjector:
    name = "threads"
    handles: frozenset[str] = frozenset(THREAD_EVENT_TYPES)

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return [
                statement
                for table in ("cur_thread", "cur_thread_message", "cur_thread_participant")
                for statement in statements(table, dialect)
            ]
        raise ValueError(f"unsupported dialect: {dialect}")

    def reset(self, conn: Connection) -> None:
        for table in ("cur_thread_participant", "cur_thread_message", "cur_thread"):
            conn.execute(text(f"DELETE FROM {table}"))

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type == THREAD_MESSAGE_POSTED:
            self._posted(conn, event)
        elif event.event_type == THREAD_MESSAGE_EDITED:
            self._edited(conn, event)
        elif event.event_type == THREAD_MESSAGE_RETRACTED:
            self._retracted(conn, event)
        elif event.event_type == THREAD_DISPATCHED:
            self._dispatched(conn, event)
        else:
            raise ValueError(f"ThreadProjector cannot apply: {event.event_type}")

    @staticmethod
    def _participant(conn: Connection, record_id: str, actor: str, reason: str, seq: int) -> None:
        row_id = f"{record_id}|{actor}"
        found = conn.execute(_PARTICIPANT, {"row_id": row_id}).first()
        if found is None:
            conn.execute(
                _INSERT_PARTICIPANT,
                {
                    "row_id": row_id,
                    "record_id": record_id,
                    "actor": actor,
                    "reasons": dumps([reason]),
                    "seq": seq,
                },
            )
            return
        reasons = [str(r) for r in as_list(load_json(found[0]))]
        if reason not in reasons:
            conn.execute(
                _UPDATE_PARTICIPANT,
                {"row_id": row_id, "reasons": dumps(sorted([*reasons, reason]))},
            )

    @classmethod
    def _mentions(cls, conn: Connection, event: Event, record_id: str) -> None:
        for mention in as_list(event.payload.get("mentions")):
            cls._participant(conn, record_id, participant_of(str(mention)), "mentioned", event.seq)

    @classmethod
    def _posted(cls, conn: Connection, event: Event) -> None:
        p: dict[str, Any] = event.payload
        record_id = str(p["record_id"])
        at = iso_utc(event.recorded_at)
        if event.stream_version == 1:
            conn.execute(
                _INSERT_THREAD,
                {
                    "record_id": record_id,
                    "scope": event.scope,
                    "created_by": p["author"],
                    "at": at,
                    "seq": event.seq,
                    "version": event.stream_version,
                },
            )
        else:
            conn.execute(
                _BUMP_THREAD,
                {
                    "record_id": record_id,
                    "at": at,
                    "seq": event.seq,
                    "version": event.stream_version,
                },
            )
        conn.execute(
            _INSERT_MESSAGE,
            {
                "message_id": p["message_id"],
                "record_id": record_id,
                "scope": event.scope,
                "seq": event.seq,
                "author": p["author"],
                "kind": p.get("kind", "message"),
                "body": p["body"],
                "mentions": dumps(as_list(p.get("mentions"))),
                "record_refs": dumps(as_list(p.get("record_refs"))),
                "at": at,
                "no": False,
            },
        )
        creator = p.get("record_creator")
        if isinstance(creator, str) and creator:
            cls._participant(conn, record_id, creator, "creator", event.seq)
        if p.get("kind", "message") in ("message", "dispatch"):
            cls._participant(conn, record_id, str(p["author"]), "author", event.seq)
        cls._mentions(conn, event, record_id)

    @classmethod
    def _edited(cls, conn: Connection, event: Event) -> None:
        p: dict[str, Any] = event.payload
        done = conn.execute(
            _EDIT_MESSAGE,
            {
                "message_id": p["message_id"],
                "body": p["body"],
                "mentions": dumps(as_list(p.get("mentions"))),
                "record_refs": dumps(as_list(p.get("record_refs"))),
                "no": False,
            },
        )
        if done.rowcount == 0:
            raise LookupError(f"no live message row {p['message_id']}")
        record_id = str(p["record_id"])
        conn.execute(
            _TOUCH_THREAD,
            {"record_id": record_id, "seq": event.seq, "version": event.stream_version},
        )
        cls._mentions(conn, event, record_id)

    @staticmethod
    def _retracted(conn: Connection, event: Event) -> None:
        p: dict[str, Any] = event.payload
        done = conn.execute(
            _RETRACT_MESSAGE,
            {"message_id": p["message_id"], "reason": p["reason"], "yes": True},
        )
        if done.rowcount == 0:
            raise LookupError(f"no message row {p['message_id']}")
        conn.execute(
            _TOUCH_THREAD,
            {"record_id": p["record_id"], "seq": event.seq, "version": event.stream_version},
        )

    @classmethod
    def _dispatched(cls, conn: Connection, event: Event) -> None:
        p: dict[str, Any] = event.payload
        outcome = {
            "message_id": p["message_id"],
            "verb": p["verb"],
            "results": as_list(p.get("results")),
            "link_ids": as_list(p.get("link_ids")),
            "summary": p.get("summary") or "",
        }
        done = conn.execute(
            _DISPATCH_MESSAGE, {"message_id": p["message_id"], "dispatch": dumps(outcome)}
        )
        if done.rowcount == 0:
            raise LookupError(f"no message row {p['message_id']}")
        record_id = str(p["record_id"])
        conn.execute(
            _TOUCH_THREAD,
            {"record_id": record_id, "seq": event.seq, "version": event.stream_version},
        )
        cls._participant(conn, record_id, event.actor, "dispatcher", event.seq)
