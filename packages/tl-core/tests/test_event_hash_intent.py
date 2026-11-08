"""The optional intent part of the event hash (ADR-0025): none keeps the old digest."""

from __future__ import annotations

import pytest
from tl_core.intent import (
    Intent,
    IntentRef,
    IntentToward,
    intent_json,
)
from tl_core.ledger.hashing import event_hash

EVENT_ID = "01J00000000000000000000000"
RECORDED_AT = "2026-01-01T00:00:00.000000+00:00"
PAYLOAD = '{"a":1}'
VECTOR_1 = "69d2a9ba6e245b32d4fb2ab928026347dfd99bbb0ef866c11faf19256a84469d"
VECTOR_2 = "aadeb1f9ad0da9535605bbf2ed35c6fd7cc3b63fe85775fe6ccdca22936e1eb5"
VECTOR_3 = "d6ff6fedea762256f3aa94111781e1154f81aa74a7e50eef090fa980ea1f646f"  # pre-change code


def _hash(prev: str | None, intent: str | None = None, *, omit: bool = False) -> str:
    args = (prev, EVENT_ID, "s1", 1, "Record.Created", PAYLOAD, RECORDED_AT)
    return event_hash(*args) if omit else event_hash(*args, intent)


@pytest.mark.parametrize(
    ("prev", "expected"), [(None, VECTOR_1), (VECTOR_1, VECTOR_2)], ids=["v1", "v2"]
)
def test_no_intent_gives_the_old_digest(prev: str | None, expected: str) -> None:
    assert _hash(prev, omit=True) == expected
    assert _hash(prev, None) == expected


def test_third_pinned_vector_from_the_pre_change_code() -> None:
    got = event_hash(
        None,
        "E0000000000000000000000001",
        "s1",
        1,
        "Thing.Created",
        '{"n":1,"t":"café"}',
        "2026-01-01T00:00:01.000000+00:00",
    )
    assert got == VECTOR_3


def test_an_intent_changes_the_hash_and_is_stable() -> None:
    text = intent_json(Intent(why="because"))
    assert text == '{"why":"because"}'
    first = _hash(None, text)
    assert first != VECTOR_1
    assert first == _hash(None, text)
    assert first != _hash(None, intent_json(Intent(why="other")))


def test_the_intent_is_the_last_part() -> None:
    import hashlib

    parts = ["", EVENT_ID, "s1", "1", "Record.Created", PAYLOAD, RECORDED_AT, "X"]
    assert _hash(None, "X") == hashlib.sha256("\n".join(parts).encode()).hexdigest()


@pytest.mark.parametrize(
    "intent",
    [None, Intent(), Intent.model_validate({}), Intent(next=[]), Intent(why=None, goal_ref=None)],
)
def test_empty_intents_normalise_to_none_before_hashing(intent: Intent | None) -> None:
    assert intent_json(intent) is None
    assert _hash(None, intent_json(intent)) == VECTOR_1


def test_intent_json_is_canonical_and_drops_nulls_and_an_empty_next() -> None:
    intent = Intent(
        why="w",
        next=[IntentRef(command="C", target="t"), IntentRef(text="t")],
        toward=IntentToward(target="T", state="Done"),
        goal_ref="g",
    )
    assert intent_json(intent) == (
        '{"goal_ref":"g","next":[{"command":"C","target":"t"},{"text":"t"}],'
        '"toward":{"state":"Done","target":"T"},"why":"w"}'
    )


def test_unknown_keys_are_refused() -> None:
    with pytest.raises(ValueError):
        Intent.model_validate({"why": "x", "bogus": 1})
