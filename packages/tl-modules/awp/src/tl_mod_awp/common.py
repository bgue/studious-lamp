"""Helpers every awp handler shares: scope check, versions, appends, record lookups, allocations.

Every id a command is given goes through ``load_record`` (``require_visible`` first, ADR-0016
section 5): a record the viewer may not read, one in another project, one of another type and one
that does not exist all answer ``RecordNotFoundError`` with the same words. A code is resolved the
same way (``resolve_code``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, inspect, text
from tl_core import confidentiality
from tl_core.ledger import AppendResult, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import DuplicateKeyError, RecordNotFoundError
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid
from tl_mod_engineering import codelists
from tl_mod_engineering.errors import UnknownCodeError, UnknownCodeListError

from tl_mod_awp.errors import (
    AllocationError,
    AwpScopeError,
    CodeNotFoundError,
    DuplicateCodeError,
    UnknownListCodeError,
)
from tl_mod_awp.limits import MAX_ALLOCATIONS
from tl_mod_awp.names import (
    CWA_TABLE,
    CWP_ALLOCATION_TABLE,
    CWP_TABLE,
    FEED_NONE,
    KEY_PREFIX,
    ST_PLANNED,
    ST_VOID,
)

HUNDRED = Decimal("100.00")
MIN_PERCENT = Decimal("0.01")
_CENTS = Decimal("0.01")
_PERCENT = re.compile(r"[0-9]{1,3}(?:\.[0-9]{1,2})?", re.ASCII)  # ASCII digits only
_VERSION_SQL = text("SELECT version FROM cur_core_record WHERE id = :id")
_RECORD_SQL = text("SELECT id, key, title, scope, type, voided FROM cur_core_record WHERE id = :id")
_BY_KEY_SQL = text(
    "SELECT id FROM cur_core_record WHERE scope = :scope AND type = :type AND key = :key "
    "AND voided = :voided"
)
_CWP_ON_NODE_SQL = text(
    f"SELECT 1 FROM {CWP_ALLOCATION_TABLE} a JOIN cur_core_record r ON r.id = a.cwp_id "
    "WHERE a.wbs_node_id = :node AND r.voided = :voided LIMIT 1"
)
_CWP_ON_CWA_SQL = text(
    f"SELECT 1 FROM {CWP_TABLE} c JOIN cur_core_record r ON r.id = c.id "
    "WHERE c.cwa_id = :cwa AND r.voided = :voided LIMIT 1"
)
_KEY_TAKEN_SQL = text(
    "SELECT 1 FROM cur_core_record WHERE scope = :scope AND type = :type AND key = :key"
)
_STATE_SQL = text("SELECT status, voided FROM cur_core_record WHERE id = :id")
_CWA_BY_ID_SQL = text(f"SELECT id, code, location_text, retired FROM {CWA_TABLE} WHERE id = :id")

#: Fixed messages shared by the allocation checks (here and in S4's CWP allocation).
MSG_ROWS = "an allocation holds 1 to 20 lines"
MSG_REPEAT = "a target is allocated twice in one list"
MSG_PERCENT = "each percent is a number from 0.01 to 100.00 with at most two decimals"
MSG_DUPLICATE = "the code is already used by a record of that kind in the project"


@dataclass(frozen=True)
class RecordRef:
    id: str
    key: str | None
    title: str


def require_project(cmd: Command) -> None:
    if not cmd.scope.startswith("project:"):
        raise AwpScopeError(f"work packaging belongs to a project; the scope is {cmd.scope!r}")


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
    uow: UnitOfWork, cmd: Command, stream_id: str, stream_type: str, events: list[NewEvent]
) -> AppendResult:
    """Append ``events`` to a stream at its current version."""
    return uow.append(
        stream_id=stream_id,
        stream_type=stream_type,
        scope=cmd.scope,
        expected_version=version_of(uow, stream_id),
        events=events,
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )


def silent(payload: dict[str, Any]) -> dict[str, Any]:
    """``payload`` with the feed policy the eight no-card events carry."""
    return {**payload, "feed_policy": FEED_NONE}


def load_record(uow: UnitOfWork, scope: str, record_id: str, record_type: str) -> RecordRef:
    """The record ``record_id`` of ``record_type`` in ``scope``.

    ``RecordNotFoundError`` (the same words) when it is hidden from the viewer, does not exist,
    is in another project or is of another type.
    """
    conn = uow.conn()
    confidentiality.require_visible(conn, record_id)
    row = conn.execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None or row.scope != scope or row.type != record_type or bool(row.voided):
        raise RecordNotFoundError(f"no record {record_id!r}")
    return RecordRef(id=str(row.id), key=None if row.key is None else str(row.key), title=row.title)


def record_key(record_type: str, code: str) -> str:
    """The record key of an awp record with the typed ``code``: ``awp.wbs@1.2``, ``awp.cwa@A1``,
    ``awp.ewp@EWP-7``. The code of a record of another module (a cost code) is its own key.

    Every awp key holds the ``@`` a typed key may not, so no other module's typed record can equal
    one: a node ``1`` and a cost code ``1`` coexist, and a record the viewer may not read never
    makes a code look taken. The displayed code stays the typed ``code`` column and the title."""
    return f"{KEY_PREFIX.get(record_type, '')}{code}"


def key_taken(conn: Connection, scope: str, record_type: str, code: str) -> bool:
    """A record of ``record_type`` (void ones too, as core counts them) already has ``code``.

    The key asked for is the prefixed one and the type is part of the question, so only awp
    records of that kind answer it."""
    found = conn.execute(
        _KEY_TAKEN_SQL,
        {"scope": scope, "type": record_type, "key": record_key(record_type, code)},
    )
    return found.first() is not None


def create_coded_record(
    uow: UnitOfWork,
    cmd: Command,
    *,
    record_type: str,
    title: str,
    code: str,
    extra_events: Sequence[NewEvent],
) -> CommandResult:
    """``create_module_record`` for a record keyed by a typed ``code`` (the prefixed key).

    Refuses a code the kind already has with the one fixed message, whether the same-kind check
    or core's own duplicate-key error caught it."""
    if key_taken(uow.conn(), cmd.scope, record_type, code):
        raise DuplicateCodeError(MSG_DUPLICATE)
    try:
        return create_module_record(
            uow,
            cmd,
            record_type=record_type,
            title=title,
            key=record_key(record_type, code),
            composed_key=True,
            extra_events=extra_events,
        )
    except DuplicateKeyError:
        raise DuplicateCodeError(MSG_DUPLICATE) from None


