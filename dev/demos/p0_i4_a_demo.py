"""Demo for P0-I4 workstream A: the filter language and the change feed (run by P0-I4-A.sh)."""

from __future__ import annotations

import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.sqlite.engine import make_engine
from tl_adapters.sqlite.ledger import SqliteLedger
from tl_adapters.sqlite.uow import create_schema, open_uow
from tl_core.bus import Bus, InProcessBus
from tl_core.changefeed import (
    ChangePoller,
    SubscriptionFilter,
    SubscriptionOverflow,
    SubscriptionRegistry,
    fetch_changes,
)
from tl_core.ledger import Event, NewEvent
from tl_core.query import QuerySpec, QuerySyntaxError, parse, run_query, to_text, use_clock

SCOPE = "project:P123"
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)

# key, type, title, status, psets, created_at
RECORDS = [
    (
        "W-001",
        "piping.Weld",
        "Bevel weld on spool 1",
        "open",
        {"nde": {"method": "RT"}},
        "2026-10-01",
    ),
    (
        "W-002",
        "piping.Weld",
        "Root pass, bevel check",
        "closed",
        {"nde": {"method": "UT"}},
        "2026-10-05",
    ),
    ("W-003", "piping.Weld", "Cap weld", None, {}, "2026-10-08"),
    ("NCR-001", "quality.NCR", "Crack in weld", "open", {}, "2026-10-03"),
    ("NCR-002", "quality.NCR", "Porosity", "closed", {}, "2026-10-04"),
    ("PRM-001", "permit", "Hot work permit", "open", {}, "2026-10-06"),
    ("V-0001", "piping.Valve", "Gate valve", "open", {"valve_data": {"size_in": 4}}, "2026-10-09"),
]
LINKS = [  # from, to, relation, status
    ("NCR-001", "W-001", "raised_against", "active"),
    ("NCR-001", "W-002", "raised_against", "active"),
    ("NCR-002", "W-002", "raised_against", "stale"),
    ("W-002", "PRM-001", "requires", "active"),
    ("W-003", "PRM-001", "requires", "suggested"),
]


def step(title: str) -> None:
    print(f"\n== {title}")


def fail(message: str) -> None:
    print(f"DEMO FAILED: {message}", file=sys.stderr)
    sys.exit(1)


def rid(key: str) -> str:
    return f"R-{key}"


def create(
    db: Path,
    key: str,
    record_type: str,
    title: str,
    psets: dict[str, Any],
    *,
    bus: Bus | None = None,
) -> None:
    with open_uow(db, bus=bus) as uow:
        uow.append(
            stream_id=rid(key),
            stream_type="core.Record",
            scope=SCOPE,
            expected_version=0,
            events=[
                NewEvent(
                    event_type="Record.Created",
                    payload={
                        "record_type": record_type,
                        "key": key,
                        "title": title,
                        "psets": psets,
                    },
                )
            ],
            actor="user:demo",
            source="demo",
            correlation_id="demo",
        )


def seed(db: Path) -> None:
    create_schema(db)
    for key, record_type, title, status, psets, created in RECORDS:
        create(db, key, record_type, title, psets)
        with open_uow(db) as uow:
            uow.conn().execute(
                text(
                    "UPDATE cur_core_record SET status = :s, created_at = :c, updated_at = :c "
                    "WHERE id = :id"
                ),
                {"s": status, "c": f"{created}T09:00:00.000000+00:00", "id": rid(key)},
            )
    with open_uow(db) as uow:
        for n, (source, target, relation, status) in enumerate(LINKS):
            uow.conn().execute(
                text(
                    "INSERT INTO cur_links (link_id, scope, from_id, to_id, relation, status, "
                    "source, created_by, created_at, updated_at, version, last_seq) VALUES "
                    "(:l, :scope, :f, :t, :r, :s, 'manual', 'demo', 'x', 'x', 1, 1)"
                ),
                {
                    "l": f"L{n}",
                    "scope": SCOPE,
                    "f": rid(source),
                    "t": rid(target),
                    "r": relation,
                    "s": status,
                },
            )


