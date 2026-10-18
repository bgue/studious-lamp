"""Key resolution replaces `{"$key": ...}` by record ids inside the lookup (P1-I7-T04a)."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from tl_core.integration.contract import INBOUND_MAX_JSON_DEPTH, RecordRef
from tl_core.integration.keys import (
    MAX_KEY_REFS,
    MAX_NODES,
    SHOWN_KEY_CHARS,
    resolve_keys,
    shown,
)


class Lookup:
    """Records by key; counts the calls."""

    def __init__(self, *refs: RecordRef) -> None:
        self.refs = list(refs)
        self.calls: list[tuple[str, str | None]] = []

    def find(self, key: str, record_type: str | None) -> list[RecordRef]:
        self.calls.append((key, record_type))
        return [r for r in self.refs if r.key == key and record_type in (None, r.record_type)]


def ref(id: str, key: str, record_type: str = "core.Record") -> RecordRef:
    return RecordRef(id=id, key=key, record_type=record_type, version=1)


WELDS = Lookup(ref("id-12", "47-1234-W012"), ref("id-13", "47-1234-W013"))


def resolved(args: dict[str, Any], lookup: Lookup = WELDS) -> dict[str, Any]:
    out, problems = resolve_keys(args, lookup)
    assert problems == [], problems
    return out


def refused(args: dict[str, Any], lookup: Lookup = WELDS) -> str:
    out, problems = resolve_keys(args, lookup)
    assert len(problems) == 1, problems
    assert out == args, "on a problem the arguments come back unchanged"
    return problems[0].code


def test_a_key_becomes_the_records_id() -> None:
    assert resolved({"stream_id": {"$key": "47-1234-W012"}, "pset": "nde"}) == {
        "stream_id": "id-12",
        "pset": "nde",
    }


def test_the_long_form_names_the_type() -> None:
    args = {"stream_id": {"$key": {"type": "core.Record", "key": "47-1234-W013"}}}
    assert resolved(args) == {"stream_id": "id-13"}


def test_keys_are_found_at_any_depth_and_in_lists() -> None:
    args = {
        "a": [{"b": {"$key": "47-1234-W012"}}, 7, "text", None],
        "c": {"d": {"$key": "47-1234-W013"}},
    }
    assert resolved(args) == {"a": [{"b": "id-12"}, 7, "text", None], "c": {"d": "id-13"}}


def test_the_arguments_given_are_not_changed() -> None:
    args = {"stream_id": {"$key": "47-1234-W012"}, "list": [{"$key": "47-1234-W013"}]}
    before = copy.deepcopy(args)
    resolved(args)
    assert args == before


def test_arguments_without_keys_come_back_equal() -> None:
    args = {"body": "hello", "n": 3, "flag": True, "nothing": None, "items": [1, 2]}
    assert resolved(args) == args


def test_no_record_and_two_records_are_the_same_answer() -> None:
    twins = Lookup(ref("a", "K-1"), ref("b", "K-1"))
    missing = resolve_keys({"x": {"$key": "K-9"}}, twins)[1][0]
    ambiguous = resolve_keys({"x": {"$key": "K-1"}}, twins)[1][0]
    assert missing.code == ambiguous.code == "key_not_found"
    assert missing.message.replace("K-9", "K-1") == ambiguous.message


def test_a_record_of_another_type_is_not_the_one_asked_for() -> None:
    lookup = Lookup(ref("t1", "K-5", "engineering.Tag"))
    assert (
        refused({"x": {"$key": {"type": "core.Record", "key": "K-5"}}}, lookup) == "key_not_found"
    )
    assert resolved({"x": {"$key": {"type": "engineering.Tag", "key": "K-5"}}}, lookup) == {
        "x": "t1"
    }


def test_a_lookup_that_ignores_the_type_cannot_widen_the_search() -> None:
    class Careless:
        def find(self, key: str, record_type: str | None) -> list[RecordRef]:
            return [ref("t1", key, "engineering.Tag")]

    args = {"x": {"$key": {"type": "core.Record", "key": "K-5"}}}
    assert refused(args, Careless()) == "key_not_found"  # type: ignore[arg-type]


def test_a_lookup_result_without_an_id_is_not_a_record() -> None:
    class Empty:
        def find(self, key: str, record_type: str | None) -> list[RecordRef]:
            return [RecordRef(id="", key=key, record_type="core.Record")]

    assert refused({"x": {"$key": "K-1"}}, Empty()) == "key_not_found"  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "marker",
    [
        5,
        None,
        True,
        [],
        "",
        "x" * 256,
        "bad\x00key",
        "bad\nkey",
        {"key": "K"},
        {"type": "core.Record"},
        {"type": "", "key": "K"},
        {"type": 3, "key": "K"},
        {"type": "core.Record", "key": 3},
        {"type": "core.Record", "key": "K", "extra": 1},
    ],
)
def test_a_malformed_key_object_is_refused(marker: Any) -> None:
    assert refused({"x": {"$key": marker}}) == "bad_key_ref"


def test_a_key_object_stands_alone() -> None:
    assert refused({"x": {"$key": "47-1234-W012", "other": 1}}) == "bad_key_ref"


def test_the_message_shows_a_short_key() -> None:
    problem = resolve_keys({"x": {"$key": "K" * 200}}, WELDS)[1][0]
    assert problem.code == "key_not_found"
    assert "K" * (SHOWN_KEY_CHARS + 1) not in problem.message and len(problem.message) < 200


def test_a_key_is_looked_up_once() -> None:
    lookup = Lookup(ref("id-12", "47-1234-W012"))
    args = {
        "a": {"$key": "47-1234-W012"},
        "b": [{"$key": "47-1234-W012"}, {"$key": "47-1234-W012"}],
    }
    assert resolved(args, lookup) == {"a": "id-12", "b": ["id-12", "id-12"]}
    assert lookup.calls == [("47-1234-W012", None)]


def test_the_same_key_with_another_type_is_another_lookup() -> None:
    lookup = Lookup(ref("id-12", "47-1234-W012"))
    args = {
        "a": {"$key": "47-1234-W012"},
        "b": {"$key": {"type": "core.Record", "key": "47-1234-W012"}},
    }
    resolved(args, lookup)
    assert len(lookup.calls) == 2


def test_nesting_is_bounded() -> None:
    def nested(wrappers: int) -> Any:
        value: Any = {"$key": "47-1234-W012"}
        for _ in range(wrappers):
            value = {"n": value}
        return value

    assert resolve_keys(nested(INBOUND_MAX_JSON_DEPTH), WELDS)[1] == []
    assert refused(nested(INBOUND_MAX_JSON_DEPTH + 1)) == "too_deep"


def test_the_number_of_values_is_bounded() -> None:
    # the root dict and the list are two values; each item is one
    assert resolve_keys({"items": list(range(MAX_NODES - 2))}, WELDS)[1] == []
    assert refused({"items": list(range(MAX_NODES - 1))}) == "too_large"


def test_a_key_is_shown_printable_and_short() -> None:
    assert shown("A\u202eB\x00C") == "A?B?C"
    assert shown("K" * SHOWN_KEY_CHARS) == "K" * SHOWN_KEY_CHARS
    assert shown("K" * (SHOWN_KEY_CHARS + 1)) == "K" * SHOWN_KEY_CHARS + "..."


def test_the_number_of_distinct_keys_is_bounded_and_the_lookup_stops() -> None:
    refs = [ref(f"id-{n}", f"K-{n}") for n in range(MAX_KEY_REFS + 1)]
    lookup = Lookup(*refs)
    args = {"items": [{"$key": f"K-{n}"} for n in range(MAX_KEY_REFS + 1)]}
    assert refused(args, lookup) == "too_many_keys"
    assert len(lookup.calls) == MAX_KEY_REFS
    ok = {"items": [{"$key": f"K-{n}"} for n in range(MAX_KEY_REFS)]}
    assert len(resolved(ok, Lookup(*refs))["items"]) == MAX_KEY_REFS


def test_a_marker_name_as_a_plain_value_is_just_text() -> None:
    assert resolved({"note": "$key", "x": ["$key"]}) == {"note": "$key", "x": ["$key"]}
