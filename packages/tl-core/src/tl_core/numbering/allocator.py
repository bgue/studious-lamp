"""The numbering allocator: next key for a pattern, written as a ledger event (brief 8; Q7).

Allocation is transactional. ``allocate_key`` appends ``Numbering.Allocated`` to the counter's
stream inside the caller's unit of work, which is the same unit of work that appends the record's
``Record.Created``. If anything later in the transaction fails, the allocation rolls back with it
and the number is handed out again. That is what "gap-free" means here: a number is never spent
without a record.

Three layers stop two writers from getting the same number:

1. A write transaction is exclusive (SQLite ``BEGIN IMMEDIATE``), so the counter row read below
   cannot change before the append.
2. The append states the counter stream's expected version, so a writer that read a stale counter
   (another database, or a future adapter without an exclusive lock) gets ``ConcurrencyError``
   instead of a duplicate. The caller may retry in a new transaction.
3. ``(scope, key)`` is unique in ``cur_core_record``.

A counter is one ledger stream per scope, pattern and *prefix* (the key without its sequence
digits), so ``{project}-{type}-{discipline}-{seq:4}`` numbers each discipline separately.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import NoReturn

from sqlalchemy import text

from tl_core.ledger import Event, NewEvent
from tl_core.numbering.config import NumberingPattern
from tl_core.numbering.pattern import PatternError
from tl_core.services.errors import GapFreeError, NotAvailableError, NumberingValueError
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

COUNTER_STREAM_TYPE = "numbering.Counter"
_COUNTER_SQL = text("SELECT last_sequence, version FROM cur_numbering WHERE counter_id = :counter")


@dataclass(frozen=True)
class Allocation:
    key: str
    sequence: int
    counter_id: str
    prefix: str
    event: Event


def segment_values(
    pattern: NumberingPattern, scope: str, extra: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The value of every field segment of ``pattern`` for a record in ``scope``.

    ``{project}`` comes from the scope (a project scope only), ``{type}`` from the pattern's
    ``type_code``; every other field must be in ``extra``. Raises ``NumberingValueError`` when a
    value is missing or is not letters and digits.
    """
    fields = pattern.compiled().fields
    values: dict[str, str] = dict(extra or {})
    if "project" in fields:
        if not scope.startswith("project:"):
            raise NumberingValueError(
                f"pattern {pattern.id!r} needs a project, but the scope is {scope!r}"
            )
        values["project"] = scope.removeprefix("project:")
    if "type" in fields:
        values["type"] = pattern.type_code
    missing = [name for name in fields if name not in values]
    if missing:
        raise NumberingValueError(f"pattern {pattern.id!r} needs a value for: {', '.join(missing)}")
    try:
        pattern.compiled().prefix(values)
    except PatternError as exc:
        raise NumberingValueError(str(exc)) from exc
    return {name: values[name] for name in fields}


def counter_id(pattern: NumberingPattern, scope: str, prefix: str) -> str:
    """The ledger stream id of a counter."""
    return f"numbering:{scope}:{pattern.id}:{prefix}"


def allocate_key(
    uow: UnitOfWork,
    *,
    pattern: NumberingPattern,
    scope: str,
    values: Mapping[str, str],
    record_id: str | None,
    record_type: str,
    actor: str,
    source: str,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    is_taken: Callable[[str], bool] | None = None,
) -> Allocation:
    """Reserve the next key of ``pattern`` for ``values`` inside the open unit of work.

    ``values`` come from ``segment_values``. Sequence numbers in the pattern's reserved ranges are
    skipped, and so is any number whose key ``is_taken`` reports as used (a key typed by hand),
    without being recorded: such a number belongs to an existing record, so nothing is wasted.
    Raises ``ConcurrencyError`` if the counter changed under this transaction.
    """
    compiled = pattern.compiled()
    prefix = compiled.prefix(values)
    counter = counter_id(pattern, scope, prefix)
    row = uow.conn().execute(_COUNTER_SQL, {"counter": counter}).first()
    last, version = (int(row.last_sequence), int(row.version)) if row is not None else (0, 0)

    sequence = pattern.skip_reserved(last + 1)
    key = compiled.render(values, sequence)
    while is_taken is not None and is_taken(key):
        sequence = pattern.skip_reserved(sequence + 1)
        key = compiled.render(values, sequence)

    result = uow.append(
        stream_id=counter,
        stream_type=COUNTER_STREAM_TYPE,
        scope=scope,
        expected_version=version,
        events=[
            NewEvent(
                event_type="Numbering.Allocated",
                payload={
                    "pattern": pattern.id,
                    "key": key,
                    "sequence": sequence,
                    "prefix": prefix,
                    "record_id": record_id,
                    "record_type": record_type,
                },
            )
        ],
        actor=actor,
        source=source,
        correlation_id=correlation_id or new_ulid(),
        causation_id=causation_id,
    )
    return Allocation(
        key=key, sequence=sequence, counter_id=counter, prefix=prefix, event=result.events[0]
    )


def allocate_standalone(
    uow: UnitOfWork,
    *,
    pattern: NumberingPattern,
    scope: str,
    values: Mapping[str, str],
    actor: str,
    source: str,
    correlation_id: str | None = None,
) -> Allocation:
    """Allocate a number that no record is created for (bulk or offline preparation).

    Only a pattern with ``gap_free: false`` allows it; a gap-free pattern raises ``GapFreeError``.
    """
    if pattern.gap_free:
        raise GapFreeError(
            f"pattern {pattern.id!r} is gap-free: numbers are allocated only when a record "
            "is created"
        )
    return allocate_key(
        uow,
        pattern=pattern,
        scope=scope,
        values=values,
        record_id=None,
        record_type=pattern.record_type,
        actor=actor,
        source=source,
        correlation_id=correlation_id,
    )


def reserve_range(*_args: object, **_kwargs: object) -> NoReturn:
    """Reserved ranges for offline use (brief 8) are a stub until offline sync (Phase 3)."""
    raise NotAvailableError("reserved number ranges arrive with offline sync (Phase 3)")
