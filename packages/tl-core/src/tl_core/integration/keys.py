"""Key resolution for mapped commands (brief §18.5, §19.3; FANOUT D4).

A mapping names records by their human key: ``{"$key": "47-1234-W012"}`` or ``{"$key": {"type":
"core.Record", "key": "47-1234-W012"}}``. Before the command model is built, every such object in
a command's ``args`` is replaced by the record's id. The lookup is the caller's: it searches only
the endpoint's scope, so a mapping can never reach a record outside it.

A key that names no record, or more than one, is ``key_not_found``: the same code and words for
both, so the answer does not tell a payload sender which keys exist. Bounds: a walk of at most
``MAX_NODES`` values, ``INBOUND_MAX_JSON_DEPTH`` levels and ``MAX_KEY_REFS`` distinct keys; more is
refused, never cut. The arguments given are not changed; the resolved copy is returned.
"""

from __future__ import annotations

from typing import Any, Protocol, cast

from tl_core.integration.contract import (
    INBOUND_MAX_JSON_DEPTH,
    KEY_REF_MARKER,
    Problem,
    RecordRef,
)

MAX_NODES = 10_000
MAX_KEY_REFS = 100
MAX_KEY_CHARS = 255
SHOWN_KEY_CHARS = 60

BAD_REF = Problem(
    code="bad_key_ref",
    message='A $key is a text, or {"type": text, "key": text}, and nothing else.',
)
STANDS_ALONE = Problem(code="bad_key_ref", message="A $key stands alone in its object.")
TOO_LARGE = Problem(code="too_large", message="The arguments have too many values.")
TOO_DEEP = Problem(code="too_deep", message="The arguments are nested too deeply.")
TOO_MANY = Problem(code="too_many_keys", message=f"At most {MAX_KEY_REFS} keys per command.")


class KeyLookup(Protocol):
    """Records of the endpoint's scope by key. ``record_type`` is ``None`` for any type."""

    def find(self, key: str, record_type: str | None) -> list[RecordRef]: ...


class _Refused(Exception):
    def __init__(self, problem: Problem) -> None:
        super().__init__(problem.code)
        self.problem = problem


def shown(key: str) -> str:
    """``key`` as it appears in a message: printable, cut to ``SHOWN_KEY_CHARS``."""
    printable = "".join(char if char.isprintable() else "?" for char in key)
    if len(printable) > SHOWN_KEY_CHARS:
        return printable[:SHOWN_KEY_CHARS] + "..."
    return printable


def parse_ref(marker: Any) -> tuple[str, str | None]:
    """``(key, record_type)`` of a ``$key`` object's value; ``_Refused(BAD_REF)`` if malformed."""
    record_type: str | None = None
    key: Any
    if isinstance(marker, str):
        key = marker
    elif isinstance(marker, dict):
        pair = cast("dict[str, Any]", marker)
        if set(pair) != {"type", "key"}:
            raise _Refused(BAD_REF)
        record_type = pair["type"]
        key = pair["key"]
        if not isinstance(record_type, str) or not record_type:
            raise _Refused(BAD_REF)
    else:
        raise _Refused(BAD_REF)
    if not isinstance(key, str) or not key or len(key) > MAX_KEY_CHARS or not key.isprintable():
        raise _Refused(BAD_REF)
    return key, record_type


def resolve_keys(args: dict[str, Any], lookup: KeyLookup) -> tuple[dict[str, Any], list[Problem]]:
    """``args`` with every ``$key`` object replaced by a record id, and the problems found.

    On any problem the result is the unchanged ``args`` and the problems say why (the first one
    found: a walk stops at the first refusal).
    """
    seen: dict[tuple[str, str | None], str] = {}
    nodes = 0

    def find(key: str, record_type: str | None) -> str:
        pair = (key, record_type)
        if pair in seen:
            return seen[pair]
        if len(seen) >= MAX_KEY_REFS:
            raise _Refused(TOO_MANY)
        found = [
            ref
            for ref in lookup.find(key, record_type)
            if ref.id and (record_type is None or ref.record_type == record_type)
        ]
        if len(found) != 1:
            raise _Refused(
                Problem(
                    code="key_not_found",
                    # Nothing of the payload goes into a message (it lands in an event and the
                    # error queue): the length says which key without saying what it is.
                    message=f"No single record has the key (a text of {len(key)} characters).",
                )
            )
        seen[pair] = found[0].id
        return found[0].id

    def walk(value: Any, depth: int) -> Any:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES:
            raise _Refused(TOO_LARGE)
        if depth > INBOUND_MAX_JSON_DEPTH:
            raise _Refused(TOO_DEEP)
        if isinstance(value, dict):
            pairs = cast("dict[str, Any]", value)
            if KEY_REF_MARKER in pairs:
                if len(pairs) > 1:
                    raise _Refused(STANDS_ALONE)
                return find(*parse_ref(pairs[KEY_REF_MARKER]))
            return {name: walk(item, depth + 1) for name, item in pairs.items()}
        if isinstance(value, list):
            return [walk(item, depth + 1) for item in cast("list[Any]", value)]
        return value

    try:
        return walk(args, 0), []
    except _Refused as refused:
        return args, [refused.problem]
