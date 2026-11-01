"""Helpers every materials handler, projector and view shares: scope, versions, appends, Decimal.

**Decimal everywhere** (decision 2 of the S2 spec). A quantity is text in an event (``"12.500"``),
a ``Decimal`` in Python and a ``NUMERIC`` column (``REAL`` on SQLite). Nothing here does SQL
arithmetic: a row is read with :func:`dec`, the sum is made in ``Decimal``, quantized to 3 places
and bound back with :func:`num`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import AppendResult, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

from tl_mod_materials.errors import (
    InvalidQuantityError,
    InvalidValueError,
    MaterialsScopeError,
)
from tl_mod_materials.limits import MAX_QTY, QTY_STEP, QTY_TEXT
from tl_mod_materials.names import COMPANY


@dataclass(frozen=True)
class CommandSpec:
    """One command of the module: its model, its handler and its access word.

    ``access`` is a row of ``schema/settings/access-words.yaml`` (``materials.library.edit``): the
    API builds one ``POST /commands/<Name>`` route per row and reads the word as its table word.
    """

    model: type[Command]
    handler: Callable[[UnitOfWork, Any], CommandResult]
    access: str


_VERSION_SQL = text("SELECT version FROM cur_core_record WHERE id = :id")
_FIND_SQL = text(
    "SELECT id FROM cur_core_record "
    "WHERE scope = :scope AND type = :type AND key = :key AND voided = :voided"
)
ZERO = Decimal(0)


def require_project(cmd: Command) -> None:
    if not cmd.scope.startswith("project:"):
        raise MaterialsScopeError(f"this command belongs to a project; the scope is {cmd.scope!r}")


def require_company(cmd: Command) -> None:
    if cmd.scope != COMPANY:
        raise MaterialsScopeError(f"the item library is the company's; the scope is {cmd.scope!r}")


def correlated[C: Command](cmd: C) -> C:
    """``cmd`` with a correlation id, so every event of the command carries the same one."""
    if cmd.correlation_id is not None:
        return cmd
    return cmd.model_copy(update={"correlation_id": new_ulid()})


def version_of(uow: UnitOfWork, record_id: str) -> int:
    found = uow.conn().execute(_VERSION_SQL, {"id": record_id}).scalar_one_or_none()
    if found is None:
        raise LookupError(f"no record {record_id!r}")
    return int(found)


def append(
    uow: UnitOfWork,
    cmd: Command,
    stream_id: str,
    stream_type: str,
    events: list[NewEvent],
    *,
    source: str | None = None,
) -> AppendResult:
    """Append ``events`` to a stream at its current version."""
    return uow.append(
        stream_id=stream_id,
        stream_type=stream_type,
        scope=cmd.scope,
        expected_version=version_of(uow, stream_id),
        events=events,
        actor=cmd.actor,
        source=source or cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )


def find_record(conn: Connection, scope: str, record_type: str, key: str) -> str | None:
    """The id of the live (not voided) record of ``record_type`` with ``key`` in ``scope``."""
    found = conn.execute(
        _FIND_SQL, {"scope": scope, "type": record_type, "key": key, "voided": False}
    ).scalar_one_or_none()
    return None if found is None else str(found)


# --- Decimal -------------------------------------------------------------------------------------


def dec(value: Any) -> Decimal:
    """A stored quantity as a ``Decimal`` of 3 places. SQLite hands back a float, Postgres a
    ``Decimal``; ``str`` first, so ``0.3`` is ``0.300`` and never ``0.29999...``."""
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(QTY_STEP, rounding=ROUND_HALF_EVEN)


def num(value: Decimal) -> float:
    """A quantity as the number a column is bound with (the way cost binds its amounts)."""
    return float(value.quantize(QTY_STEP, rounding=ROUND_HALF_EVEN))


def qty_text(value: Decimal) -> str:
    """The event form of a quantity: ``"12.500"``."""
    return format(value.quantize(QTY_STEP, rounding=ROUND_HALF_EVEN), "f")


def parse_qty(value: str, field: str = "qty") -> Decimal:
    """A quantity from its text: ASCII digits, at most 3 decimals, above zero, at most 1e9."""
    if not isinstance(value, str) or QTY_TEXT.fullmatch(value) is None:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise InvalidQuantityError(
            f"{field} must be ASCII digits with at most 3 decimals, as 12.500"
        )
    number = Decimal(value)
    if number <= ZERO:
        raise InvalidQuantityError(f"{field} must be above zero")
    if number > MAX_QTY:
        raise InvalidQuantityError(f"{field} must be at most {MAX_QTY}")
    return number


def check_one_of(value: str, allowed: tuple[str, ...], field: str) -> str:
    if value not in allowed:
        raise InvalidValueError(f"{field} must be one of: {', '.join(allowed)}")
    return value
