"""Stock movements: the eight kinds behind seven commands (m4-materials.md sections 2, 3; ADR-0022).

A movement is a ``StockLot.Moved`` event on the lot's stream, never a record. The seven commands
(``IssueStock``, ``TransferStock``, ``ReturnStock``, ``ReserveStock``, ``UnreserveStock``,
``AdjustStock``, ``ScrapStock``) each carry 1 to 200 movements of one kind; ``receive`` happens only
inside an accepted receipt. :func:`post_batch` is the one path both the commands and the public
surface (``tl_mod_materials.api.post_movements``) take.

**All or nothing.** The batch is checked and appended one movement at a time inside the caller's
unit of work: the append runs the projectors, so the next movement of the same batch reads the
balances the earlier one left (two issues of 3 from a lot of 5 cannot both pass). A refusal raises
and the unit of work rolls back, so no event of the batch survives. The ledger writer lock
(SQLite ``BEGIN IMMEDIATE``, a Postgres advisory lock) is taken by the first statement of the
write transaction, so the balances read here cannot change before the append: two concurrent
issues of the last 5.000 are serialised and the second sees the first.

**No balance goes negative**, adjust included. Quantities are ``Decimal`` (3 places) throughout;
nothing here does SQL arithmetic. Messages name a movement by its index and never repeat text the
caller sent.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.text import clean_optional_text
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

from tl_mod_materials.common import (
    ZERO,
    correlated,
    dec,
    parse_qty,
    qty_text,
    require_project,
    version_of,
)
from tl_mod_materials.errors import (
    CostCodeNotFoundError,
    InsufficientStockError,
    LocationNotFoundError,
    LotNotFoundError,
    MovementRuleError,
    MtoLineNotFoundError,
)
from tl_mod_materials.limits import MAX_LOCATION_CODE, MAX_MOVEMENTS, MAX_REASON
from tl_mod_materials.names import (
    ADJUST,
    ISSUE,
    LOCATION_TABLE,
    LOT_MOVED,
    LOT_TABLE,
    MTO_LINE_TABLE,
    PROJECT_ITEM_TABLE,
    RESERVATION_TABLE,
    RESERVE,
    RETURN,
    SCRAP,
    STOCK_LOT,
    STOCK_TABLE,
    TRANSFER,
    UNRESERVE,
)

MovementKind = Literal["issue", "transfer", "return", "adjust", "scrap", "reserve", "unreserve"]
#: ``awp.IWP``: a line whose work package is an installation work package copies it to the event.
IWP_TYPE: Final = "awp.IWP"
COST_CODE_TYPE: Final = "cost.CostCode"
MAX_PERSON: Final = 120
MAX_ID: Final = 64
MAX_LOT_KEY: Final = 80


class Movement(BaseModel):
    """One movement of a batch. Fields as the ``cur_materials_movement`` columns; the kind is the
    command's. ``from_location`` and ``to_location`` are location codes of the project."""

    model_config = ConfigDict(extra="forbid")

    lot_key: str = Field(min_length=1, max_length=MAX_LOT_KEY)
    qty: str = Field(min_length=1, max_length=32)
    uom: str = Field(min_length=1, max_length=8)
    from_location: str | None = Field(default=None, min_length=1, max_length=MAX_LOCATION_CODE)
    to_location: str | None = Field(default=None, min_length=1, max_length=MAX_LOCATION_CODE)
    cost_code_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)
    mto_line_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)
    reason: str | None = Field(default=None, max_length=MAX_REASON)
    person: str | None = Field(default=None, max_length=MAX_PERSON)
    direction: Literal["in", "out"] | None = None

    @field_validator("reason", "person")
    @classmethod
    def _check_text(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class PostedMovement(Movement):
    """A movement posted through the public surface: it carries its own kind and project, and may
    name the requisition that asked for it (P2-I4-A fulfilment)."""

    kind: MovementKind
    scope: str = Field(min_length=1, max_length=80)
    requisition_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)


class _Batch(Command):
    model_config = ConfigDict(extra="forbid")

    movements: list[Movement] = Field(min_length=1, max_length=MAX_MOVEMENTS)


