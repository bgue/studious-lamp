"""A scripted history synced in several steps equals a single load and the ledger, on each adapter.

The `ledger` fixture follows `--adapters`, so this runs on SQLite by default and on SQLite and
Postgres under `just test-parity`. It covers what differs between the two dialects: the snapshot
transaction, JSONB payloads (the lake stores canonical JSON text), timestamptz and boolean columns,
and promoted columns added mid-history.
"""

from __future__ import annotations

import json

from builder import OTHER_SCOPE, LedgerBuilder
from lakecheck import assert_lake_matches_ledger, do_sync, lake_dump
from tl_lake import LakeConfig


def test_incremental_steps_equal_one_load_and_the_ledger(
    ledger: LedgerBuilder, lake: LakeConfig
) -> None:
    a = ledger.record("A-1")
    b = ledger.record("B-1")
    x = ledger.record("X-1", scope=OTHER_SCOPE)
    do_sync(ledger, lake)
    ledger.values(a, "valve_data", {"size_in": 4, "manufacturer": "Acme"})  # promotes columns
    link = ledger.link(a, b)
    do_sync(ledger, lake)
    ledger.update(b, title="Renamed", description="d")
    ledger.values(x, "valve_data", {"manufacturer": "Other"})
    ledger.retract(link)
    do_sync(ledger, lake)
    ledger.values(a, "valve_data", {"size_in": None, "manufacturer": None})
    ledger.void(x)
    do_sync(ledger, lake)

    single = LakeConfig.at(lake.lake_dir.parent / "single")
    do_sync(ledger, single)
    assert_lake_matches_ledger(ledger, lake, single)


def test_bronze_payloads_are_canonical_json_and_hashes_reverify(
    ledger: LedgerBuilder, lake: LakeConfig
) -> None:
    from tl_core.ledger import canonical_json, event_hash

    a = ledger.record("A-1")
    ledger.values(a, "valve_data", {"manufacturer": "Acme", "size_in": 2})
    do_sync(ledger, lake)
    names, _, rows = lake_dump(lake, "events")
    assert rows
    previous: dict[str, str | None] = {}
    for row in sorted(rows, key=lambda r: r[names.index("seq")]):
        event = dict(zip(names, row, strict=True))
        payload = json.loads(event["payload"])
        assert event["payload"] == canonical_json(payload)  # same text on SQLite and Postgres
        assert event["prev_hash"] == previous.get(event["scope"])
        expected = event_hash(
            event["prev_hash"],
            event["event_id"],
            event["stream_id"],
            event["stream_version"],
            event["event_type"],
            event["payload"],
            event["recorded_at"],
        )
        assert event["hash"] == expected, event["seq"]
        previous[event["scope"]] = event["hash"]
