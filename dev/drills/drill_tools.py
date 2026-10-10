"""Helpers the restore drills call (brief 24.4, "restore drills"). Not part of the product.

Every subcommand takes ``--db TARGET`` (a SQLite file or a ``postgresql://`` URL) and prints one
line of ``key=value`` words so a shell script can read it:

  populate --records N   create N records, set pset values on some, link some; print head=<seq>
  append --count N       add N more records (the writes a backup may or may not have caught)
  head [--seq N]         print head=<seq> at=<recorded_at of the newest event, or of event N>
  digest                 print events=<sha> tables=<sha> over the ledger rows and every cur_* table
  probe                  append one event to prove the database accepts writes; print head=<seq>
  gap --from A --to B    seconds between two recorded_at values; print gap=<seconds>
  render                 fill docs/templates/restore-drill.md from a measurements file

The schema packages come from ``TL_SCHEMA_DIR`` (default ``schema/fixtures``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import create_schema, make_engine, open_uow, read_tx
from tl_core.projection.defaults import default_registry
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import CreateRecord
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.records import handle_create_record

SCOPE = "project:P123"


def _provider() -> DirectorySchemaProvider:
    return DirectorySchemaProvider(Path(os.environ.get("TL_SCHEMA_DIR", "schema/fixtures")))


def _create(db: str, key: str) -> Any:
    cmd = CreateRecord(
        actor="user:drill",
        source="drill",
        scope=SCOPE,
        record_type="core.Record",
        title=f"Drill record {key}",
        key=key,
    )
    with open_uow(db) as uow:
        return handle_create_record(uow, cmd)


def _head(db: str) -> tuple[int, str]:
    engine = make_engine(db)
    try:
        with read_tx(engine) as conn:
            row = conn.execute(
                text("SELECT seq, recorded_at FROM events ORDER BY seq DESC LIMIT 1")
            ).first()
    finally:
        engine.dispose()
    return (0, "") if row is None else (int(row[0]), str(row[1]))


def populate(db: str, records: int) -> None:
    create_schema(db)
    with use_provider(_provider()):
        made = [_create(db, f"D-{n:05d}") for n in range(1, records + 1)]
        for index, record in enumerate(made):
            if index % 3 == 0:
                cmd = SetPsetValues(
                    actor="user:drill",
                    source="drill",
                    scope=SCOPE,
                    stream_id=record.stream_id,
                    expected_version=record.version,
                    pset="valve_data",
                    layer="standard",
                    values={"size_in": 2 + index % 10, "manufacturer": "Acme"},
                )
                with open_uow(db) as uow:
                    handle_set_pset_values(uow, cmd)
            if index % 5 == 0 and index > 0:
                link = AddLink(
                    actor="user:drill",
                    source="drill",
                    scope=SCOPE,
                    from_id=record.stream_id,
                    to_id=made[index - 1].stream_id,
                )
                with open_uow(db) as uow:
                    handle_add_link(uow, link)
    print(f"head={_head(db)[0]}")


def append(db: str, count: int, prefix: str = "T") -> None:
    with use_provider(_provider()):
        stamp = _head(db)[0]
        for n in range(1, count + 1):
            _create(db, f"{prefix}-{stamp:06d}-{n:04d}")
    print(f"head={_head(db)[0]}")


def head(db: str, seq: int | None = None) -> None:
    """The newest event, or event ``seq``: ``head=<seq> at=<recorded_at>``."""
    if seq is None:
        newest, at = _head(db)
        print(f"head={newest} at={at}")
        return
    engine = make_engine(db)
    try:
        with read_tx(engine) as conn:
            row = conn.execute(
                text("SELECT recorded_at FROM events WHERE seq = :s"), {"s": seq}
            ).first()
    finally:
        engine.dispose()
    print(f"head={seq} at={'' if row is None else row[0]}")


def _current_tables(dialect: str) -> list[str]:
    names: set[str] = set()
    for projector in default_registry().all():
        for statement in projector.ddl(dialect):
            found = re.match(r"\s*CREATE TABLE IF NOT EXISTS (cur_\w+)", statement)
            if found:
                names.add(found.group(1))
    return sorted(names)


def digest(db: str) -> None:
    dialect = "postgres" if db.startswith("postgresql://") else "sqlite"
    engine = make_engine(db)
    try:
        with read_tx(engine) as conn:
            events = hashlib.sha256()
            for row in conn.execute(text("SELECT * FROM events ORDER BY seq")):
                events.update(json.dumps([str(v) for v in row]).encode())
            tables = hashlib.sha256()
            for table in _current_tables(dialect):
                found = conn.execute(text(f"SELECT * FROM {table}")).mappings().all()
                rows = sorted(json.dumps(sorted((k, str(v)) for k, v in r.items())) for r in found)
                tables.update(table.encode())
                for row_text in rows:
                    tables.update(row_text.encode())
    finally:
        engine.dispose()
    print(f"events={events.hexdigest()[:16]} tables={tables.hexdigest()[:16]}")


def gap(start: str, end: str) -> None:
    """Seconds from one recorded_at to another (``gap=<seconds>``); 0 if either is missing."""
    from datetime import datetime

    if not start or not end:
        print("gap=0.00")
        return
    seconds = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    print(f"gap={max(seconds, 0.0):.2f}")


def probe(db: str) -> None:
    with use_provider(_provider()):
        _create(db, f"PROBE-{_head(db)[0] + 1}")
    print(f"head={_head(db)[0]}")


def render(measurements: Path, template: Path, out: Path) -> None:
    """Fill ``{{key}}`` placeholders from ``key<TAB>value`` lines; unknown keys become ``n/a``."""
    values: dict[str, str] = {}
    for line in measurements.read_text(encoding="utf-8").splitlines():
        if "\t" in line:
            key, value = line.split("\t", 1)
            values[key] = value
    body = template.read_text(encoding="utf-8")
    body = re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), "n/a"), body)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(f"report={out}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("populate", "append", "head", "digest", "probe"):
        item = sub.add_parser(name)
        item.add_argument("--db", required=True)
        if name == "populate":
            item.add_argument("--records", type=int, default=100)
        if name == "head":
            item.add_argument("--seq", type=int, default=None)
        if name == "append":
            item.add_argument("--count", type=int, default=10)
            item.add_argument("--prefix", default="T")
    gap_parser = sub.add_parser("gap")
    gap_parser.add_argument("--from", dest="start", required=True)
    gap_parser.add_argument("--to", dest="end", required=True)
    rend = sub.add_parser("render")
    rend.add_argument("--measurements", type=Path, required=True)
    rend.add_argument("--template", type=Path, required=True)
    rend.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "populate":
        populate(args.db, args.records)
    elif args.command == "append":
        append(args.db, args.count, args.prefix)
    elif args.command == "head":
        head(args.db, args.seq)
    elif args.command == "digest":
        digest(args.db)
    elif args.command == "gap":
        gap(args.start, args.end)
    elif args.command == "probe":
        probe(args.db)
    else:
        render(args.measurements, args.template, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