class IssueStock(_Batch):
    """Issue stock to a crew or a cost code (consumed; a reservation of the line is used first)."""


class TransferStock(_Batch):
    """Move stock between two locations of the project."""


class ReturnStock(_Batch):
    """Return issued stock to a location (at most what was issued net)."""


class ReserveStock(_Batch):
    """Hold available stock for a take-off line."""


class UnreserveStock(_Batch):
    """Release a reservation."""


class AdjustStock(_Batch):
    """Correct a count in or out, with a reason (superuser)."""


class ScrapStock(_Batch):
    """Dispose of damaged or nonconforming stock, with a reason (superuser)."""


#: What each kind takes besides ``lot_key``, ``qty`` and ``uom``: field -> required.
_FIELDS: Final[dict[str, dict[str, bool]]] = {
    ISSUE: {
        "from_location": True,
        "mto_line_id": False,
        "cost_code_id": False,
        "person": False,
        "reason": False,
    },
    TRANSFER: {"from_location": True, "to_location": True, "person": False, "reason": False},
    RETURN: {"to_location": True, "person": False, "reason": False},
    # adjust: ``direction`` says which of ``from`` (out) and ``to`` (in) the movement has
    ADJUST: {
        "direction": True,
        "from_location": False,
        "to_location": False,
        "reason": True,
        "person": False,
    },
    SCRAP: {"from_location": True, "reason": True, "person": False},
    RESERVE: {"from_location": True, "mto_line_id": True, "reason": False},
    UNRESERVE: {"from_location": True, "mto_line_id": True, "reason": False},
}
_OPTIONAL: Final = (
    "from_location",
    "to_location",
    "cost_code_id",
    "mto_line_id",
    "reason",
    "person",
    "direction",
)


@dataclass(frozen=True)
class _Lot:
    id: str
    key: str
    project_item_id: str
    uom: str
    issued_net: Decimal
    consumable: bool


@dataclass(frozen=True)
class _Line:
    id: str
    project_item_id: str
    qty: Decimal
    reserved: Decimal
    work_package_id: str | None
    iwp_id: str | None


_LOT = text(
    "SELECT l.id, r.key, l.project_item_id, l.uom, l.issued_net, p.consumable "
    f"FROM {LOT_TABLE} l JOIN cur_core_record r ON r.id = l.id "
    f"JOIN {PROJECT_ITEM_TABLE} p ON p.id = l.project_item_id "
    "WHERE l.scope = :scope AND r.key = :key AND r.voided = :no"
)
_LINE = text(
    "SELECT l.id, l.project_item_id, l.qty, l.reserved_qty, l.work_package_id, w.type AS wp_type "
    f"FROM {MTO_LINE_TABLE} l JOIN cur_core_record r ON r.id = l.id "
    "LEFT JOIN cur_core_record w ON w.id = l.work_package_id "
    "WHERE l.id = :id AND l.scope = :scope AND r.voided = :no"
)
_COST_CODE = text(
    "SELECT type FROM cur_core_record WHERE id = :id AND scope = :scope AND voided = :no"
)
_LOCATION = text(
    f"SELECT t.id, t.retired FROM {LOCATION_TABLE} t JOIN cur_core_record r ON r.id = t.id "
    "WHERE t.scope = :scope AND t.code = :code AND r.voided = :no"
)
_BALANCE = text(
    f"SELECT on_hand, reserved FROM {STOCK_TABLE} WHERE lot_id = :lot AND location_id = :loc"
)
_HELD = text(
    f"SELECT qty FROM {RESERVATION_TABLE} "
    "WHERE lot_id = :lot AND location_id = :loc AND mto_line_id = :line"
)


