"""Seed data for the query-language tests (imported by tests as ``from query_seed import ...``).

Records of scope ``project:P123`` (key, type, status, interesting fields):

    W-001 piping.Weld   open    title "Bevel weld on spool 1"; nde.method RT, nde.count 3
    W-002 piping.Weld   closed  description "needs bevel check"; nde.method UT, nde.count 5
    W-003 piping.Weld   (none)  title "Cap weld"; no psets
    W-099 piping.Weld   open    voided
    NCR-001 quality.NCR open    title "Crack in weld"
    NCR-002 quality.NCR closed  title "Porosity"
    PRM-001 permit      open    title "Hot work permit"
    V-0001 piping.Valve open    title "Gate valve 100%_off"; valve_data size_in 4, tested true,
                                manufacturer Acme, due "2026-10-20"
and ``W-001`` again in scope ``project:P999``.

Links (written straight into ``cur_links``; the base has no link services to lean on):

    NCR-001 -> W-001   raised_against  active
    NCR-002 -> W-001   raised_against  retracted   (does not count)
    NCR-001 -> W-002   raised_against  active
    NCR-002 -> W-002   raised_against  stale
    W-002   -> PRM-001 requires        active
    W-003   -> PRM-001 requires        suggested   (does not count)

``created_at`` is set per record so date windows can be tested.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.sqlite.uow import SqliteUnitOfWork, create_schema, open_uow
from tl_core.ledger import NewEvent

SCOPE = "project:P123"

# key: (type, title, description, status, psets, created_at)
RECORDS: dict[str, tuple[str, str, str | None, str | None, dict[str, Any], str]] = {
    "W-001": (
        "piping.Weld",
        "Bevel weld on spool 1",
        None,
        "open",
        {"nde": {"method": "RT", "count": 3}},
        "2026-10-01T10:00:00.000000+00:00",
    ),
    "W-002": (
        "piping.Weld",
        "Root pass",
        "needs bevel check",
        "closed",
        {"nde": {"method": "UT", "count": 5}},
        "2026-10-05T23:30:00.000000+00:00",
    ),
    "W-003": ("piping.Weld", "Cap weld", None, None, {}, "2026-10-08T09:00:00.000000+00:00"),
    "W-099": ("piping.Weld", "Scrapped weld", None, "open", {}, "2026-10-02T09:00:00.000000+00:00"),
    "NCR-001": (
        "quality.NCR",
        "Crack in weld",
        None,
        "open",
        {},
        "2026-10-03T09:00:00.000000+00:00",
    ),
    "NCR-002": ("quality.NCR", "Porosity", None, "closed", {}, "2026-10-04T09:00:00.000000+00:00"),
    "PRM-001": ("permit", "Hot work permit", None, "open", {}, "2026-10-06T09:00:00.000000+00:00"),
    "V-0001": (
        "piping.Valve",
        "Gate valve 100%_off",
        None,
        "open",
        {
            "valve_data": {
                "size_in": 4,
                "tested": True,
                "manufacturer": "Acme",
                "due": "2026-10-20",
            }
        },
        "2026-10-09T08:00:00.000000+00:00",
    ),
}
LINKS = [
    ("L1", "NCR-001", "W-001", "raised_against", "active"),
    ("L2", "NCR-002", "W-001", "raised_against", "retracted"),
    ("L3", "NCR-001", "W-002", "raised_against", "active"),
    ("L4", "NCR-002", "W-002", "raised_against", "stale"),
    ("L5", "W-002", "PRM-001", "requires", "active"),
    ("L6", "W-003", "PRM-001", "requires", "suggested"),
]


def record_id(key: str, scope: str = SCOPE) -> str:
    return f"R-{scope}-{key}"


def create_record(
    uow: SqliteUnitOfWork,
    key: str,
    *,
    scope: str = SCOPE,
    record_type: str = "piping.Weld",
    title: str = "t",
    description: str | None = None,
    psets: dict[str, Any] | None = None,
) -> None:
    uow.append(
        stream_id=record_id(key, scope),
        stream_type="core.Record",
        scope=scope,
        expected_version=0,
        events=[
            NewEvent(
                event_type="Record.Created",
                payload={
                    "record_type": record_type,
                    "key": key,
                    "title": title,
                    "description": description,
                    "psets": psets or {},
                },
            )
        ],
        actor="user:t",
        source="test",
        correlation_id="c",
    )


def build_db(path: Path) -> None:
    """Create the schema at ``path`` and load the records and links described above."""
    create_schema(path)
    with open_uow(path) as uow:
        for key, (rtype, title, description, status, psets, created) in RECORDS.items():
            create_record(
                uow,
                key,
                record_type=rtype,
                title=title,
                description=description,
                psets=psets,
            )
            conn = uow.conn()
            conn.execute(
                text("UPDATE cur_core_record SET created_at = :c, updated_at = :c WHERE id = :id"),
                {"c": created, "id": record_id(key)},
            )
            if status is not None:
                conn.execute(
                    text("UPDATE cur_core_record SET status = :s WHERE id = :id"),
                    {"s": status, "id": record_id(key)},
                )
        create_record(uow, "W-001", scope="project:P999", title="Other project weld")
        uow.append(
            stream_id=record_id("W-099"),
            stream_type="core.Record",
            scope=SCOPE,
            expected_version=1,
            events=[NewEvent(event_type="Record.Voided", payload={"reason": "scrapped"})],
            actor="user:t",
            source="test",
            correlation_id="c",
        )
        for link_id, source, target, relation, status in LINKS:
            uow.conn().execute(
                text(
                    "INSERT INTO cur_links (link_id, scope, from_id, to_id, relation, status, "
                    "source, created_by, created_at, updated_at, version, last_seq) VALUES "
                    "(:l, :scope, :f, :t, :r, :s, 'manual', 'user:t', 'x', 'x', 1, 1)"
                ),
                {
                    "l": link_id,
                    "scope": SCOPE,
                    "f": record_id(source),
                    "t": record_id(target),
                    "r": relation,
                    "s": status,
                },
            )
