"""Load targets of the materials module (W0-B2: group ``throughline.load_targets``).

Three targets, each a column mapping that **plans through the command** it applies: the file's
columns become the fields of ``DefineItem``, ``DefineLocation`` or ``RecordPoLine``, the plan
runs the
command's own ``check_*`` rule, and the apply stage calls the command's handler. The loader and the
command therefore share one check. All three are create-only: a key the scope holds is left
alone and
counted; compensation voids exactly the records the run made, and only while nothing depends
on them.

* ``materials_item_master`` (scope ``company``): code, description, category, uom, size, rating,
  material, consumable.
* ``materials_location`` (scope ``project``): code, title, kind, parent_code (parents first).
* ``materials_po_line`` (scope ``project``): po_number, line_no, item_code, qty_ordered, uom,
  promised_date, supplier_text.

The names use an underscore: the group allows ``^[a-z][a-z0-9_]*$``. A problem is a line number and
fixed words or a field name, never a cell of the file.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Connection, text
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import DuplicateKeyError
from tl_core.uow import UnitOfWork
from tl_mod_legacy.errors import MappingProblemError
from tl_mod_legacy.model import Grid, LoaderDef
from tl_mod_legacy.targets import (
    Comparison,
    Created,
    Plan,
    PlannedRow,
    Reversal,
    Target,
    TargetScope,
)

from tl_mod_materials.common import parse_qty, qty_text, version_of
from tl_mod_materials.errors import MaterialsError
from tl_mod_materials.handlers.items import (
    DefineItem,
    check_define_item,
    handle_define_item,
)
from tl_mod_materials.handlers.locations import (
    DefineLocation,
    check_define_location,
    handle_define_location,
)
from tl_mod_materials.handlers.po_lines import (
    RecordPoLine,
    check_record_po_line,
    handle_record_po_line,
    po_key,
)
from tl_mod_materials.names import (
    ITEM_MASTER,
    LOCATION,
    LOCATION_TABLE,
    PO_LINE,
    RECEIPT_TABLE,
    TARGET_ITEM_MASTER,
    TARGET_LOCATION,
    TARGET_PO_LINE,
)
from tl_mod_materials.registry import (
    get_item,
    get_location,
    get_po_line,
    has_active_child,
    holds_stock,
    item_is_adopted,
)

KEY_BATCH = 400
PLAN_ACTOR = "user:plan"
PLAN_SOURCE = "load"
MAX_REASON = 500
_TRUE = frozenset({"true", "yes", "1"})
_FALSE = frozenset({"false", "no", "0"})


class _CellError(ValueError):
    """A cell cannot be read as the field it maps to; ``fields`` names the field, never the cell."""

    def __init__(self, *fields: str) -> None:
        super().__init__(", ".join(fields))
        self.fields = fields


def _opt(raw: Mapping[str, str], column: str) -> str | None:
    value = raw.get(column, "").strip()
    return value or None


def _bool(raw: Mapping[str, str], column: str) -> bool:
    value = raw.get(column, "").strip().lower()
    if not value:
        return False
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise _CellError("consumable")


def _problem(exc: Exception) -> str:
    """Fixed words and field names for any failure of a row: never the text of a cell."""
    if isinstance(exc, ValidationError):
        names = sorted({str(e["loc"][0]) for e in exc.errors() if e["loc"]})
        return ("invalid " + ", ".join(names))[:300] if names else "invalid row"
    if isinstance(exc, _CellError):
        return "invalid " + ", ".join(exc.fields)
    if isinstance(exc, DuplicateKeyError):
        return "the key is already used by another record"
    return str(exc)[:300]


def _current_dict(**values: Any) -> dict[str, str | None]:
    return {k: (None if v is None else str(v)) for k, v in values.items()}


class _CommandTarget:
    """A target that plans through one command and applies it (see the module docstring)."""

    kind: str
    module = "materials"
    scope: TargetScope
    record_type: str
    required: tuple[str, ...]
    optional: tuple[str, ...] = ()

    # --- hooks a target fills ---------------------------------------------------------------

    def command(self, scope: str, raw: Mapping[str, str], **base: Any) -> Command:
        raise NotImplementedError

    def key_of(self, cmd: Any) -> str:
        raise NotImplementedError

    def handler(self) -> Callable[[UnitOfWork, Any], CommandResult]:
        raise NotImplementedError

    def lookup(self, conn: Connection, scope: str, cmd: Any) -> str | None:
        """The id of the live record the row would create, when the scope already holds it."""
        raise NotImplementedError

    def check(self, conn: Connection, cmd: Any, state: dict[str, int]) -> None:
        """The command's own rule; ``state`` carries what earlier rows of the file would make."""
        raise NotImplementedError

    def current(self, conn: Connection, scope: str, cmd: Any) -> dict[str, str | None] | None:
        raise NotImplementedError

    def intended(self, cmd: Any) -> dict[str, str | None]:
        raise NotImplementedError

    def dependants(self, conn: Connection, record_id: str) -> str | None:
        """Why the record cannot be taken back (something depends on it), else ``None``."""
        raise NotImplementedError

    # --- the grid --------------------------------------------------------------------------

    def _cells(self, grid: Grid) -> list[tuple[int, dict[str, str]]]:
        missing = [c for c in self.required if c not in grid.columns]
        if missing:
            raise MappingProblemError(f"target {self.kind}: the file has no column {missing[0]!r}")
        out: list[tuple[int, dict[str, str]]] = []
        for index, cells in enumerate(grid.rows):
            raw = {c: ("" if v is None else v) for c, v in zip(grid.columns, cells, strict=False)}
            out.append((index + 2, raw))
        return out

    def _build(self, scope: str, raw: Mapping[str, str]) -> Command:
        return self.command(scope, raw, actor=PLAN_ACTOR, source=PLAN_SOURCE)

    # --- the Target protocol ---------------------------------------------------------------

    def plan(self, conn: Connection, scope: str, loader: LoaderDef, grid: Grid) -> Plan:
        new: list[PlannedRow] = []
        existing: list[str] = []
        invalid: list[tuple[int, str]] = []
        seen: set[str] = set()
        state: dict[str, int] = {}
        for line, raw in self._cells(grid):
            try:
                cmd = self._build(scope, raw)
            except (ValidationError, _CellError) as exc:
                invalid.append((line, _problem(exc)))
                continue
            key = self.key_of(cmd)
            if key in seen:
                invalid.append((line, "key repeated"))
                continue
            seen.add(key)
            if self.lookup(conn, scope, cmd) is not None:
                existing.append(key)
                continue
            try:
                self.check(conn, cmd, state)
            except (MaterialsError, DuplicateKeyError) as exc:
                invalid.append((line, _problem(exc)))
                continue
            new.append(PlannedRow(line, key, dict(raw), cmd))
        return Plan(rows=new, existing=existing, invalid=invalid)

    def apply(
        self,
        uow: UnitOfWork,
        scope: str,
        loader: LoaderDef,
        plan: Plan,
        *,
        actor: str,
        source: str,
        correlation_id: str,
        confidentiality: str | None,
    ) -> list[Created]:
        made: list[Created] = []
        handle = self.handler()
        for row in plan.rows:
            cmd = row.native.model_copy(
                update={"actor": actor, "source": source, "correlation_id": correlation_id}
            )
            result = handle(uow, cmd)
            made.append(Created(result.stream_id, row.key, row.line, row.raw))
        return made

    def compare(
        self, conn: Connection, scope: str, loader: LoaderDef, grid: Grid, created_keys: set[str]
    ) -> Comparison:
        valid = matched = left = invalid = 0
        missing: list[int] = []
        differs: list[tuple[int, str]] = []
        seen: set[str] = set()
        bad = {line for line, _ in self.plan(conn, scope, loader, grid).invalid}
        for line, raw in self._cells(grid):
            if line in bad:
                invalid += 1  # also a key that appears again: judged on its first row only
                continue
            cmd = self._build(scope, raw)
            key = self.key_of(cmd)
            if key in seen:
                invalid += 1
                continue
            seen.add(key)
            valid += 1
            found = self.current(conn, scope, cmd)
            if found is None:
                missing.append(line)
                continue
            fields = [
                name
                for name, wanted in self.intended(cmd).items()
                if wanted is not None and wanted != found.get(name)
            ]
            if not fields:
                matched += 1
            elif key in created_keys:
                differs.extend((line, name) for name in fields)
            else:
                left += 1
        return Comparison(valid, matched, missing, differs, left, invalid)

    def reversals(
        self, conn: Connection, scope: str, record_ids: list[str], correlation_id: str
    ) -> list[Reversal]:
        found: list[Reversal] = []
        for record_id in record_ids:
            row = conn.execute(
                text("SELECT key, status, voided, type, scope FROM cur_core_record WHERE id = :id"),
                {"id": record_id},
            ).first()
            if row is None or row.scope != scope or row.type != self.record_type:
                found.append(
                    Reversal(record_id, None, None, False, "a record the load made is not there")
                )
                continue
            state = "Void" if bool(row.voided) else "Active"
            foreign = conn.execute(
                text("SELECT count(*) FROM events WHERE stream_id = :id AND correlation_id <> :c"),
                {"id": record_id, "c": correlation_id},
            ).scalar_one()
            if int(foreign):
                found.append(
                    Reversal(record_id, row.key, state, False, "it was changed after the load")
                )
                continue
            why = None if bool(row.voided) else self.dependants(conn, record_id)
            found.append(Reversal(record_id, row.key, state, why is None, why))
        return found

    def reverse(
        self,
        uow: UnitOfWork,
        scope: str,
        record_ids: list[str],
        *,
        actor: str,
        source: str,
        correlation_id: str,
        reason: str,
    ) -> int:
        count = 0
        for record_id in record_ids:
            voided = (
                uow.conn()
                .execute(
                    text("SELECT voided FROM cur_core_record WHERE id = :id"), {"id": record_id}
                )
                .scalar_one_or_none()
            )
            if voided is None or bool(voided):
                continue
            uow.append(
                stream_id=record_id,
                stream_type=self.record_type,
                scope=scope,
                expected_version=version_of(uow, record_id),
                events=[
                    NewEvent(event_type="Record.Voided", payload={"reason": reason[:MAX_REASON]})
                ],
                actor=actor,
                source=source,
                correlation_id=correlation_id,
            )
            count += 1
        return count