def resolve_code(conn: Connection, scope: str, record_type: str, code: str) -> str | None:
    """The id of the live record of ``record_type`` whose code is ``code``; ``None`` when there is
    none or the viewer may not read it (the two answer alike)."""
    found = conn.execute(
        _BY_KEY_SQL,
        {
            "scope": scope,
            "type": record_type,
            "key": record_key(record_type, code),
            "voided": False,
        },
    ).scalar_one_or_none()
    if found is None or confidentiality.is_hidden(conn, str(found)):
        return None
    return str(found)


def require_code(conn: Connection, scope: str, record_type: str, code: str, what: str) -> str:
    found = resolve_code(conn, scope, record_type, code)
    if found is None:
        raise CodeNotFoundError(f"no {what} with that code in the project")
    return found


def has_table(conn: Connection, name: str) -> bool:
    return inspect(conn).has_table(name)


def cwp_allocates_to(conn: Connection, node_id: str) -> bool:
    """A package that is not void allocates to the node. The package tables belong to S4's
    projector: before it is registered the table is absent and no package exists."""
    if not has_table(conn, CWP_ALLOCATION_TABLE):
        return False
    return conn.execute(_CWP_ON_NODE_SQL, {"node": node_id, "voided": False}).first() is not None


def cwp_names_cwa(conn: Connection, cwa_id: str) -> bool:
    """A package that is not void names the area (same note as ``cwp_allocates_to``)."""
    if not has_table(conn, CWP_TABLE):
        return False
    return conn.execute(_CWP_ON_CWA_SQL, {"cwa": cwa_id, "voided": False}).first() is not None


@dataclass(frozen=True)
class CwaRow:
    id: str
    code: str
    location_text: str | None
    retired: bool


def get_cwa(conn: Connection, cwa_id: str) -> CwaRow | None:
    found = conn.execute(_CWA_BY_ID_SQL, {"id": cwa_id}).first()
    if found is None:
        return None
    return CwaRow(
        id=str(found.id),
        code=str(found.code),
        location_text=None if found.location_text is None else str(found.location_text),
        retired=bool(found.retired),
    )


def parse_percent(value: str) -> Decimal:
    """``value`` (ASCII digits, at most two decimals) as a ``Decimal`` from 0.01 to 100.00."""
    if _PERCENT.fullmatch(value) is None:
        raise AllocationError(MSG_PERCENT)
    percent = Decimal(value).quantize(_CENTS)
    if percent < MIN_PERCENT or percent > HUNDRED:
        raise AllocationError(MSG_PERCENT)
    return percent


def percent_text(value: Decimal) -> str:
    """Two decimals, as the events and tables carry a percent (``"40.00"``)."""
    return f"{value:.2f}"


def check_allocations(
    lines: Sequence[tuple[str, str]], *, allow_empty: bool = False
) -> list[tuple[str, Decimal]]:
    """``(target, percent)`` lines checked: 1 to 20 of them, no target twice, each percent from
    0.01 to 100.00, the sum exactly 100.00. The messages are fixed (no cell text).

    ``allow_empty``: no line at all is a valid list (it clears an allocation) and has no sum to
    check; with lines the sum rule holds."""
    if not lines and allow_empty:
        return []
    if not 1 <= len(lines) <= MAX_ALLOCATIONS:
        raise AllocationError(MSG_ROWS)
    seen: set[str] = set()
    checked: list[tuple[str, Decimal]] = []
    for target, percent in lines:
        if target in seen:
            raise AllocationError(MSG_REPEAT)
        seen.add(target)
        checked.append((target, parse_percent(percent)))
    total = sum((p for _, p in checked), Decimal("0.00"))
    if total != HUNDRED:
        raise AllocationError(f"the percentages sum to {total}, not 100.00")
    return checked


def package_state(conn: Connection, record_id: str) -> str:
    """The workflow state of a package (``Void`` once voided, ``Planned`` before its first move)."""
    row = conn.execute(_STATE_SQL, {"id": record_id}).first()
    if row is None:
        return ST_PLANNED
    return ST_VOID if bool(row.voided) else str(row.status or ST_PLANNED)


def require_list_code(conn: Connection, scope: str, list_name: str, code: str, what: str) -> None:
    """``code`` is a usable value of the code list ``list_name`` for ``scope`` (company values and
    the project's own). Fixed message; the code is not repeated. A list that is not registered
    answers the same way, so a project without the standards edition refuses rather than guesses."""
    try:
        found = codelists.resolve(conn, scope, list_name, code, on=date.today())
    except (UnknownCodeListError, UnknownCodeError):
        raise UnknownListCodeError(f"{what} is not a value of the code list {list_name}") from None
    if not found.usable:
        raise UnknownListCodeError(f"{what} is not in use in the code list {list_name}")
