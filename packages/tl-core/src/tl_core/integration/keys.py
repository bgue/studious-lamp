# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedClass=false
"""Key resolution for mapped commands (brief §18.5, §19.3; FANOUT D4).

STUB (P1-I7-T04a): the constants, ``KeyLookup`` and ``_Refused`` are final; the functions raise
NotImplementedError. Remove this paragraph, every STEPS comment, the two lint-silencing lines above
and `NotImplementedError` when you implement them.

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
    # STEPS
    # 1. Replace every character that is not `isprintable()` by "?".
    # 2. If the result is longer than SHOWN_KEY_CHARS, cut it there and add "...".
    raise NotImplementedError


def parse_ref(marker: Any) -> tuple[str, str | None]:
    """``(key, record_type)`` of a ``$key`` object's value; ``_Refused(BAD_REF)`` if malformed."""
    # STEPS
    # 1. A str: that is the key, with record_type None.
    # 2. A dict whose key set is exactly {"type", "key"}: record_type = marker["type"] (must be a
    #    non-empty str) and key = marker["key"].
    # 3. Anything else (int, None, bool, list, other dicts): raise _Refused(BAD_REF).
    # 4. The key must be a non-empty str of at most MAX_KEY_CHARS characters, with only printable
    #    characters (`str.isprintable`), else raise _Refused(BAD_REF).
    # 5. pyright (strict) sees a dict taken from `Any` as unknown: read it through
    #    `pair = cast("dict[str, Any]", marker)` and put
    #    `# pyright: ignore[reportUnknownArgumentType]` on the `set(marker)` test.
    raise NotImplementedError


def resolve_keys(args: dict[str, Any], lookup: KeyLookup) -> tuple[dict[str, Any], list[Problem]]:
    """``args`` with every ``$key`` object replaced by a record id, and the problems found.

    On any problem the result is the unchanged ``args`` and the problems say why (the first one
    found: a walk stops at the first refusal).
    """
    # STEPS
    # 1. Keep `seen: dict[(key, record_type), id]` and a counter `nodes`.
    # 2. A recursive `walk(value, depth)` (nested function) that first adds 1 to `nodes`: more than
    #    MAX_NODES raises _Refused(TOO_LARGE); `depth` over INBOUND_MAX_JSON_DEPTH raises
    #    _Refused(TOO_DEEP). The root is depth 0 and each dict value or list item is depth + 1.
    # 3. A dict that holds KEY_REF_MARKER: if it holds anything else too, raise
    #    _Refused(STANDS_ALONE); otherwise the result is `find(*parse_ref(value[KEY_REF_MARKER]))`.
    #    Any other dict: a new dict with the same names and walked values. A list: a new list of
    #    walked items. Any other value is returned as it is (the text "$key" is just text).
    # 4. `find(key, record_type)`: a pair already in `seen` is answered from it with no lookup.
    #    With MAX_KEY_REFS pairs in `seen` already, raise _Refused(TOO_MANY) before looking up.
    #    Call `lookup.find(key, record_type)` and keep only results with a non-empty `id` whose
    #    `record_type` equals the asked type (when one was asked). Not exactly one left: raise
    #    _Refused(Problem(code="key_not_found", message=f"No single record has the key
    #    {shown(key)}.")): the same words for none and for several. Else remember and return the
    #    id.
    # 5. pyright (strict): `len(value)`, `value.items()` and the iteration over a list taken from
    #    `Any` need `# pyright: ignore[reportUnknownArgumentType]` or
    #    `# pyright: ignore[reportUnknownVariableType]` on that line (the error message names it).
    # 6. `try: return walk(args, 0), []` and `except _Refused as refused: return args,
    #    [refused.problem]`. The arguments given are never changed.
    raise NotImplementedError