def queries(db: Path) -> None:
    expectations: list[tuple[str, set[str]]] = [
        ("status:open", {"W-001", "NCR-001", "PRM-001", "V-0001"}),
        ("-status:open", {"W-002", "W-003", "NCR-002"}),
        ("type:piping.Weld status:open OR key:PRM-001", {"W-001", "PRM-001"}),
        ("bevel", {"W-001", "W-002"}),
        ("psets.nde.method=RT", {"W-001"}),
        ("psets.valve_data.size_in>=2", {"V-0001"}),
        ("created_at<=-5d", {"W-001", "NCR-001", "NCR-002"}),
        ("created_at>=today", {"V-0001"}),
        ("linked:NCR", {"W-001", "W-002"}),
        ("linked(raised_against).status:closed", {"W-002", "NCR-001", "NCR-002"}),
        ("linked:NCR.status:open", {"W-001", "W-002"}),
        ("count(linked:NCR)>1", {"W-002"}),
        ("missing(link:permit)", {"W-001", "W-003", "NCR-001", "NCR-002", "PRM-001", "V-0001"}),
    ]
    with open_uow(db, readonly=True) as uow, use_clock(NOW):
        for query, expected in expectations:
            rows = run_query(uow, QuerySpec(scope=SCOPE, where=parse(query), limit=None))
            keys = sorted(str(row["key"]) for row in rows)
            print(f"{query:50s} -> {', '.join(keys) or '(none)'}")
            if set(keys) != expected:
                fail(f"{query!r} returned {keys}, expected {sorted(expected)}")
        ordered = run_query(
            uow, QuerySpec(scope=SCOPE, order_by=[("psets.nde.method", "desc")], limit=2)
        )
        print(
            f"{'order by psets.nde.method desc, limit 2':50s} -> "
            f"{', '.join(str(r['key']) for r in ordered)}"
        )
    step("a syntax error carries its position")
    bad = "status:open version>=abc"
    try:
        parse(bad)
    except QuerySyntaxError as error:
        print(bad)
        print(" " * error.position + "^ " + str(error))
        if error.position != bad.index("abc"):
            fail("the error position is wrong")
    else:
        fail("a bad query parsed")
    step("a hostile value is data, not SQL")
    hostile = "'; DROP TABLE events;--"
    create(db, "EVIL", "test.Hostile", hostile, {})
    with open_uow(db, readonly=True) as uow:
        query = f'title:"{hostile}"'
        rows = run_query(uow, QuerySpec(scope=SCOPE, where=parse(query)))
        print(
            f"{query} -> {[r['key'] for r in rows]}; events table intact: "
            f"{uow.conn().execute(text('SELECT COUNT(*) FROM events')).scalar_one()} events"
        )
        if [r["key"] for r in rows] != ["EVIL"]:
            fail("the hostile title was not found as data")
    step("the AST prints back as query text")
    text_back = to_text(parse("status:open (linked:NCR OR count(linked)>2) -type:permit"))
    print(text_back)


def wait_for(got: list[int], count: int) -> None:
    for _ in range(1000):
        if len(got) >= count:
            return
        time.sleep(0.01)
    fail(f"expected {count} events, saw {got}")


def feed(db: Path) -> None:
    step("change feed: the in-process bus and a poller in another connection feed one registry")
    bus = InProcessBus()
    reader_engine = make_engine(db)
    reader = SqliteLedger(reader_engine)
    start = reader.head_seq()
    registry = SubscriptionRegistry(reader)
    registry.attach(bus)
    everything: list[int] = []
    welds: list[Event] = []
    registry.subscribe(lambda event: everything.append(event.seq))
    registry.subscribe(
        welds.append,
        SubscriptionFilter.of(scope=SCOPE, event_types=["Record.*"], record_ids=[rid("W-9")]),
    )
    with ChangePoller(reader, registry, interval_s=0.01):
        create(db, "W-9", "piping.Weld", "Written in this process", {}, bus=bus)  # via the bus
        create(db, "W-10", "piping.Weld", "Written by another process", {})  # no bus: poller only
        wait_for(everything, 2)
        time.sleep(0.1)  # the poller offers the bus event again; it must not repeat
    print(f"seqs delivered once each, in order: {everything}")
    if everything != [start + 1, start + 2]:
        fail(f"unexpected delivery {everything}")
    if [e.stream_id for e in welds] != [rid("W-9")]:
        fail("the record-id filter delivered the wrong events")

    step("a client resumes from its last seq (fetch_changes pages, then a replaying subscription)")
    page = fetch_changes(reader, after_seq=start, limit=1)
    print(
        f"page 1: seq {[e.seq for e in page.events]}, next_seq={page.next_seq}, "
        f"more={page.has_more}"
    )
    rest = fetch_changes(reader, after_seq=page.next_seq, limit=10)
    print(
        f"page 2: seq {[e.seq for e in rest.events]}, next_seq={rest.next_seq}, "
        f"more={rest.has_more}"
    )
    replayed: list[int] = []
    fresh = SubscriptionRegistry(reader)
    fresh.subscribe(lambda e: replayed.append(e.seq), after_seq=page.next_seq)
    print(f"resumed subscription saw: {replayed}")
    if replayed != [e.seq for e in rest.events] or page.has_more is not True or rest.has_more:
        fail("resume did not continue exactly after the stored seq")

    step("a slow queue consumer is cut off with a resume point instead of blocking writers")
    sub = registry.subscribe_queue(after_seq=start, maxsize=1)  # two events wait; one fits
    first = sub.get()
    try:
        sub.get()
    except SubscriptionOverflow as overflow:
        print(
            f"got seq {first.seq if first else None}, then overflow: "
            f"resume after seq {overflow.resume_seq}"
        )
        again = registry.subscribe_queue(after_seq=overflow.resume_seq, maxsize=1)
        last = again.get()
        if first is None or last is None or (first.seq, last.seq) != (start + 1, start + 2):
            fail("the resumed queue did not continue where the overflow stopped")
    else:
        fail("the queue did not overflow")
    reader_engine.dispose()


def main() -> None:
    with tempfile.TemporaryDirectory() as workdir:
        db = Path(workdir) / "tl.db"
        step("seed: 7 records in project:P123, 5 links (one suggested, one stale)")
        seed(db)
        step("queries (the clock is fixed at 2026-10-09 12:00 UTC)")
        queries(db)
        feed(db)
    print("\nP0-I4-A demo ok")


if __name__ == "__main__":
    main()