class ItemMasterTarget(_CommandTarget):
    """The company item library: ``DefineItem`` per row."""

    kind = TARGET_ITEM_MASTER
    scope: TargetScope = "company"
    record_type = ITEM_MASTER
    required = ("code", "description", "category", "uom")
    optional = ("size", "rating", "material", "consumable")

    def command(self, scope: str, raw: Mapping[str, str], **base: Any) -> Command:
        return DefineItem(
            scope=scope,
            code=raw.get("code", "").strip(),
            title=raw.get("description", "").strip(),
            category=raw.get("category", "").strip(),
            base_uom=raw.get("uom", "").strip(),
            size_text=_opt(raw, "size"),
            rating_text=_opt(raw, "rating"),
            material_code=_opt(raw, "material"),
            consumable=_bool(raw, "consumable"),
            **base,
        )

    def key_of(self, cmd: DefineItem) -> str:
        return cmd.code

    def handler(self) -> Callable[[UnitOfWork, Any], CommandResult]:
        return handle_define_item

    def lookup(self, conn: Connection, scope: str, cmd: DefineItem) -> str | None:
        found = get_item(conn, cmd.code)
        return None if found is None else found.id

    def check(self, conn: Connection, cmd: DefineItem, state: dict[str, int]) -> None:
        check_define_item(conn, cmd)

    def current(
        self, conn: Connection, scope: str, cmd: DefineItem
    ) -> dict[str, str | None] | None:
        found = get_item(conn, cmd.code)
        if found is None:
            return None
        return _current_dict(
            title=found.title,
            category=found.category,
            base_uom=found.base_uom,
            size_text=found.size_text,
            rating_text=found.rating_text,
            material_code=found.material_code,
            consumable=found.consumable,
        )

    def intended(self, cmd: DefineItem) -> dict[str, str | None]:
        return _current_dict(
            title=cmd.title,
            category=cmd.category,
            base_uom=cmd.base_uom,
            size_text=cmd.size_text,
            rating_text=cmd.rating_text,
            material_code=cmd.material_code,
            consumable=cmd.consumable,
        )

    def dependants(self, conn: Connection, record_id: str) -> str | None:
        if item_is_adopted(conn, record_id):
            return "a project holds a copy of the item"
        return None


