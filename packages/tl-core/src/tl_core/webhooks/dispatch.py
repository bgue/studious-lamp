"""The dispatcher: fans committed outbox rows out to subscriptions as deliveries (brief 18.4).

``outbox_events`` holds one row per event. The dispatcher reads rows after its cursor in ``seq``
order, applies each active subscription's filter, builds the signed-body text once (payload mode,
confidentiality policy) and inserts one ``wh_delivery`` row per match. Everything for one pass
happens in one transaction, so a crash repeats the pass and the unique ``(subscription, dedupe
key)``
index makes the repeat harmless.

Which events a subscription receives: those committed after it was created or last enabled
(``active_from_seq``) and, if it was disabled, up to the disable (``active_until_seq``); within its
scope (a project subscription sees its own project; a company subscription sees every scope); that
pass ``WebhookFilter.matches_row`` and, if set, the ``record_selector`` evaluated against the
subject
record's **current** state at dispatch time; that are before its ``expires_at``.

Postgres sequences can become visible out of order (L-P0-I4-A2). Workstream A serialises appends so
commit order equals ``seq`` order; ``lag_window`` is a second line of defence: each pass also re-
reads
that many rows before the cursor, and the unique index drops the ones already dispatched.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text

from tl_core.query.api import QuerySpec, count_query, parse
from tl_core.query.ast import And, Compare
from tl_core.services.queries import get_record_by_id
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid
from tl_core.webhooks.base import Clock, UowFactory, iso_z, parse_iso, utc_now
from tl_core.webhooks.envelope import (
    ConfidentialityPolicy,
    OpenPolicy,
    build_envelope,
    effective_mode,
    to_body,
)
from tl_core.webhooks.filters import WebhookFilter
from tl_core.webhooks.rows import OUTBOX_COLUMNS, OutboxRow
from tl_core.webhooks.uris import UriConfig

log = logging.getLogger(__name__)

CURSOR_NAME = "outbox"
PAGE = 500

_SUBSCRIPTION_COLUMNS = (
    "subscription_id, scope, name, owner, target_url, filter_json, payload_mode, status, "
    "active_from_seq, active_until_seq, expires_at, current_secret_id, version"
)
_INSERT_DELIVERY = text(
    "INSERT INTO wh_delivery (delivery_id, subscription_id, dedupe_key, seq, event_id, subject_id, "
    "origin, status, body, attempts, created_at, next_attempt_at, replay_of) VALUES "
    "(:delivery_id, :subscription_id, :dedupe_key, :seq, :event_id, :subject_id, :origin, "
    "'pending', :body, 0, :now, :now, :replay_of) ON CONFLICT DO NOTHING"
)
_DELIVERY_EXISTS = text(
    "SELECT 1 FROM wh_delivery "
    "WHERE subscription_id = :subscription_id AND dedupe_key = :dedupe_key"
)
_LINKS_SQL = text(
    "SELECT l.relation AS rel, l.to_id AS id, r.type AS type, r.key AS key FROM cur_links l "
    "LEFT JOIN cur_core_record r ON r.id = l.to_id "
    "WHERE l.from_id = :id AND l.status = 'active' ORDER BY l.relation, l.to_id"
)


@dataclass(frozen=True)
class SubscriptionRow:
    """``cur_webhook_subscription`` as delivery uses it."""

    subscription_id: str
    scope: str
    name: str
    owner: str
    target_url: str
    filter: WebhookFilter
    payload_mode: str
    status: str
    active_from_seq: int
    active_until_seq: int | None
    expires_at: datetime | None
    current_secret_id: str | None
    version: int

    @staticmethod
    def from_mapping(row: Mapping[Any, Any]) -> SubscriptionRow:
        from tl_core.webhooks.rows import load_json

        return SubscriptionRow(
            subscription_id=row["subscription_id"],
            scope=row["scope"],
            name=row["name"],
            owner=row["owner"],
            target_url=row["target_url"],
            filter=WebhookFilter.from_dict(load_json(row["filter_json"])),
            payload_mode=row["payload_mode"],
            status=row["status"],
            active_from_seq=int(row["active_from_seq"]),
            active_until_seq=None
            if row["active_until_seq"] is None
            else int(row["active_until_seq"]),
            expires_at=None if row["expires_at"] is None else parse_iso(str(row["expires_at"])),
            current_secret_id=row["current_secret_id"],
            version=int(row["version"]),
        )

    def receives(self, row: OutboxRow) -> bool:
        """Whether ``row`` falls inside this subscription's window, scope and expiry."""
        if row.seq <= self.active_from_seq:
            return False
        if self.active_until_seq is not None and row.seq > self.active_until_seq:
            return False
        if self.scope != "company" and self.scope != row.scope:
            return False
        return not (self.expires_at is not None and parse_iso(row.recorded_at) >= self.expires_at)


