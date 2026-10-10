"""SettingProjector: ``Setting.*`` events into ``cur_setting`` and ``cur_setting_lock`` (brief 30).

One ``cur_setting`` row per ``Setting.Changed`` event (the per-key history and the resolver's
input), one ``cur_setting_lock`` row per key that was ever locked or bounded. Deterministic: every
value comes from the event. ``effective_us`` is the later of the time the event was recorded and
its ``applies_at``, so a change never takes effect before it was recorded and a rebuild gives the
same rows as the live run (the projector never reads a clock).

The projector also owns the operational table ``setting_effect_applied`` (see
``schema/core/settings.yaml``): it is created with the rest of the schema, written by
``tl projections rebuild`` and the server start, and never cleared by ``reset``.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.ledger import Event, iso_utc
from tl_core.settings.instants import to_us
from tl_core.settings.types import SETTING_CHANGED, SETTING_LOCKED

SETTING_EVENT_TYPES = frozenset({SETTING_CHANGED, SETTING_LOCKED})
TABLES = ("cur_setting", "cur_setting_lock", "setting_effect_applied")

_INSERT_SQL = text(
    "INSERT INTO cur_setting (change_id, key, layer, scope, value_json, reset, old_value_json, "
    "old_set, reason, actor, source, accept_risk, applies_at, effective_us, recorded_at, seq, "
    "version) VALUES (:change_id, :key, :layer, :scope, :value_json, :reset, :old_value_json, "
    ":old_set, :reason, :actor, :source, :accept_risk, :applies_at, :effective_us, :recorded_at, "
    ":seq, :version)"
)
_LOCK_UPDATE_SQL = text(
    "UPDATE cur_setting_lock SET locked = :locked, bounds_json = :bounds_json, reason = :reason, "
    "actor = :actor, seq = :seq, version = :version, recorded_at = :recorded_at WHERE key = :key"
)
_LOCK_INSERT_SQL = text(
    "INSERT INTO cur_setting_lock (key, locked, bounds_json, reason, actor, seq, version, "
    "recorded_at) VALUES (:key, :locked, :bounds_json, :reason, :actor, :seq, :version, "
    ":recorded_at)"
)


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class SettingProjector:
    name = "settings"
    handles = SETTING_EVENT_TYPES

    def ddl(self, dialect: str) -> list[str]:
        if dialect != "sqlite" and dialect != "postgres":
            raise ValueError(f"unsupported dialect: {dialect}")
        found: list[str] = []
        for table in TABLES:
            found.extend(statements(table, dialect))
        return found

    def reset(self, conn: Connection) -> None:
        """Clear the two projected tables. ``setting_effect_applied`` is operational and stays."""
        conn.execute(text("DELETE FROM cur_setting"))
        conn.execute(text("DELETE FROM cur_setting_lock"))

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type == SETTING_CHANGED:
            self._changed(conn, event)
        elif event.event_type == SETTING_LOCKED:
            self._locked(conn, event)
        else:
            raise ValueError(f"SettingProjector cannot apply: {event.event_type}")

    @staticmethod
    def _changed(conn: Connection, event: Event) -> None:
        payload = event.payload
        recorded_us = to_us(event.recorded_at)
        applies_at: str | None = None
        effective_us = recorded_us
        if payload.get("applies_at"):
            moment = datetime.fromisoformat(str(payload["applies_at"]))
            applies_at = iso_utc(moment)
            effective_us = max(recorded_us, to_us(moment))
        reset = bool(payload.get("reset", False))
        conn.execute(
            _INSERT_SQL,
            {
                "change_id": event.event_id,
                "key": payload["key"],
                "layer": payload["layer"],
                "scope": event.scope,
                "value_json": _dump(None if reset else payload.get("new_value")),
                "reset": reset,
                "old_value_json": _dump(payload.get("old_value")),
                "old_set": bool(payload.get("old_set", False)),
                "reason": payload.get("reason"),
                "actor": event.actor,
                "source": event.source,
                "accept_risk": bool(payload.get("accept_risk", False)),
                "applies_at": applies_at,
                "effective_us": effective_us,
                "recorded_at": iso_utc(event.recorded_at),
                "seq": event.seq,
                "version": event.stream_version,
            },
        )

    @staticmethod
    def _locked(conn: Connection, event: Event) -> None:
        payload = event.payload
        bounds = payload.get("bounds")
        params = {
            "key": payload["key"],
            "locked": bool(payload["locked"]),
            "bounds_json": None if bounds is None else _dump(bounds),
            "reason": payload.get("reason") or "",
            "actor": event.actor,
            "seq": event.seq,
            "version": event.stream_version,
            "recorded_at": iso_utc(event.recorded_at),
        }
        if conn.execute(_LOCK_UPDATE_SQL, params).rowcount == 0:
            conn.execute(_LOCK_INSERT_SQL, params)