class LocationTarget(_CommandTarget):
    """A project's location tree: ``DefineLocation`` per row, parents first."""

    kind = TARGET_LOCATION
    scope: TargetScope = "project"
    record_type = LOCATION
    required = ("code", "title", "kind")
    optional = ("parent_code",)

    def command(self, scope: str, raw: Mapping[str, str], **base: Any) -> Command:
        return DefineLocation(
            scope=scope,
            code=raw.get("code", "").strip(),
            title=raw.get("title", "").strip(),
            kind=raw.get("kind", "").strip(),
            parent_code=_opt(raw, "parent_code"),
            **base,
        )

    def key_of(self, cmd: DefineLocation) -> str:
        return cmd.code

    def handler(self) -> Callable[[UnitOfWork, Any], CommandResult]:
        return handle_define_location

    def lookup(self, conn: Connection, scope: str, cmd: DefineLocation) -> str | None:
        found = get_location(conn, scope, cmd.code)
        return None if found is None else found.id

    def check(self, conn: Connection, cmd: DefineLocation, state: dict[str, int]) -> None:
        _, depth = check_define_location(conn, cmd, planned=state)
        state[cmd.code] = depth

    def current(
        self, conn: Connection, scope: str, cmd: DefineLocation
    ) -> dict[str, str | None] | None:
        found = get_location(conn, scope, cmd.code)
        if found is None:
            return None
        parent = None
        if found.parent_id is not None:
            parent = conn.execute(
                text(f"SELECT code FROM {LOCATION_TABLE} WHERE id = :id"), {"id": found.parent_id}
            ).scalar_one_or_none()
        return _current_dict(title=found.title, kind=found.kind, parent_code=parent)

    def intended(self, cmd: DefineLocation) -> dict[str, str | None]:
        return _current_dict(title=cmd.title, kind=cmd.kind, parent_code=cmd.parent_code)

    def dependants(self, conn: Connection, record_id: str) -> str | None:
        if holds_stock(conn, record_id):
            return "the location holds stock"
        if has_active_child(conn, record_id):
            return "the location has a child location"
        used = conn.execute(
            text(f"SELECT 1 FROM {RECEIPT_TABLE} WHERE location_id = :id"), {"id": record_id}
        ).first()
        if used is not None:
            return "a receipt names the location"
        return None


