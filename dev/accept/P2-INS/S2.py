"""P2-INS-S2 acceptance: the Checks read over five sources, and the telemetry write (SQLite)."""

from __future__ import annotations

import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/tl-core/tests/insights"))
from test_checks import SOURCES, USER, record_checks, record_facts, seed_world  # noqa: E402
from tl_adapters.db import create_schema, open_uow, rebuild_projections  # noqa: E402
from tl_core import telemetry  # noqa: E402

NOW = datetime(2026, 11, 1, tzinfo=UTC)
GOOD = dict(
    request_kind="check",
    trigger="request",
    record_type="awp.IWP",
    viewer_role="user",
    outcome="shown",
)


def ok(name: str, cond: bool) -> None:
    sys.exit(f"FAIL {name}") if not cond else print(f"PASS {name}")


def count(conn, sql: str = "SELECT COUNT(*) FROM telemetry_need") -> int:  # noqa: ANN001
    return int(conn.execute(text(sql)).scalar_one())


db = Path(tempfile.mkdtemp()) / "s2.db"
create_schema(db)
with open_uow(db) as uow:
    ids = seed_world(uow.conn())
with open_uow(db, readonly=True) as uow:
    conn = uow.conn()
    iwp, item = (record_facts(conn, ids[k], USER) for k in ("iwp", "corr"))
    assert iwp is not None and item is not None
    found = record_checks(conn, iwp, SOURCES, USER) + record_checks(conn, item, SOURCES, USER)
    sources = [f.source for f in found]
    ok(
        "one source each",
        {s: sources.count(s) for s in set(sources)}
        == {"readiness": 3, "constraints": 1, "expected_links": 1, "clocks": 1, "shortages": 1},
    )
    ok("no hidden key in any text", all("SECRET" not in f.model_dump_json() for f in found))
    ok(
        "checks read nothing hidden",
        ids["hidden"] not in " ".join(f.model_dump_json() for f in found),
    )

with open_uow(db) as uow:
    telemetry.note_need(uow.conn(), **GOOD, now=NOW)
    telemetry.note_need(uow.conn(), **GOOD, now=NOW)
    ok("append: two calls, two rows", count(uow.conn()) == 2)
    telemetry.note_need(uow.conn(), **GOOD, now=NOW + timedelta(days=400))
    ok("a row past retention is pruned", count(uow.conn()) == 1)
    telemetry._INSERT = text("INSERT INTO telemetry_nope VALUES (1)")  # force a database error
    telemetry.note_need(uow.conn(), **GOOD, now=NOW + timedelta(days=401))
    ok("a database error leaves the transaction usable", count(uow.conn(), "SELECT 1") == 1)
rebuild_projections(db)
with open_uow(db, readonly=True) as uow:
    ok("rebuild-projections keeps the rows", count(uow.conn()) == 1)
print("S2 ok")
