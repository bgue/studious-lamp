"""WebhookSubscriptionProjector: ``WebhookSubscription.*`` events into ``cur_webhook_subscription``.

One row per subscription. Deterministic: every value comes from the event (the secret itself is
never in an event; only ``secret_id`` is). ``active_windows`` lists the ``seq`` intervals in which
the subscription receives events: creation and every enable open one, a disable closes the open
one, so events committed while it was disabled are not delivered unless an operator replays them.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.ledger import Event, iso_utc
from tl_core.webhooks.rows import as_list, as_object, dumps, load_json

SUBSCRIPTION_STREAM_TYPE = "core.WebhookSubscription"
CREATED = "WebhookSubscription.Created"
UPDATED = "WebhookSubscription.Updated"
DISABLED = "WebhookSubscription.Disabled"
ENABLED = "WebhookSubscription.Enabled"
SECRET_ROTATED = "WebhookSubscription.SecretRotated"
SUBSCRIPTION_EVENT_TYPES = frozenset({CREATED, UPDATED, DISABLED, ENABLED, SECRET_ROTATED})

#: changes-field name to column name. Column names never come from event data.
_UPDATABLE_COLUMNS: dict[str, str] = {
    "name": "name",
    "integration_app": "integration_app",
    "target_url": "target_url",
    "filter": "filter_json",
    "payload_mode": "payload_mode",
    "event_schema_version": "event_schema_version",
    "expires_at": "expires_at",
}
UPDATABLE_FIELDS = frozenset(_UPDATABLE_COLUMNS)

_INSERT_SQL = text(
    "INSERT INTO cur_webhook_subscription (subscription_id, scope, name, owner, integration_app, "
    "target_url, filter_json, payload_mode, event_schema_version, status, disabled_reason, "
    "active_windows_json, expires_at, current_secret_id, created_by, created_at, updated_at, "
    "version, last_seq) VALUES (:subscription_id, :scope, :name, :owner, :integration_app, "
    ":target_url, :filter_json, :payload_mode, :event_schema_version, 'active', NULL, "
    ":active_windows, :expires_at, :current_secret_id, :created_by, :created_at, :updated_at, "
    ":version, :last_seq)"
)


def _load_windows(conn: Connection, subscription_id: str) -> list[dict[str, Any]]:
    row = conn.execute(
        text("SELECT active_windows_json FROM cur_webhook_subscription WHERE subscription_id = :s"),
        {"s": subscription_id},
    ).first()
    if row is None:
        raise LookupError(f"no subscription row for stream {subscription_id}")
    return [dict(as_object(item)) for item in as_list(load_json(row[0]))]


class WebhookSubscriptionProjector:
    name = "webhook_subscriptions"
    handles = SUBSCRIPTION_EVENT_TYPES

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return statements("cur_webhook_subscription", dialect)
        raise ValueError(f"unsupported dialect: {dialect}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_webhook_subscription"))

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type == CREATED:
            self._create(conn, event)
        elif event.event_type in SUBSCRIPTION_EVENT_TYPES:
            self._change(conn, event)
        else:
            raise ValueError(f"WebhookSubscriptionProjector cannot apply: {event.event_type}")

    @staticmethod
    def _create(conn: Connection, event: Event) -> None:
        payload = event.payload
        stamp = iso_utc(event.recorded_at)
        conn.execute(
            _INSERT_SQL,
            {
                "subscription_id": event.stream_id,
                "scope": event.scope,
                "name": payload["name"],
                "owner": payload["owner"],
                "integration_app": payload.get("integration_app"),
                "target_url": payload["target_url"],
                "filter_json": dumps(payload.get("filter") or {}),
                "payload_mode": payload.get("payload_mode", "thin"),
                "event_schema_version": payload.get("event_schema_version", "v1"),
                "active_windows": dumps([{"from": event.seq, "until": None}]),
                "expires_at": payload.get("expires_at"),
                "current_secret_id": payload.get("secret_id"),
                "created_by": event.actor,
                "created_at": stamp,
                "updated_at": stamp,
                "version": event.stream_version,
                "last_seq": event.seq,
            },
        )

    @staticmethod
    def _change(conn: Connection, event: Event) -> None:
        payload = event.payload
        changes: dict[str, Any] = {
            "version": event.stream_version,
            "last_seq": event.seq,
            "updated_at": iso_utc(event.recorded_at),
        }
        if event.event_type == UPDATED:
            raw_changes = as_object(payload.get("changes"))
            for name in raw_changes:
                column = _UPDATABLE_COLUMNS.get(name)
                if column is None:
                    raise ValueError(f"cannot update subscription field {name!r}")
                new = as_list(raw_changes[name])[1]
                changes[column] = dumps(new) if name == "filter" else new
        elif event.event_type == DISABLED:
            windows = _load_windows(conn, event.stream_id)
            if windows and windows[-1]["until"] is None:
                windows[-1]["until"] = event.seq
            changes.update(
                status="disabled",
                disabled_reason=payload.get("reason", "owner"),
                active_windows_json=dumps(windows),
            )
        elif event.event_type == ENABLED:
            windows = _load_windows(conn, event.stream_id)
            windows.append({"from": event.seq, "until": None})
            changes.update(
                status="active",
                disabled_reason=None,
                active_windows_json=dumps(windows),
            )
        elif event.event_type == SECRET_ROTATED:
            changes["current_secret_id"] = payload["secret_id"]
        assignments = ", ".join(f"{column} = :{column}" for column in changes)
        updated = conn.execute(
            text(
                f"UPDATE cur_webhook_subscription SET {assignments} "
                "WHERE subscription_id = :subscription_id"
            ),
            {**changes, "subscription_id": event.stream_id},
        )
        if updated.rowcount == 0:
            raise LookupError(f"no subscription row for stream {event.stream_id}")