class PoLineTarget(_CommandTarget):
    """A project's PO line mirror: ``RecordPoLine`` per row (an unadopted item is adopted)."""

    kind = TARGET_PO_LINE
    scope: TargetScope = "project"
    record_type = PO_LINE
    required = ("po_number", "line_no", "item_code", "qty_ordered", "uom")
    optional = ("promised_date", "supplier_text")

    def command(self, scope: str, raw: Mapping[str, str], **base: Any) -> Command:
        line = raw.get("line_no", "").strip()
        if not (line.isascii() and line.isdigit()):
            raise _CellError("line_no")
        return RecordPoLine(
            scope=scope,
            po_number=raw.get("po_number", "").strip(),
            line_no=int(line),
            item_code=raw.get("item_code", "").strip(),
            qty_ordered=raw.get("qty_ordered", "").strip(),
            uom=raw.get("uom", "").strip(),
            promised_date=_opt(raw, "promised_date"),
            supplier_text=_opt(raw, "supplier_text"),
            **base,
        )

    def key_of(self, cmd: RecordPoLine) -> str:
        return po_key(cmd.po_number, cmd.line_no)

    def handler(self) -> Callable[[UnitOfWork, Any], CommandResult]:
        return handle_record_po_line

    def lookup(self, conn: Connection, scope: str, cmd: RecordPoLine) -> str | None:
        found = get_po_line(conn, scope, self.key_of(cmd))
        return None if found is None else found.id

    def check(self, conn: Connection, cmd: RecordPoLine, state: dict[str, int]) -> None:
        check_record_po_line(conn, cmd)

    def current(
        self, conn: Connection, scope: str, cmd: RecordPoLine
    ) -> dict[str, str | None] | None:
        found = get_po_line(conn, scope, self.key_of(cmd))
        if found is None:
            return None
        item = conn.execute(
            text("SELECT key FROM cur_core_record WHERE id = :id"), {"id": found.project_item_id}
        ).scalar_one_or_none()
        return _current_dict(
            item_code=item,
            qty_ordered=qty_text(found.qty_ordered),
            uom=found.uom,
            promised_date=found.promised_date,
            supplier_text=found.supplier_text,
        )

    def intended(self, cmd: RecordPoLine) -> dict[str, str | None]:
        return _current_dict(
            item_code=cmd.item_code,
            qty_ordered=qty_text(parse_qty(cmd.qty_ordered, "qty_ordered")),
            uom=cmd.uom,
            promised_date=cmd.promised_date,
            supplier_text=cmd.supplier_text,
        )

    def dependants(self, conn: Connection, record_id: str) -> str | None:
        used = conn.execute(
            text(f"SELECT 1 FROM {RECEIPT_TABLE} WHERE po_line_id = :id"), {"id": record_id}
        ).first()
        if used is not None:
            return "a receipt names the PO line"
        return None


def item_master_target() -> Target:
    """Entry point ``materials_item_master`` of the group ``throughline.load_targets``."""
    return ItemMasterTarget()


def location_target() -> Target:
    """Entry point ``materials_location`` of the group ``throughline.load_targets``."""
    return LocationTarget()


def po_line_target() -> Target:
    """Entry point ``materials_po_line`` of the group ``throughline.load_targets``."""
    return PoLineTarget()


__all__ = [
    "ItemMasterTarget",
    "LocationTarget",
    "PoLineTarget",
    "item_master_target",
    "location_target",
    "po_line_target",
]