class _Checker:
    """The rules of one batch, with the lookups it repeats remembered (they cannot change inside
    a batch: movements move stock, not records)."""

    def __init__(self, conn: Connection, scope: str, kind: str) -> None:
        self.conn = conn
        self.scope = scope
        self.kind = kind
        self._locations: dict[str, tuple[str, bool]] = {}
        self._cost_codes: set[str] = set()

    # --- lookups ------------------------------------------------------------------------------

    def lot(self, i: int, key: str) -> _Lot:
        row = self.conn.execute(_LOT, {"scope": self.scope, "key": key, "no": False}).first()
        if row is None or confidentiality.is_hidden(self.conn, str(row.id)):
            raise LotNotFoundError(f"movement {i}: there is no such lot in the project")
        return _Lot(
            id=str(row.id),
            key=str(row.key),
            project_item_id=str(row.project_item_id),
            uom=str(row.uom),
            issued_net=dec(row.issued_net),
            consumable=bool(row.consumable),
        )

    def location(self, i: int, code: str) -> tuple[str, bool]:
        """``(location id, retired)`` of a location of the project the viewer may read."""
        if code not in self._locations:
            row = self.conn.execute(
                _LOCATION, {"scope": self.scope, "code": code, "no": False}
            ).first()
            if row is None or confidentiality.is_hidden(self.conn, str(row.id)):
                raise LocationNotFoundError(f"movement {i}: there is no such location")
            self._locations[code] = (str(row.id), bool(row.retired))
        return self._locations[code]

    def active_location(self, i: int, code: str) -> str:
        found, retired = self.location(i, code)
        if retired:
            raise MovementRuleError(f"movement {i}: the location is retired")
        return found

    def line(self, i: int, line_id: str) -> _Line:
        row = self.conn.execute(_LINE, {"id": line_id, "scope": self.scope, "no": False}).first()
        if row is None or confidentiality.is_hidden(self.conn, line_id):
            raise MtoLineNotFoundError(f"movement {i}: there is no such take-off line")
        wp = None if row.work_package_id is None else str(row.work_package_id)
        return _Line(
            id=str(row.id),
            project_item_id=str(row.project_item_id),
            qty=dec(row.qty),
            reserved=dec(row.reserved_qty),
            work_package_id=wp,
            iwp_id=wp if wp is not None and row.wp_type == IWP_TYPE else None,
        )

    def cost_code(self, i: int, code_id: str) -> str:
        if code_id not in self._cost_codes:
            found = self.conn.execute(
                _COST_CODE, {"id": code_id, "scope": self.scope, "no": False}
            ).scalar_one_or_none()
            if found != COST_CODE_TYPE or confidentiality.is_hidden(self.conn, code_id):
                raise CostCodeNotFoundError(f"movement {i}: there is no such cost code")
            self._cost_codes.add(code_id)
        return code_id

    def available(self, lot: str, loc: str) -> Decimal:
        row = self.conn.execute(_BALANCE, {"lot": lot, "loc": loc}).first()
        return ZERO if row is None else dec(row.on_hand) - dec(row.reserved)

    def held(self, lot: str, loc: str, line: str) -> Decimal:
        found = self.conn.execute(
            _HELD, {"lot": lot, "loc": loc, "line": line}
        ).scalar_one_or_none()
        return ZERO if found is None else dec(found)

    # --- one movement -------------------------------------------------------------------------

    def fields(self, i: int, m: Movement) -> None:
        """Every field the kind needs is there and none the kind does not take."""
        takes = _FIELDS[self.kind]
        for name in _OPTIONAL:
            value = getattr(m, name)
            if value is None and takes.get(name, False):
                raise MovementRuleError(f"movement {i}: {name} is required for {self.kind}")
            if value is not None and name not in takes:
                raise MovementRuleError(
                    f"movement {i}: {name} does not apply to a {self.kind} movement"
                )
        if self.kind == ADJUST:
            side = "to_location" if m.direction == "in" else "from_location"
            other = "from_location" if m.direction == "in" else "to_location"
            if getattr(m, side) is None:
                raise MovementRuleError(
                    f"movement {i}: {side} is required for adjust {m.direction}"
                )
            if getattr(m, other) is not None:
                raise MovementRuleError(
                    f"movement {i}: {other} does not apply to adjust {m.direction}"
                )
        if self.kind in (ADJUST, SCRAP) and not (m.reason or "").strip():
            raise MovementRuleError(f"movement {i}: a reason is required for {self.kind}")

    def payload(
        self, i: int, m: Movement, requisition_id: str | None
    ) -> tuple[str, dict[str, Any]]:
        """The lot id and the event payload of a movement that passes every rule of its kind."""
        self.fields(i, m)
        qty = parse_qty(m.qty, f"movement {i} qty")
        lot = self.lot(i, m.lot_key)
        if m.uom != lot.uom:
            raise MovementRuleError(f"movement {i}: uom must be the unit of the lot")
        out: dict[str, Any] = {
            "kind": self.kind,
            "qty": qty_text(qty),
            "uom": lot.uom,
            "direction": m.direction,
            "from_location_id": None,
            "to_location_id": None,
            "cost_code_id": None,
            "mto_line_id": None,
            "iwp_id": None,
            "requisition_id": requisition_id,
            "person": m.person,
            "reason": m.reason,
            "feed_policy": "none",
        }
        rules = {
            ISSUE: self._issue,
            TRANSFER: self._transfer,
            RETURN: self._return,
            ADJUST: self._adjust,
            SCRAP: self._scrap,
            RESERVE: self._reserve,
            UNRESERVE: self._unreserve,
        }
        rules[self.kind](i, m, lot, qty, out)
        return lot.id, out

    # --- the seven kinds ----------------------------------------------------------------------

    def _issue(self, i: int, m: Movement, lot: _Lot, qty: Decimal, out: dict[str, Any]) -> None:
        assert m.from_location is not None
        where = self.location(i, m.from_location)[0]
        out["from_location_id"] = where
        covered = ZERO
        if m.mto_line_id is not None:
            line = self.line(i, m.mto_line_id)
            if line.project_item_id != lot.project_item_id:
                raise MovementRuleError(f"movement {i}: the lot is not of the item of the line")
            out["mto_line_id"] = line.id
            out["iwp_id"] = line.iwp_id
            covered = self.held(lot.id, where, line.id)
        if lot.consumable and m.cost_code_id is None:
            raise MovementRuleError(f"movement {i}: a consumable is issued against a cost code")
        if m.cost_code_id is not None:
            out["cost_code_id"] = self.cost_code(i, m.cost_code_id)
        if qty > self.available(lot.id, where) + covered:
            raise InsufficientStockError(
                f"movement {i}: the quantity is more than is available at the location"
            )

    def _transfer(self, i: int, m: Movement, lot: _Lot, qty: Decimal, out: dict[str, Any]) -> None:
        assert m.from_location is not None and m.to_location is not None
        if m.from_location == m.to_location:
            raise MovementRuleError(f"movement {i}: from and to are the same location")
        origin = self.active_location(i, m.from_location)
        target = self.active_location(i, m.to_location)
        if origin == target:
            raise MovementRuleError(f"movement {i}: from and to are the same location")
        out["from_location_id"], out["to_location_id"] = origin, target
        if qty > self.available(lot.id, origin):
            raise InsufficientStockError(
                f"movement {i}: the quantity is more than is available at the location"
            )

    def _return(self, i: int, m: Movement, lot: _Lot, qty: Decimal, out: dict[str, Any]) -> None:
        assert m.to_location is not None
        out["to_location_id"] = self.active_location(i, m.to_location)
        if qty > lot.issued_net:
            raise InsufficientStockError(
                f"movement {i}: the quantity is more than was issued from the lot"
            )

    def _adjust(self, i: int, m: Movement, lot: _Lot, qty: Decimal, out: dict[str, Any]) -> None:
        if m.direction == "in":
            assert m.to_location is not None
            out["to_location_id"] = self.active_location(i, m.to_location)
            return
        assert m.from_location is not None
        origin = self.location(i, m.from_location)[0]
        out["from_location_id"] = origin
        if qty > self.available(lot.id, origin):
            raise InsufficientStockError(
                f"movement {i}: the quantity is more than is available at the location"
            )

    def _scrap(self, i: int, m: Movement, lot: _Lot, qty: Decimal, out: dict[str, Any]) -> None:
        assert m.from_location is not None
        origin = self.location(i, m.from_location)[0]
        out["from_location_id"] = origin
        if qty > self.available(lot.id, origin):
            raise InsufficientStockError(
                f"movement {i}: the quantity is more than is available at the location"
            )

    def _reserve(self, i: int, m: Movement, lot: _Lot, qty: Decimal, out: dict[str, Any]) -> None:
        assert m.from_location is not None and m.mto_line_id is not None
        where = self.location(i, m.from_location)[0]
        line = self.line(i, m.mto_line_id)
        if line.project_item_id != lot.project_item_id:
            raise MovementRuleError(f"movement {i}: the lot is not of the item of the line")
        out["from_location_id"], out["mto_line_id"], out["iwp_id"] = where, line.id, line.iwp_id
        if qty > self.available(lot.id, where):
            raise InsufficientStockError(
                f"movement {i}: the quantity is more than is available at the location"
            )
        if line.reserved + qty > line.qty:
            raise InsufficientStockError(
                f"movement {i}: the reservations of the line would be more than its quantity"
            )

    def _unreserve(self, i: int, m: Movement, lot: _Lot, qty: Decimal, out: dict[str, Any]) -> None:
        assert m.from_location is not None and m.mto_line_id is not None
        where = self.location(i, m.from_location)[0]
        line = self.line(i, m.mto_line_id)
        out["from_location_id"], out["mto_line_id"], out["iwp_id"] = where, line.id, line.iwp_id
        if qty > self.held(lot.id, where, line.id):
            raise InsufficientStockError(f"movement {i}: the quantity is more than is reserved")