def load_subscriptions(conn: Connection, ids: Sequence[str] | None = None) -> list[SubscriptionRow]:
    """Every subscription (or the named ones), oldest first."""
    sql = f"SELECT {_SUBSCRIPTION_COLUMNS} FROM cur_webhook_subscription"
    params: dict[str, Any] = {}
    if ids is not None:
        marks = ", ".join(f":i{n}" for n in range(len(ids)))
        sql += f" WHERE subscription_id IN ({marks})" if ids else " WHERE 1 = 0"
        params = {f"i{n}": value for n, value in enumerate(ids)}
    rows = conn.execute(text(sql + " ORDER BY created_at, subscription_id"), params).mappings()
    return [SubscriptionRow.from_mapping(row) for row in rows]


def record_matches(uow: UnitOfWork, row: OutboxRow, selector: str) -> bool:
    """Whether the subject record of ``row`` matches the query-language ``selector`` right now.

    A subject that is not a record in ``cur_core_record`` matches nothing. Voided records are
    included, so a ``Record.Voided`` event can still be selected.
    """
    where = parse(selector)
    pinned = Compare("id", "=", row.subject_id)
    spec = QuerySpec(
        scope=row.scope,
        where=pinned if where is None else And((pinned, where)),
        include_voided=True,
        limit=None,
    )
    return count_query(uow, spec) > 0


@dataclass
class DispatchStats:
    read: int = 0
    created: int = 0
    cursor: int = 0


