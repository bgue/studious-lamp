"""Demo clause 2 for dev/demos/P2-INT.sh: the hash of an event with an intent.

Usage: ``uv run python dev/accept/P2-INT/demo_archive_lake.py DB``

Reads the first event of the ledger DB that carries an intent (through ``tl_adapters.db``, the
ledger's own ``read_stream``), recomputes its hash with the core hashing function
(``tl_core.archive.segments.recomputed_hash``) and checks two things: the stored hash equals the
hash over the stored intent, and it differs from the hash the same event would have had without
the intent. Prints ``PASS clause 2: ...`` on success; a miss prints ``FAIL ...`` and exits 1.
The URL is never printed.
"""

from __future__ import annotations

import sys

from sqlalchemy import text
from tl_adapters.db import as_target, display_target, make_engine, make_ledger, read_tx
from tl_core.archive.segments import recomputed_hash


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: demo_archive_lake.py DB", file=sys.stderr)
        return 2
    target = as_target(argv[1])
    engine = make_engine(target)
    try:
        with read_tx(engine) as conn:
            row = conn.execute(
                text("SELECT stream_id FROM events WHERE intent IS NOT NULL ORDER BY seq LIMIT 1")
            ).first()
        if row is None:
            print("FAIL no event with an intent in the ledger")
            return 1
        events = make_ledger(engine).read_stream(row[0])
    finally:
        engine.dispose()
    with_intent = [e for e in events if e.intent is not None]
    if not with_intent:
        print(f"FAIL the stream {row[0]} has no event with an intent")
        return 1
    event = with_intent[0]
    stored = event.hash
    with_hash = recomputed_hash(event)
    without_hash = recomputed_hash(event.model_copy(update={"intent": None}))
    ok = stored == with_hash and stored != without_hash
    print(
        f"{'PASS' if ok else 'FAIL'} clause 2: the intent event's hash is over its intent and "
        f"differs from the hash without intent (ledger {display_target(target)})"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
