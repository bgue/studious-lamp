"""Test vectors and behaviour for canonical JSON, UTC formatting, and the event hash chain."""

import hashlib
from datetime import UTC, datetime, timedelta, timezone

import pytest
from tl_core.ledger.hashing import canonical_json, event_hash, iso_utc

EVENT_ID = "01J00000000000000000000000"
RECORDED_AT = "2026-01-01T00:00:00.000000+00:00"
PAYLOAD = '{"a":1}'

VECTOR_1 = "69d2a9ba6e245b32d4fb2ab928026347dfd99bbb0ef866c11faf19256a84469d"
VECTOR_2 = "aadeb1f9ad0da9535605bbf2ed35c6fd7cc3b63fe85775fe6ccdca22936e1eb5"


def _recompute(prev: str, stream_version: int) -> str:
    parts = [prev, EVENT_ID, "s1", str(stream_version), "Record.Created", PAYLOAD, RECORDED_AT]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def test_vector_1_no_prev_hash() -> None:
    got = event_hash(None, EVENT_ID, "s1", 1, "Record.Created", PAYLOAD, RECORDED_AT)
    assert got == VECTOR_1


def test_vector_2_chained_to_vector_1() -> None:
    got = event_hash(VECTOR_1, EVENT_ID, "s1", 1, "Record.Created", PAYLOAD, RECORDED_AT)
    assert got == VECTOR_2


def test_vectors_match_independent_recomputation() -> None:
    assert _recompute("", 1) == VECTOR_1
    assert _recompute(VECTOR_1, 1) == VECTOR_2
    assert event_hash(
        None, EVENT_ID, "s1", 1, "Record.Created", PAYLOAD, RECORDED_AT
    ) == _recompute("", 1)


def test_prev_hash_none_and_empty_string_are_equivalent() -> None:
    assert event_hash("", EVENT_ID, "s1", 1, "Record.Created", PAYLOAD, RECORDED_AT) == VECTOR_1


def test_canonical_json_stable_under_key_order_and_nested_dicts() -> None:
    assert canonical_json({"b": 1, "a": {"d": 1, "c": 2}}) == '{"a":{"c":2,"d":1},"b":1}'
    assert canonical_json({"a": {"c": 2, "d": 1}, "b": 1}) == '{"a":{"c":2,"d":1},"b":1}'


def test_canonical_json_preserves_non_ascii() -> None:
    assert canonical_json({"k": "é"}) == '{"k":"é"}'


def test_iso_utc_formats_utc_datetime() -> None:
    assert iso_utc(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-01-01T00:00:00.000000+00:00"


def test_iso_utc_converts_offset_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    moment = datetime(2026, 1, 1, 2, 0, 0, tzinfo=plus_two)
    assert iso_utc(moment) == "2026-01-01T00:00:00.000000+00:00"


def test_iso_utc_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        iso_utc(datetime(2026, 1, 1))