class Dispatcher:
    def __init__(
        self,
        open_uow: UowFactory,
        *,
        uris: UriConfig | None = None,
        policy: ConfidentialityPolicy | None = None,
        clock: Clock = utc_now,
        lag_window: int = 0,
    ) -> None:
        self._open = open_uow
        self._uris = uris if uris is not None else UriConfig()
        self._policy: ConfidentialityPolicy = policy if policy is not None else OpenPolicy()
        self._clock = clock
        self._lag = lag_window

    # --- live fan-out ------------------------------------------------------------------------

    def run_once(self, *, limit: int = PAGE) -> DispatchStats:
        """Dispatch up to ``limit`` outbox rows after the cursor. Returns what it did."""
        with self._open() as uow:
            conn = uow.conn()
            cursor = self._cursor(conn)
            start = max(0, cursor - self._lag)
            rows = self._read(conn, "seq > :start", {"start": start}, limit)
            stats = DispatchStats(read=len(rows), cursor=cursor)
            if not rows:
                return stats
            subscriptions = load_subscriptions(conn)
            now = iso_z(self._clock())
            for row in rows:
                for sub in subscriptions:
                    if self._wanted(uow, sub, row) and self._enqueue(
                        uow, sub, row, str(row.seq), "live", now
                    ):
                        stats.created += 1
            stats.cursor = max(cursor, rows[-1].seq)
            if stats.cursor != cursor:
                self._set_cursor(conn, stats.cursor)
            return stats

    def run_until_idle(self, *, limit: int = PAGE) -> DispatchStats:
        """Repeat :meth:`run_once` until a pass neither advances the cursor nor creates a
        delivery."""
        total = DispatchStats()
        while True:
            stats = self.run_once(limit=limit)
            total.read += stats.read
            total.created += stats.created
            advanced = stats.cursor > total.cursor
            total.cursor = max(total.cursor, stats.cursor)
            if not advanced and stats.created == 0:
                return total

    # --- operator actions --------------------------------------------------------------------

    def replay(self, subscription_id: str, from_seq: int, to_seq: int) -> int:
        """Re-send events ``from_seq..to_seq`` to one subscription; returns deliveries created.

        Rows are chosen with the subscription's **current** filter and rendered in its current
        payload
        mode, but ignore the active window (replay exists to cover gaps). Receivers dedupe on the
        event id. Works for a disabled subscription (deliveries wait until it is enabled).
        """
        if from_seq > to_seq:
            raise ValueError("from_seq must not be greater than to_seq")
        return self._replay(
            subscription_id, "seq >= :lo AND seq <= :hi", {"lo": from_seq, "hi": to_seq}
        )

    def replay_between(self, subscription_id: str, since: datetime, until: datetime) -> int:
        """Replay the events recorded in ``[since, until]``."""
        if since > until:
            raise ValueError("since must not be after until")
        return self._replay(
            subscription_id,
            "recorded_at >= :lo AND recorded_at <= :hi",
            {"lo": iso_z(since), "hi": iso_z(until)},
        )

    def redrive(self, subscription_id: str, delivery_ids: Sequence[str] | None = None) -> int:
        """Re-enqueue dead-lettered deliveries of one subscription (all of them, or the named ones).

        Each dead delivery becomes ``redriven`` and a fresh pending delivery with the same body is
        created, so the history of failures stays. Returns the number re-enqueued.
        """
        with self._open() as uow:
            conn = uow.conn()
            sql = (
                "SELECT delivery_id, seq, event_id, subject_id, body FROM wh_delivery "
                "WHERE subscription_id = :s AND status = 'dead'"
            )
            params: dict[str, Any] = {"s": subscription_id}
            if delivery_ids is not None:
                if not delivery_ids:
                    return 0
                marks = ", ".join(f":d{n}" for n in range(len(delivery_ids)))
                sql += f" AND delivery_id IN ({marks})"
                params.update({f"d{n}": value for n, value in enumerate(delivery_ids)})
            dead = conn.execute(text(sql + " ORDER BY seq, delivery_id"), params).mappings().all()
            now = iso_z(self._clock())
            for old in dead:
                new_id = new_ulid()
                conn.execute(
                    text(
                        "UPDATE wh_delivery SET status = 'redriven' WHERE delivery_id = :id "
                        "AND status = 'dead'"
                    ),
                    {"id": old["delivery_id"]},
                )
                conn.execute(
                    _INSERT_DELIVERY,
                    {
                        "delivery_id": new_id,
                        "subscription_id": subscription_id,
                        "dedupe_key": f"{old['seq']}:redrive:{new_id}",
                        "seq": old["seq"],
                        "event_id": old["event_id"],
                        "subject_id": old["subject_id"],
                        "origin": "redrive",
                        "body": old["body"],
                        "now": now,
                        "replay_of": old["delivery_id"],
                    },
                )
            return len(dead)

    # --- internals ---------------------------------------------------------------------------

    def _replay(self, subscription_id: str, where: str, params: dict[str, Any]) -> int:
        with self._open() as uow:
            conn = uow.conn()
            subs = load_subscriptions(conn, [subscription_id])
            if not subs:
                raise LookupError(f"no webhook subscription {subscription_id}")
            sub = subs[0]
            created = 0
            now = iso_z(self._clock())
            cursor = 0
            while True:
                page = self._read(
                    conn, f"({where}) AND seq > :after", {**params, "after": cursor}, PAGE
                )
                if not page:
                    return created
                for row in page:
                    in_scope = sub.scope == "company" or sub.scope == row.scope
                    if in_scope and self._matches(uow, sub, row):
                        key = f"{row.seq}:replay:{new_ulid()}"
                        if self._enqueue(uow, sub, row, key, "replay", now):
                            created += 1
                cursor = page[-1].seq

    def _wanted(self, uow: UnitOfWork, sub: SubscriptionRow, row: OutboxRow) -> bool:
        return sub.receives(row) and self._matches(uow, sub, row)

    def _matches(self, uow: UnitOfWork, sub: SubscriptionRow, row: OutboxRow) -> bool:
        if not sub.filter.matches_row(row):
            return False
        selector = sub.filter.record_selector
        return selector is None or record_matches(uow, row, selector)

    def _enqueue(
        self, uow: UnitOfWork, sub: SubscriptionRow, row: OutboxRow, key: str, origin: str, now: str
    ) -> bool:
        conn = uow.conn()
        if conn.execute(
            _DELIVERY_EXISTS, {"subscription_id": sub.subscription_id, "dedupe_key": key}
        ).first():
            return False
        if not self._policy.allows(row, sub.owner):
            return False
        body = self.render_body(uow, row, sub.payload_mode)
        result = conn.execute(
            _INSERT_DELIVERY,
            {
                "delivery_id": new_ulid(),
                "subscription_id": sub.subscription_id,
                "dedupe_key": key,
                "seq": row.seq,
                "event_id": row.event_id,
                "subject_id": row.subject_id,
                "origin": origin,
                "body": body,
                "now": now,
                "replay_of": None,
            },
        )
        return result.rowcount == 1

    def render_body(self, uow: UnitOfWork, row: OutboxRow, requested_mode: str) -> str:
        """The signed-body text for ``row`` in the mode the policy allows."""
        mode = effective_mode(self._policy, row, requested_mode)
        links: list[dict[str, Any]] = []
        record: dict[str, Any] | None = None
        if mode != "thin":
            links = self._links(uow.conn(), row)
            if mode == "full":
                record = get_record_by_id(uow, row.subject_id)
        return to_body(build_envelope(row, mode, self._uris, links=links, record=record))

    @staticmethod
    def _links(conn: Connection, row: OutboxRow) -> list[dict[str, Any]]:
        found: dict[tuple[str, str | None], dict[str, Any]] = {}
        for own in row.data.get("links", []):
            found[(own["rel"], own.get("id"))] = {
                "rel": own["rel"],
                "id": own.get("id"),
                "type": None,
                "key": None,
            }
        for link in conn.execute(_LINKS_SQL, {"id": row.subject_id}).mappings():
            found[(link["rel"], link["id"])] = dict(link)
        return sorted(found.values(), key=lambda item: (item["rel"], item["id"] or ""))

    @staticmethod
    def _read(conn: Connection, where: str, params: dict[str, Any], limit: int) -> list[OutboxRow]:
        sql = f"SELECT {OUTBOX_COLUMNS} FROM outbox_events WHERE {where} ORDER BY seq LIMIT :limit"
        result = conn.execute(text(sql), {**params, "limit": limit}).mappings()
        return [OutboxRow.from_mapping(row) for row in result]

    @staticmethod
    def _cursor(conn: Connection) -> int:
        row = conn.execute(
            text("SELECT last_seq FROM wh_cursor WHERE name = :n"), {"n": CURSOR_NAME}
        ).first()
        if row is None:
            conn.execute(
                text(
                    "INSERT INTO wh_cursor (name, last_seq) VALUES (:n, 0) ON CONFLICT DO NOTHING"
                ),
                {"n": CURSOR_NAME},
            )
            return 0
        return int(row.last_seq)

    @staticmethod
    def _set_cursor(conn: Connection, seq: int) -> None:
        conn.execute(
            text("UPDATE wh_cursor SET last_seq = :seq WHERE name = :n"),
            {"seq": seq, "n": CURSOR_NAME},
        )
