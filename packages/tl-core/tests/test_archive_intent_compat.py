"""A segment without intent is byte-identical to a pre-ADR-0025 one; one with intents round-trips.

The golden digests were taken from the code before the change, for the three events below.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from tl_core.archive.segments import (
    EVENT_COLUMNS,
    decode_ndjson,
    encode_ndjson,
    encode_parquet,
    event_line,
    parquet_matches,
    parquet_rows,
    recomputed_hash,
)
from tl_core.intent import Intent, IntentToward
from tl_core.ledger import Event, canonical_json, event_hash, iso_utc

GOLDEN_NDJSON = "3626a8aabd1f179968e9d4150b15b8ee41c0d1574237a57b5c2304024f809c70"
GOLDEN_PARQUET = "073cfa62d45644c44e842ba880d5e2c2e3da45c812529dcabb33d1c72235457e"
OLD_COLUMNS = [name for name, _ in EVENT_COLUMNS[:-1]]


def events(intents: dict[int, Intent] | None = None) -> list[Event]:
    out: list[Event] = []
    prev: str | None = None
    for i in range(1, 4):
        moment = datetime(2026, 1, 1, 0, 0, i, tzinfo=UTC)
        payload = {"n": i, "t": "café"}
        intent = (intents or {}).get(i)
        from tl_core.intent import intent_json

        digest = event_hash(
            prev,
            f"E{i:025d}",
            f"s{i}",
            1,
            "Thing.Created",
            canonical_json(payload),
            iso_utc(moment),
            intent_json(intent),
        )
        out.append(
            Event(
                event_type="Thing.Created",
                payload=payload,
                seq=i,
                event_id=f"E{i:025d}",
                stream_id=f"s{i}",
                stream_type="test.Thing",
                stream_version=1,
                scope="company",
                actor="user:u-1",
                recorded_at=moment,
                effective_at=moment,
                correlation_id=f"c-{i}",
                causation_id=None,
                source="test",
                prev_hash=prev,
                hash=digest,
                intent=intent,
            )
        )
        prev = digest
    return out


def test_a_segment_without_intent_is_byte_identical_to_the_pre_change_one() -> None:
    evs = events()
    assert hashlib.sha256(encode_ndjson(evs)).hexdigest() == GOLDEN_NDJSON
    assert hashlib.sha256(encode_parquet(evs)).hexdigest() == GOLDEN_PARQUET
    assert evs[0].hash == "d6ff6fedea762256f3aa94111781e1154f81aa74a7e50eef090fa980ea1f646f"


def test_the_line_has_no_intent_key_without_an_intent_and_never_null() -> None:
    for line in encode_ndjson(events()).splitlines():
        assert "intent" not in json.loads(line)


def test_a_segment_with_intents_round_trips_and_verifies() -> None:
    intents = {
        2: Intent(why="reason", toward=IntentToward(target="R-1", state="Done")),
        3: Intent(goal_ref="G-1"),
    }
    evs = events(intents)
    assert all(recomputed_hash(e) == e.hash for e in evs)
    again = decode_ndjson(encode_ndjson(evs))
    assert again == evs and all(recomputed_hash(e) == e.hash for e in again)
    assert json.loads(event_line(evs[1]))["intent"]["why"] == "reason"
    data = encode_parquet(evs)
    assert parquet_matches(data, evs)
    assert [row[-1] for row in parquet_rows(data)] == [
        None,
        evs[1].intent
        and canonical_json({"toward": {"state": "Done", "target": "R-1"}, "why": "reason"}),
        '{"goal_ref":"G-1"}',
    ]
    assert encode_parquet(evs) == data  # deterministic


def test_a_pre_change_parquet_without_the_column_reads_as_none(tmp_path: Path) -> None:
    evs = events()
    path = tmp_path / "old.parquet"
    columns = ", ".join(f"{n} {k}" for n, k in EVENT_COLUMNS[:-1])
    con = duckdb.connect(":memory:")
    con.execute("SET threads = 1")
    con.execute(f"CREATE TABLE events ({columns})")
    from tl_core.archive.segments import event_row

    con.executemany(
        f"INSERT INTO events VALUES ({', '.join('?' for _ in OLD_COLUMNS)})",
        [event_row(e)[:-1] for e in evs],
    )
    con.execute(f"COPY events TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.close()
    rows = parquet_rows(path.read_bytes())
    assert [r[-1] for r in rows] == [None, None, None]
    assert parquet_matches(path.read_bytes(), evs)


def test_an_old_line_still_validates() -> None:
    line = event_line(events()[0])
    assert Event.model_validate(json.loads(line)).intent is None
