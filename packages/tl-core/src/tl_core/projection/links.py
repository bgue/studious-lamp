"""LinkProjector: link events into ``cur_links`` and ``cur_link_counts`` (brief 7.1, 5.4).

One row per link. Both directions of a link are read from the same row: outbound by ``from_id``,
inbound by ``to_id``. A retracted link keeps its row (links are never deleted). Every event also
refreshes ``cur_link_counts`` for both records of the link.

Deterministic: the new row depends only on the event and on the rows already in the database. The
status that follows an event comes from ``tl_core.links.lifecycle.next_status``. It must be
registered after ``RecordProjector`` (it reads the record's scope for the counts row).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.ledger import Event, iso_utc
from tl_core.links.lifecycle import CREATING_EVENTS, LINK_EVENT_TYPES, next_status

_INSERT_LINK_SQL = text(
    "INSERT INTO cur_links (link_id, scope, from_id, to_id, relation, status, pin, note, "
    "source, confidence, reason, declined, verified_by, verified_at, created_by, created_at, "
    "updated_at, version, last_seq) VALUES (:link_id, :scope, :from_id, :to_id, :relation, "
    ":status, :pin, :note, :source, :confidence, :reason, :declined, :verified_by, "
    ":verified_at, :created_by, :created_at, :updated_at, :version, :last_seq)"
)
_LOAD_LINK_SQL = text("SELECT status, from_id, to_id FROM cur_links WHERE link_id = :link_id")
# One statement refreshes the counts row of one record end. The aggregate has no GROUP BY, so it
# returns exactly one row even when no link matches: the first event for a record inserts, later
# ones hit ON CONFLICT and update. The WHERE clause is required (SQLite parses INSERT ... SELECT ...
# ON CONFLICT ambiguously without it). Every value is a bound parameter.
_UPSERT_COUNTS_SQL = text(
    "INSERT INTO cur_link_counts (record_id, scope, active_out, active_in, stale, broken, "
    "suggested, last_seq) "
    "SELECT :record_id, "
    "COALESCE((SELECT scope FROM cur_core_record WHERE id = :record_id), :scope), "
    "COALESCE(SUM(CASE WHEN status = 'active' AND from_id = :record_id THEN 1 ELSE 0 END), 0), "
    "COALESCE(SUM(CASE WHEN status = 'active' AND to_id = :record_id THEN 1 ELSE 0 END), 0), "
    "COALESCE(SUM(CASE WHEN status = 'stale' THEN 1 ELSE 0 END), 0), "
    "COALESCE(SUM(CASE WHEN status = 'broken' THEN 1 ELSE 0 END), 0), "
    "COALESCE(SUM(CASE WHEN status = 'suggested' THEN 1 ELSE 0 END), 0), "
    ":last_seq "
    "FROM cur_links WHERE from_id = :record_id OR to_id = :record_id "
    "ON CONFLICT (record_id) DO UPDATE SET scope = excluded.scope, "
    "active_out = excluded.active_out, active_in = excluded.active_in, "
    "stale = excluded.stale, broken = excluded.broken, suggested = excluded.suggested, "
    "last_seq = excluded.last_seq"
)


class LinkProjector:
    name = "links"
    handles = LINK_EVENT_TYPES

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return statements("cur_links", dialect) + statements("cur_link_counts", dialect)
        raise ValueError(f"unsupported dialect: {dialect}")

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type in CREATING_EVENTS:
            from_id, to_id = self._create(conn, event)
        else:
            from_id, to_id = self._change(conn, event)
        for record_id in (from_id, to_id):
            self._refresh_counts(conn, record_id, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_links"))
        conn.execute(text("DELETE FROM cur_link_counts"))

    def _create(self, conn: Connection, event: Event) -> tuple[Any, Any]:
        payload = event.payload
        stamp = iso_utc(event.recorded_at)
        source = payload.get("source") or "manual"
        conn.execute(
            _INSERT_LINK_SQL,
            {
                "link_id": event.stream_id,
                "scope": event.scope,
                "from_id": payload["from_ref"],
                "to_id": payload["to_ref"],
                "relation": payload["relation"],
                "status": next_status(None, event.event_type),
                "pin": payload.get("pin"),
                "note": payload.get("note"),
                "source": source,
                "confidence": payload.get("confidence"),
                "reason": None,
                "declined": False,
                "verified_by": None,
                "verified_at": None,
                "created_by": event.actor,
                "created_at": stamp,
                "updated_at": stamp,
                "version": event.stream_version,
                "last_seq": event.seq,
            },
        )
        return payload["from_ref"], payload["to_ref"]

    def _change(self, conn: Connection, event: Event) -> tuple[Any, Any]:
        payload = event.payload
        row = conn.execute(_LOAD_LINK_SQL, {"link_id": event.stream_id}).first()
        if row is None:
            raise LookupError(f"no cur_links row for stream {event.stream_id}")
        changes: dict[str, Any] = {
            "status": next_status(row.status, event.event_type, flag=payload.get("status")),
            "version": event.stream_version,
            "last_seq": event.seq,
            "updated_at": iso_utc(event.recorded_at),
        }
        if event.event_type == "Link.Accepted":
            if payload.get("note") is not None:
                changes["note"] = payload["note"]
        elif event.event_type == "Link.Declined":
            changes["declined"] = True
            changes["reason"] = payload.get("reason")
        elif event.event_type == "Link.Repinned":
            changes["pin"] = payload.get("pin")
        elif event.event_type == "Link.Verified":
            changes["verified_by"] = event.actor
            changes["verified_at"] = iso_utc(event.recorded_at)
        elif event.event_type in ("Link.Flagged", "Link.Retracted"):
            changes["reason"] = payload.get("reason")
        self._update_link(conn, event.stream_id, changes)
        return row.from_id, row.to_id

    @staticmethod
    def _update_link(conn: Connection, link_id: str, changes: dict[str, Any]) -> None:
        # Column names are fixed literals chosen in ``_change``; only values come from the event.
        assignments = ", ".join(f"{column} = :{column}" for column in changes)
        conn.execute(
            text(f"UPDATE cur_links SET {assignments} WHERE link_id = :link_id"),
            {**changes, "link_id": link_id},
        )

    @staticmethod
    def _refresh_counts(conn: Connection, record_id: str, event: Event) -> None:
        conn.execute(
            _UPSERT_COUNTS_SQL,
            {"record_id": record_id, "scope": event.scope, "last_seq": event.seq},
        )