def post_batch(
    uow: UnitOfWork,
    *,
    kind: str,
    scope: str,
    movements: Sequence[Movement],
    actor: str,
    source: str,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> list[Event]:
    """Check and append a batch of one kind; the events in batch order. Raises on the first
    problem; the caller's unit of work then rolls back, so nothing of the batch is written."""
    if kind not in _FIELDS:
        raise MovementRuleError(f"{kind!r} is not a kind of movement a batch can post")
    if not 1 <= len(movements) <= MAX_MOVEMENTS:
        raise MovementRuleError(f"a batch holds 1 to {MAX_MOVEMENTS} movements")
    if not scope.startswith("project:"):
        raise MovementRuleError("movements belong to a project")
    check = _Checker(uow.conn(), scope, kind)
    correlation = correlation_id or new_ulid()
    events: list[Event] = []
    for i, m in enumerate(movements, start=1):
        requisition = m.requisition_id if isinstance(m, PostedMovement) else None
        lot_id, payload = check.payload(i, m, requisition)
        done = uow.append(
            stream_id=lot_id,
            stream_type=STOCK_LOT,
            scope=scope,
            expected_version=version_of(uow, lot_id),
            events=[NewEvent(event_type=LOT_MOVED, payload=payload)],
            actor=actor,
            source=source,
            correlation_id=correlation,
            causation_id=causation_id,
        )
        events.extend(done.events)
    return events


def _handle(kind: str, uow: UnitOfWork, cmd: _Batch) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    events = post_batch(
        uow,
        kind=kind,
        scope=cmd.scope,
        movements=cmd.movements,
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id,
        causation_id=cmd.causation_id,
    )
    last = events[-1]
    return CommandResult(
        stream_id=last.stream_id, key=None, version=last.stream_version, events=events
    )


def handle_issue_stock(uow: UnitOfWork, cmd: IssueStock) -> CommandResult:
    return _handle(ISSUE, uow, cmd)


def handle_transfer_stock(uow: UnitOfWork, cmd: TransferStock) -> CommandResult:
    return _handle(TRANSFER, uow, cmd)


def handle_return_stock(uow: UnitOfWork, cmd: ReturnStock) -> CommandResult:
    return _handle(RETURN, uow, cmd)


def handle_reserve_stock(uow: UnitOfWork, cmd: ReserveStock) -> CommandResult:
    return _handle(RESERVE, uow, cmd)


def handle_unreserve_stock(uow: UnitOfWork, cmd: UnreserveStock) -> CommandResult:
    return _handle(UNRESERVE, uow, cmd)


def handle_adjust_stock(uow: UnitOfWork, cmd: AdjustStock) -> CommandResult:
    return _handle(ADJUST, uow, cmd)


def handle_scrap_stock(uow: UnitOfWork, cmd: ScrapStock) -> CommandResult:
    return _handle(SCRAP, uow, cmd)
