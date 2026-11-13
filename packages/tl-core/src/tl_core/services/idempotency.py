"""Idempotency keys (P2-X1): a retry with the same key never writes twice.

``check`` claims ``(actor, key)`` inside the caller's transaction (an ``INSERT ... ON CONFLICT DO
NOTHING``, which both dialects accept) and ``record`` stores the ids the command produced in the
same transaction, so the claim commits with the command's events or not at all. Nothing here
commits, and nothing here logs: the key is never in a log record or an error text. A replay keeps
no response text; ``replay_result`` re-reads the ids through the viewer filter (ADR-0016).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import BaseModel
from sqlalchemy import Connection, bindparam, text
from tl_schema.ddl_loader import statements

from tl_core.confidentiality import Viewer, hidden_among
from tl_core.ledger import Event
from tl_core.services.commands import KEY_PATTERN, KEY_REFUSED, CommandResult
from tl_core.services.errors import RecordNotFoundError, ServiceError

#: Left out of the body hash: they change on a retry without changing the request.
EXCLUDED = frozenset({"idempotency_key", "correlation_id", "causation_id"})

MISMATCH_TEXT = "this Idempotency-Key was already used for a different request; nothing was written"
IN_PROGRESS_TEXT = "a request with this Idempotency-Key is still in progress; retry shortly"


class InvalidIdempotencyKeyError(ServiceError):
    """The key is not 1 to 128 printable ASCII characters (the text never holds the key)."""


class IdempotencyMismatch(ServiceError):
    """The key was used for another command or another body; nothing was written."""


class IdempotencyInProgress(ServiceError):
    """A concurrent claim of the same (actor, key) has not completed."""


@dataclass(frozen=True)
class Replay:
    """The stored answer: the command name and the result ids (stream id, then event ids)."""

    command: str
    result_ids: list[str]


_CLAIM = text(
    "INSERT INTO idempotency_key (actor, idem_key, command, body_hash, result_json, created_at) "
    "VALUES (:actor, :key, :command, :hash, NULL, :now) ON CONFLICT (actor, idem_key) DO NOTHING"
)
_FIND = text(
    "SELECT command, body_hash, result_json FROM idempotency_key "
    "WHERE actor = :actor AND idem_key = :key"
)
_RECORD = text(
    "UPDATE idempotency_key SET result_json = :ids WHERE actor = :actor AND idem_key = :key"
)


def validate_key(key: str) -> str:
    """The key, or ``InvalidIdempotencyKeyError`` with a fixed text."""
    if KEY_PATTERN.fullmatch(key) is None:
        raise InvalidIdempotencyKeyError(KEY_REFUSED)
    return key


def body_hash(body: object) -> str:
    """SHA-256 (hex) of the canonical JSON of ``body`` without the key and trace ids."""
    plain: Any
    if isinstance(body, BaseModel):
        plain = body.model_dump(mode="json")
    else:
        plain = json.loads(json.dumps(body, default=str))
    if isinstance(plain, dict):
        fields = cast("dict[str, Any]", plain)
        plain = {k: v for k, v in fields.items() if k not in EXCLUDED}
    canonical = json.dumps(plain, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def check(
    conn: Connection, actor: str, key: str | None, command: str, body: object
) -> Replay | None:
    """``None`` when ``key`` is ``None`` or new (a claim row is inserted in the caller's
    transaction); a ``Replay`` when the same (actor, key, command, body hash) completed.

    Raises ``IdempotencyMismatch`` for another command or body, ``IdempotencyInProgress`` when a
    claim exists that was not completed, ``InvalidIdempotencyKeyError`` for a bad key.
    """
    if key is None:
        return None
    validate_key(key)
    digest = body_hash(body)
    claimed = conn.execute(
        _CLAIM, {"actor": actor, "key": key, "command": command, "hash": digest, "now": _now()}
    )
    if claimed.rowcount == 1:
        return None
    row = conn.execute(_FIND, {"actor": actor, "key": key}).first()
    if row is None:  # the winner rolled back between our insert and our read: claim again
        conn.execute(
            _CLAIM, {"actor": actor, "key": key, "command": command, "hash": digest, "now": _now()}
        )
        return None
    if row[0] != command or row[1] != digest:
        raise IdempotencyMismatch(MISMATCH_TEXT)
    if row[2] is None:
        raise IdempotencyInProgress(IN_PROGRESS_TEXT)
    return Replay(command=row[0], result_ids=list(json.loads(row[2])))


def record(conn: Connection, actor: str, key: str | None, result_ids: list[str]) -> None:
    """Store the ids the command produced on the claim ``check`` made, in the same transaction."""
    if key is None:
        return
    conn.execute(_RECORD, {"actor": actor, "key": key, "ids": json.dumps(result_ids)})


def result_ids_of(result: CommandResult) -> list[str]:
    """The ids to record for a command's result: the stream id, then the event ids."""
    return [str(result.stream_id), *(str(event.event_id) for event in result.events)]


_SEQS = text("SELECT seq FROM events WHERE event_id IN :ids").bindparams(
    bindparam("ids", expanding=True)
)
_KEY_OF = text("SELECT key FROM cur_core_record WHERE id = :id")


def replay_result(conn: Connection, replay: Replay, viewer: Viewer | None = None) -> CommandResult:
    """The ``CommandResult`` of a replay, re-read from the ledger through the viewer filter.

    A stream the viewer can no longer see answers as one that does not exist
    (``RecordNotFoundError``: the status and text of an absent record).
    """
    from tl_core.archive.sealer import read_events

    stream_id, *event_ids = replay.result_ids
    if hidden_among(conn, [stream_id], viewer):
        raise RecordNotFoundError(f"no record {stream_id!r}")
    wanted = set(event_ids)
    events: list[Event] = []
    if wanted:
        seqs = [int(r[0]) for r in conn.execute(_SEQS, {"ids": sorted(wanted)})]
        if seqs:
            events = [e for e in read_events(conn, min(seqs), max(seqs)) if e.event_id in wanted]
    version = max((e.stream_version for e in events if e.stream_id == stream_id), default=0)
    found = conn.execute(_KEY_OF, {"id": stream_id}).first()
    return CommandResult(
        stream_id=stream_id,
        key=None if found is None else found[0],
        version=version,
        events=events,
    )


class IdempotencyTables:
    """Creates ``idempotency_key`` with the rest of the schema; handles no event, never reset.

    The table is operational (no event produces it, a rebuild must not clear it), so it rides on a
    projector that handles nothing: the pattern of ``JobQueueTables`` and ``WebhookStateTables``.
    """

    name = "idempotency_state"
    handles: frozenset[str] = frozenset()

    def ddl(self, dialect: str) -> list[str]:
        if dialect != "sqlite" and dialect != "postgres":
            raise ValueError(f"unsupported dialect: {dialect}")
        return list(statements("idempotency_key", dialect))

    def apply(self, conn: Connection, event: Event) -> None:
        raise ValueError(f"{self.name} handles no events, got {event.event_type}")

    def reset(self, conn: Connection) -> None:
        """Deliberately empty: a key is operational state, not derived from the ledger."""
