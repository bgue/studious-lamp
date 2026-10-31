"""The contract harness every readiness check is tested with (contracts section 1; plan check F6).

``check_readiness_contract(check, world)`` proves what the frozen contract promises of a check: it
answers with a well-formed ``CheckResult`` that carries its own name and version, it writes
nothing, its lists and its detail stay inside the bounds, its detail is fixed text (no path, no
traceback), it watches existing record types, and it answers ``n_a`` with a reason when its
dependency is missing. It imports no test framework: a broken rule raises :class:`ContractViolation`
(an ``AssertionError``, so a test fails on it and a script can catch it), naming the rule.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

from pydantic import ValidationError
from sqlalchemy import Connection, event

from tl_core.readiness.types import (
    MAX_DETAIL_CHARS,
    MAX_NAME_CHARS,
    MAX_RESOLVE_VIA,
    CheckResult,
    IwpFacts,
    ReadinessCheck,
)

_SNAKE = re.compile(r"[a-z][a-z0-9_]*")
#: Statements that change data or schema. A statement is a write when it starts with one of these
#: words; a statement that starts with WITH is a write when a data-changing word appears in it.
_WRITE_WORDS = frozenset(
    {
        "insert",
        "update",
        "delete",
        "replace",
        "merge",
        "upsert",
        "create",
        "drop",
        "alter",
        "truncate",
        "reindex",
        "vacuum",
        "attach",
        "detach",
        "grant",
        "revoke",
        "copy",
    }
)
_CTE_WRITE = re.compile(r"\b(insert|update|delete|merge)\b")
_LEADING_NOISE = re.compile(r"\A(?:\s+|--[^\n]*\n?|/\*.*?\*/)*", re.S)
_LITERAL = re.compile(r"'(?:[^']|'')*'")
_FRACTION = re.compile(r"\d+/\d+")


class ContractViolation(AssertionError):  # noqa: N818  (the name is the contract's)
    """A readiness check broke a rule of the contract; the message names the rule."""


@dataclass(frozen=True)
class ContractWorld:
    #: Opens a connection on which any write must fail or be detected.
    open_readonly: Callable[[], Connection]
    #: An IWP the check can answer.
    iwp: IwpFacts
    today: date
    #: Existing record types, for ``watches``.
    record_types: frozenset[str]
    #: True: the check must answer ``n_a`` with a non-empty detail for this world.
    expect_n_a: bool = False


def _is_write(statement: str) -> bool:
    text = _LITERAL.sub("''", _LEADING_NOISE.sub("", statement)).lower()
    head = re.match(r"[a-z]+", text)
    if head is None:
        return False
    if head.group(0) == "with":
        return _CTE_WRITE.search(text) is not None
    return head.group(0) in _WRITE_WORDS


def _violation(check: ReadinessCheck, rule: str) -> ContractViolation:
    return ContractViolation(f"readiness check {check.name!r}: {rule}")


def _check_declaration(check: ReadinessCheck, world: ContractWorld) -> None:
    name: Any = check.name
    if not isinstance(name, str) or not name:
        raise ContractViolation("readiness check: name must be a non-empty string")
    if len(name) > MAX_NAME_CHARS or _SNAKE.fullmatch(name) is None:
        raise _violation(check, f"name must be snake case, at most {MAX_NAME_CHARS} characters")
    version: Any = check.version
    if not isinstance(version, str) or not version:
        raise _violation(check, "version must be a non-empty string")
    watches: Any = check.watches
    if not isinstance(watches, frozenset) or not watches:
        raise _violation(check, "watches must be a non-empty frozenset of record types")
    named = cast("frozenset[Any]", watches)
    unknown = sorted(str(w) for w in named if w not in world.record_types)
    if unknown:
        raise _violation(check, f"watches names record types that do not exist: {unknown}")


def _check_result(check: ReadinessCheck, world: ContractWorld, result: object) -> None:
    if not isinstance(result, CheckResult):
        raise _violation(check, "evaluate must return a CheckResult")
    try:
        CheckResult.model_validate(result.model_dump())
    except ValidationError as exc:
        raise _violation(check, "the result does not satisfy the CheckResult model") from exc
    if result.name != check.name:
        raise _violation(check, f"the result is named {result.name!r}, not the check's name")
    if result.version != check.version:
        raise _violation(check, f"the result has version {result.version!r}, not the check's")
    if len(result.resolve_via) > MAX_RESOLVE_VIA:
        raise _violation(check, f"resolve_via has more than {MAX_RESOLVE_VIA} records")
    if len(result.detail) > MAX_DETAIL_CHARS:
        raise _violation(check, f"detail is longer than {MAX_DETAIL_CHARS} characters")
    if "Traceback" in result.detail:
        raise _violation(check, "detail holds exception text (Traceback)")
    if "/" in _FRACTION.sub("", result.detail) or "\\" in result.detail:
        raise _violation(check, "detail holds a path separator; it is fixed text, keys and counts")
    if world.expect_n_a:
        if result.state != "n_a":
            raise _violation(check, f"expected state n_a for this world, got {result.state!r}")
        if not result.detail.strip():
            raise _violation(check, "an n_a answer needs a detail that names the decision")


def check_readiness_contract(check: ReadinessCheck, world: ContractWorld) -> None:
    """Raise :class:`ContractViolation` unless ``check`` keeps the contract in ``world``."""
    _check_declaration(check, world)
    writes: list[str] = []

    def watch(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        if _is_write(statement):
            writes.append(statement)

    conn = world.open_readonly()
    event.listen(conn, "before_cursor_execute", watch)
    try:
        try:
            result = check.evaluate(conn, world.iwp, world.today)
        except Exception as exc:
            if writes:
                raise _violation(check, "executed a write statement") from exc
            raise _violation(
                check, f"evaluate raised {type(exc).__name__}; it answers 'unknown' instead"
            ) from exc
        if writes:
            raise _violation(check, "executed a write statement")
    finally:
        event.remove(conn, "before_cursor_execute", watch)
        conn.close()
    _check_result(check, world, result)
