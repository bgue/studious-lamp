"""GasTestProjector: ``GasTest.Recorded`` makes the row. A reading is a fact: nothing changes it."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_permits.names import (
    GAS_TEST_EVENTS,
    GAS_TEST_RECORDED,
    GAS_TEST_TABLE,
    GAS_TEST_VIEW,
)
from tl_mod_permits.projectors._common import aware, ddl_for, reading, touch_record

_INSERT = text(
    f"INSERT INTO {GAS_TEST_TABLE} (id, scope, permit_id, taken_at, tester, instrument_text, "
    "o2_pct, lel_pct, h2s_ppm, co_ppm, result, note, last_seq) VALUES (:id, :scope, :permit_id, "
    ":taken_at, :tester, :instrument_text, :o2_pct, :lel_pct, :h2s_ppm, :co_ppm, :result, "
    ":note, :last_seq)"
)


class GasTestProjector:
    name = "permits_gas_test"
    handles = GAS_TEST_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(GAS_TEST_TABLE, dialect) + ddl_for(GAS_TEST_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type != GAS_TEST_RECORDED:
            raise ValueError(f"GasTestProjector cannot apply event type: {event.event_type}")
        payload: dict[str, Any] = event.payload
        conn.execute(
            _INSERT,
            {
                "id": event.stream_id,
                "scope": event.scope,
                "permit_id": payload["permit_id"],
                "taken_at": aware(payload["taken_at"]),
                "tester": payload["tester"],
                "instrument_text": payload.get("instrument_text"),
                "o2_pct": reading(payload.get("o2_pct")),
                "lel_pct": reading(payload.get("lel_pct")),
                "h2s_ppm": reading(payload.get("h2s_ppm")),
                "co_ppm": reading(payload.get("co_ppm")),
                "result": payload["result"],
                "note": payload.get("note"),
                "last_seq": event.seq,
            },
        )
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {GAS_TEST_TABLE}"))
