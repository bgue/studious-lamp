"""What happened around a record (P2-INS-S1, INS-A1).

One read over ``outbox_events`` (one row per event, indexed on ``scope`` and ``subject_id``) finds
the candidate events by ``seq``; the events themselves come from the ledger table. Every candidate
passes the viewer filter before it counts toward the page, and the page is refilled until it holds
``limit + 1`` visible rows or a cap stops the call. The read writes nothing.

Which ``subject_id`` each event kind carries (``tl_core.webhooks.outbox``): record events, file
events (the record of the file), thread events (the record of the thread), numbering allocations and
the events of an IWP (its own stream) carry the record id; a link event carries the ``from`` record
(so links where the record is the ``to`` end are found through ``cur_links`` and the link stream);
a constraint event carries the constraint's own id (found through ``cur_core_constraint``); a
proposal event carries the proposal id (found through ``cur_proposals``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Connection, bindparam, text

from tl_core import confidentiality
from tl_core.archive.sealer import _event_from_row  # pyright: ignore[reportPrivateUsage]
from tl_core.insights.types import ActivityKind, ActivityPage, ActivityRow
from tl_core.intent import redact_events
from tl_core.ledger import Event
from tl_core.uow import UnitOfWork

#: The relations that make a linked record related, as ``schema/core/links.yaml`` spells them (the
#: schema has no ``blocked_by``, ``targeted_by`` or ``resolved_by``: the far end of the one stored
#: row is read from either side).
RELATED_RELATIONS = ("blocks", "targets", "resolves")
#: The only event types a related record contributes.
RELATED_EVENT_TYPES = (
    "Workflow.Transitioned",
    "Technical.Answered",
    "Correspondence.Responded",
    "ResponseClock.Met",
    "Constraint.Cleared",
    "Proposal.Accepted",
)
MAX_LINKS = 200
MAX_FAR_ENDS = 100
MAX_RELATED_ROWS = 30
MAX_PROPOSALS = 50
MAX_CONSTRAINTS = 100
MAX_CANDIDATES = 1000
MAX_ROUNDS = 5
_NEWEST = 2**62

_PREFIX_KIND: dict[str, ActivityKind] = {
    "Workflow.": "move",
    "Link.": "link",
    "File.": "file",
    "Thread.": "post",
    "Proposal.": "proposal",
    "Constraint.": "constraint",
}


def kind_of(event_type: str) -> ActivityKind:
    if event_type == "IWP.ReadinessEvaluated":
        return "check"
    for prefix, kind in _PREFIX_KIND.items():
        if event_type.startswith(prefix):
            return kind
    return "change"


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _in(sql: str, name: str) -> Any:
    return text(sql).bindparams(bindparam(name, expanding=True))


def _ids(conn: Connection, sql: str, params: dict[str, Any]) -> list[Any]:
    return list(conn.execute(text(sql), params))


def _visible(conn: Connection, events: Sequence[Event]) -> list[Event]:
    """What ``confidentiality.filter_events`` keeps, with a fixed number of statements: the ids that
    the payloads of the scanned streams name are looked up together, not one event at a time."""
    who = confidentiality.current_viewer()
    if who.system or not events or confidentiality.hidden_sql(who) is None:
        return list(events)
    streams = confidentiality.hidden_event_streams(
        conn, [(e.stream_id, e.stream_type) for e in events], who
    )
    named: dict[str, set[str]] = {}
    for e in events:
        if e.stream_id not in streams and e.stream_type in confidentiality.SCANNED_STREAM_TYPES:
            named[e.event_id] = confidentiality.payload_record_ids(e.payload)
    hidden_ids = confidentiality.hidden_among(
        conn, sorted({i for ids in named.values() for i in ids}), who
    )
    return [
        e
        for e in events
        if e.stream_id not in streams and not (named.get(e.event_id, set()) & hidden_ids)
    ]


def _load(conn: Connection, seqs: Sequence[int]) -> dict[int, Event]:
    if not seqs:
        return {}
    statement = _in(
        "SELECT seq, event_id, stream_id, stream_type, stream_version, event_type, "
        "schema_version, scope, payload, actor, recorded_at, effective_at, correlation_id, "
        "causation_id, source, intent, prev_hash, hash FROM events WHERE seq IN :seqs",
        "seqs",
    )
    rows = conn.execute(statement, {"seqs": list(seqs)}).mappings().all()
    return {int(row["seq"]): _event_from_row(row) for row in rows}


def _note(event: Event) -> str | None:
    if event.event_type != "IWP.ReadinessEvaluated":
        return None
    checks = event.payload.get("checks")
    if not isinstance(checks, list):
        return None
    ok = sum(1 for c in checks if isinstance(c, dict) and c.get("state") == "ok")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
    return f"{ok} of {len(checks)} ready"  # pyright: ignore[reportUnknownArgumentType]


def _decided_by(event: Event) -> str | None:
    if event.event_type in ("Proposal.Accepted", "Proposal.Rejected"):
        by = event.payload.get("by")
        return by if isinstance(by, str) else None
    return None


class _Sources:
    """The ids that widen the own-events read beyond ``subject_id = <record id>``."""

    def __init__(self, conn: Connection, record_id: str, scope: str) -> None:
        self.constraints = [
            str(r[0])
            for r in _ids(
                conn,
                "SELECT id FROM cur_core_constraint WHERE subject_id = :id "
                f"ORDER BY id DESC LIMIT {MAX_CONSTRAINTS}",
                {"id": record_id},
            )
        ]
        links = _ids(
            conn,
            "SELECT link_id, from_id FROM cur_links WHERE to_id = :id "
            f"ORDER BY updated_at DESC, link_id DESC LIMIT {MAX_LINKS}",
            {"id": record_id},
        )
        self.link_ids = [str(r[0]) for r in links]
        self.link_from = sorted({str(r[1]) for r in links})
        self.proposals = [
            str(r[0])
            for r in _ids(
                conn,
                "SELECT proposal_id, seq FROM cur_proposals WHERE result_stream_id = :id "
                "UNION SELECT proposal_id, seq FROM cur_proposals WHERE scope = :scope "
                "AND CAST(command_json AS TEXT) LIKE :pattern ESCAPE '\\' "
                f"ORDER BY seq DESC LIMIT {MAX_PROPOSALS}",
                {"id": record_id, "scope": scope, "pattern": _like(record_id)},
            )
        ]


def _own_candidates(
    conn: Connection, record_id: str, src: _Sources | None, cursor: int, n: int
) -> list[int]:
    if src is None:  # revisions only: the record's own stream
        clause, params = "subject_id = :id AND stream_id = :id", {}
    else:
        parts, params = ["subject_id = :id"], {}
        if src.constraints:
            parts.append("subject_id IN :cids")
            params["cids"] = src.constraints
        if src.link_ids:
            parts.append("(subject_id IN :lfrom AND stream_id IN :lids)")
            params["lfrom"], params["lids"] = src.link_from, src.link_ids
        if src.proposals:
            parts.append("subject_id IN :pids")
            params["pids"] = src.proposals
        clause = "(" + " OR ".join(parts) + ")"
    sql = (
        f"SELECT seq FROM outbox_events WHERE seq < :cursor AND {clause} ORDER BY seq DESC LIMIT :n"
    )
    statement = text(sql)
    for name in ("cids", "lfrom", "lids", "pids"):
        if name in params:
            statement = statement.bindparams(bindparam(name, expanding=True))
    rows = conn.execute(statement, {**params, "id": record_id, "cursor": cursor, "n": n})
    return [int(r[0]) for r in rows]


def _far_ends(conn: Connection, record_id: str) -> dict[str, str | None]:
    """The linked records of one hop (id -> key). A link with a hidden end is dropped in SQL."""
    from_ok, p1 = confidentiality.not_hidden_each("l.from_id")
    to_ok, p2 = confidentiality.not_hidden_each("l.to_id")
    relations = ", ".join(f"'{r}'" for r in RELATED_RELATIONS)
    statement = text(
        "SELECT r.id AS far_id, r.key AS far_key FROM ("
        "SELECT l.link_id, l.updated_at, "
        "CASE WHEN l.from_id = :id THEN l.to_id ELSE l.from_id END AS far "
        f"FROM cur_links l WHERE (l.from_id = :id OR l.to_id = :id) AND l.status = 'active' "
        f"AND l.relation IN ({relations}) AND {from_ok} AND {to_ok} "
        f"ORDER BY l.updated_at DESC, l.link_id DESC LIMIT {MAX_FAR_ENDS}) k "
        "JOIN cur_core_record r ON r.id = k.far"
    )
    rows = conn.execute(statement, {"id": record_id, **p1, **p2}).all()
    return {str(r.far_id): (None if r.far_key is None else str(r.far_key)) for r in rows}


def _related_candidates(
    conn: Connection, far: Sequence[str], cursor: int, n: int
) -> list[tuple[int, str]]:
    if not far or n <= 0:
        return []
    kinds = ", ".join(f"'{t}'" for t in RELATED_EVENT_TYPES)
    statement = _in(
        "SELECT seq, subject_id FROM outbox_events WHERE seq < :cursor AND subject_id IN :far "
        f"AND event_type IN ({kinds}) ORDER BY seq DESC LIMIT :n",
        "far",
    )
    rows = conn.execute(statement, {"far": list(far), "cursor": cursor, "n": n})
    return [(int(r.seq), str(r.subject_id)) for r in rows]


def record_activity(
    uow: UnitOfWork,
    record_id: str,
    *,
    revisions_only: bool = False,
    related: bool = True,
    before_seq: int | None = None,
    limit: int = 120,
) -> ActivityPage:
    """Newest-first activity of one record, ``limit`` rows older than ``before_seq``.

    A hidden or unknown record answers an empty page. Rows of the record's own stream, thread,
    files, constraints, proposals and links come first-class; ``related`` adds one hop of causal
    events of linked records (marked ``related``). Nothing is written."""
    conn = uow.conn()
    limit = max(1, min(limit, 200))
    visible_ok, vparams = confidentiality.not_hidden_each("r.id")
    head = conn.execute(
        text(f"SELECT r.scope FROM cur_core_record r WHERE r.id = :id AND {visible_ok}"),
        {"id": record_id, **vparams},
    ).first()
    if head is None:
        return ActivityPage(rows=[], next_before_seq=None)
    src = None if revisions_only else _Sources(conn, record_id, str(head[0]))
    far_keys = _far_ends(conn, record_id) if related and not revisions_only else {}
    far = sorted(far_keys)

    cursor = _NEWEST if before_seq is None else before_seq
    rows: list[ActivityRow] = []
    related_rows = 0
    scanned = 0
    exhausted = quota_stop = False
    for _ in range(MAX_ROUNDS):
        room = min(limit + 1 - len(rows), MAX_CANDIDATES - scanned)
        if room <= 0:
            break
        own = _own_candidates(conn, record_id, src, cursor, room)
        rel_cap = min(room, MAX_RELATED_ROWS + 1)
        rel = _related_candidates(conn, far, cursor, rel_cap)
        merged: dict[int, str | None] = {s: None for s in own}
        for seq, far_id in rel:
            merged.setdefault(seq, far_id)
        batch = sorted(merged, reverse=True)[:room]
        exhausted = len(own) < room and len(rel) < rel_cap and len(merged) <= room
        if not batch:
            break
        scanned += len(batch)
        cursor = batch[-1]
        events = _load(conn, batch)
        # An intent may name a record the viewer cannot read: "not available" (ADR-0025 d5).
        kept = {
            e.event_id: e
            for e in redact_events(conn, _visible(conn, [events[s] for s in batch if s in events]))
        }
        for seq in batch:
            event = events.get(seq)
            if event is None or event.event_id not in kept:
                continue
            event = kept[event.event_id]
            far_id = merged[seq]
            if far_id is not None:
                if related_rows >= MAX_RELATED_ROWS:
                    quota_stop = True
                    break
                related_rows += 1
            rows.append(
                ActivityRow(
                    event=event,
                    kind=kind_of(event.event_type),
                    related=far_id is not None,
                    from_id=far_id,
                    from_key=far_keys.get(far_id) if far_id is not None else None,
                    decided_by=_decided_by(event),
                    note=_note(event),
                )
            )
        if quota_stop or len(rows) > limit or exhausted:
            break
    if len(rows) > limit:
        rows = rows[:limit]
        return ActivityPage(rows=rows, next_before_seq=rows[-1].event.seq)
    if quota_stop and rows:
        return ActivityPage(rows=rows, next_before_seq=rows[-1].event.seq)
    return ActivityPage(rows=rows, next_before_seq=None if exhausted else cursor)
