"""P2-INT-S1 acceptance: intent through both adapters, seal, restore, verify. One PASS per check.

``--keep PATH`` leaves the SQLite database at PATH. Postgres runs when ``TL_PG_URL`` is set.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import text
from tl_adapters.db import create_schema, make_engine, make_ledger, read_tx
from tl_adapters.restore import restore_from_archive
from tl_core.archive import ArchiveExistsError, generate_signer, seal_segment, verify_archive
from tl_core.archive.segments import recomputed_hash
from tl_core.intent import Intent, IntentRef, IntentToward, intent_json
from tl_core.ledger import NewEvent

INTENTS = [
    None,
    Intent(why="reason", next=[IntentRef(command="SignOff", target="R-1")]),
    Intent(),
    Intent(toward=IntentToward(target="R-1", state="Done"), goal_ref="G-1"),
]


class Store:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def put_bytes(self, key: str, data: bytes) -> None:
        if key in self.files:
            raise ArchiveExistsError(key)
        self.files[key] = data

    def get_bytes(self, key: str) -> bytes:
        return self.files[key]

    def exists(self, key: str) -> bool:
        return key in self.files

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self.files if k.startswith(prefix))


def rows(db: str | Path) -> list[tuple[object, ...]]:
    engine = make_engine(db)
    try:
        with read_tx(engine) as conn:
            return [tuple(r) for r in conn.execute(text("SELECT * FROM events ORDER BY seq")).all()]
    finally:
        engine.dispose()


def passed(label: str, ok: bool) -> None:
    print(f"{'PASS' if ok else 'FAIL'} {label}")
    if not ok:
        raise SystemExit(1)


def run(name: str, source: str | Path, target: str | Path) -> None:
    create_schema(source)
    engine = make_engine(source)
    ledger = make_ledger(engine)
    for i, intent in enumerate(INTENTS):
        ledger.append(
            stream_id=f"s{i}",
            stream_type="test.Thing",
            scope="company",
            expected_version=0,
            events=[NewEvent(event_type="Thing.Created", payload={"n": i}, intent=intent)],
            actor="user:accept",
            source="accept",
            correlation_id=f"c{i}",
        )
    events = [e for i in range(len(INTENTS)) for e in ledger.read_stream(f"s{i}")]
    passed(
        f"{name} append stores intent text",
        [intent_json(i) for i in INTENTS]
        == [None if e.intent is None else intent_json(e.intent) for e in events],
    )
    passed(
        f"{name} hash matches recomputed_hash", all(recomputed_hash(e) == e.hash for e in events)
    )
    signer, store = generate_signer(), Store()
    with read_tx(engine) as conn:
        sealed = seal_segment(conn, store, signer, max_events=10)
    engine.dispose()
    passed(f"{name} seal", sealed is not None)
    passed(f"{name} verify archive", verify_archive(store, public_key=signer.public_key) == [])
    restore_from_archive(store, target, public_key=signer.public_key)
    passed(f"{name} restore is verbatim", rows(target) == rows(source))
    engine = make_engine(target)
    try:
        with read_tx(engine) as conn:
            ok = verify_archive(store, public_key=signer.public_key, conn=conn) == []
    finally:
        engine.dispose()
    passed(f"{name} verify restored ledger", ok)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", type=Path, default=None)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        keep = args.keep
        if keep is not None:
            keep.parent.mkdir(parents=True, exist_ok=True)
            keep.unlink(missing_ok=True)
        run("sqlite", keep or base / "a.db", base / "b.db")
        url = os.environ.get("TL_PG_URL")
        if url:
            from tl_adapters.postgres import admin

            schemas = ["tl_s1_" + uuid.uuid4().hex[:12] for _ in range(2)]
            for schema in schemas:
                admin.create_schema_namespace(url, schema)
            try:
                run(
                    "postgres", admin.schema_url(url, schemas[0]), admin.schema_url(url, schemas[1])
                )
            finally:
                for schema in schemas:
                    admin.drop_schema_namespace(url, schema)
        else:
            print("SKIP postgres (TL_PG_URL not set)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
