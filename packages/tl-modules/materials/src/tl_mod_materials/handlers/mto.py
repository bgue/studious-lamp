"""Material take-offs: the ``mto`` publish target's work and ``AssignMtoLines`` (m4 sections 2, 3).

A derived document of schema kind ``mto`` is published into one ``materials.MTO`` and its
``materials.MTOLine`` rows through the documents module's publish pipeline (ADR-0014); the pipeline
asks the target (``mto.py``) to plan, to create and to reverse, and this module does it.

* **Keys.** The take-off is ``<document>@<revision>/MTO`` and a line ``<take-off key>/<line>``
  (``ISO-1234@A/MTO/001``). The key of a voided record stays taken, so after a compensation the
  next take-off of the same revision is ``ISO-1234@A/MTO-2`` (and so on).
* **Create-only.** Where the revision has a live take-off, its lines are skipped and counted
  (``exists``, or ``differs`` when the row has no line there); nothing is ever changed. A new
  take-off gets all its rows or none.
* **Compensation** voids the lines, then the take-off, and retracts the links the publication
  wrote. It refuses (``compensation_item``) while any line has a reservation or an issue.

Every refusal text is fixed words plus an index or a field name; it never repeats a cell.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import Connection, bindparam, text
from tl_core import confidentiality
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.links import (
    AddLink,
    RetractLink,
    handle_add_link,
    handle_retract_link,
)
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_mod_documents.derivation import rows as derived_rows
from tl_mod_documents.derivation.publish import PlanRow, PublishBase, publish_derived

from tl_mod_materials.common import (
    ZERO,
    append,
    correlated,
    dec,
    find_record,
    parse_qty,
    qty_text,
    require_project,
)
from tl_mod_materials.errors import (
    InvalidQuantityError,
    InvalidValueError,
    MtoLineInUseError,
    MtoLineNotFoundError,
    MtoPublishRefusedError,
    NoChangesError,
    WorkPackageNotFoundError,
)
from tl_mod_materials.limits import MAX_ITEM_CODE, MAX_LINE_NO, MAX_MTO_LINES
from tl_mod_materials.names import (
    BELONGS_TO,
    DERIVED_FROM,
    MTO,
    MTO_DEFINED,
    MTO_LINE,
    MTO_LINE_ASSIGNED,
    MTO_LINE_DEFINED,
    MTO_LINE_TABLE,
    REFERENCES,
)
from tl_mod_materials.registry import ProjectItemRow, get_project_item

#: The name of the publish target (the entry point's name and a schema's ``target_kind``).
TARGET_MTO = "mto"
#: The record types of a work package, checked by type string (no import of an awp module).
WORK_PACKAGE_TYPES = ("awp.CWP", "awp.IWP")
TAG_TYPE = "engineering.Tag"
#: The fields a mapping may send a column to.
MAPPING_FIELDS = ("number", "item_code", "qty", "uom", "tag")
LINK_SOURCE = "import"

#: Fixed texts. The refusal of a compensation is the same whatever the lines hold.
IN_USE_COMPENSATE = (
    "the take-off has a line with a reservation or an issue; unreserve or return the stock first"
)
IN_USE_ASSIGN = "the line has a reservation or an issue; it cannot move to another work package"

#: The work package of the publication in progress (the pipeline's ``create`` takes no extra
#: argument, so the handler leaves it here for the duration of the call).
_WORK_PACKAGE: ContextVar[str | None] = ContextVar("materials_mto_work_package", default=None)

_WP = text(
    "SELECT id FROM cur_core_record WHERE scope = :scope AND key = :key AND voided = :no "
    "AND type IN :types"
).bindparams(bindparam("types", expanding=True))
_MTOS = text(
    "SELECT id, key, voided FROM cur_core_record "
    "WHERE scope = :scope AND type = :type AND substr(key, 1, :n) = :base"
)
_LIVE_LINES = text(
    "SELECT l.id, l.line_no, l.reserved_qty, l.issued_qty "
    f"FROM {MTO_LINE_TABLE} l JOIN cur_core_record r ON r.id = l.id "
    "WHERE l.mto_id = :mto AND r.voided = :no ORDER BY l.line_no"
)
_LINE_BY_KEY = text(
    "SELECT l.id, r.key, l.work_package_id, l.reserved_qty, l.issued_qty "
    f"FROM {MTO_LINE_TABLE} l JOIN cur_core_record r ON r.id = l.id "
    "WHERE l.scope = :scope AND r.key = :key AND r.voided = :no"
)
_MODULE_LINKS = text(
    "SELECT link_id FROM cur_links WHERE from_id IN :ids AND source IN ('import', 'rule') "
    "AND status <> 'retracted' ORDER BY link_id"
).bindparams(bindparam("ids", expanding=True))
_OLD_WP_LINK = text(
    "SELECT link_id FROM cur_links WHERE from_id = :line AND to_id = :wp AND relation = :rel "
    "AND status <> 'retracted'"
)
_VOIDED = text("SELECT voided FROM cur_core_record WHERE id = :id")


class PublishDerivedMto(PublishBase):
    """Publish a valid derived document of kind ``mto`` as a take-off (superuser).

    ``work_package_number`` (a CWP or IWP of the project) assigns every line when it is given.
    """

    work_package_number: str | None = Field(default=None, min_length=1, max_length=60)

    @field_validator("work_package_number")
    @classmethod
    def _wp(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value


class AssignMtoLines(Command):
    """Assign take-off lines to a work package (user); refused when a line has stock against it."""

    model_config = ConfigDict(extra="forbid")

    mto_lines: list[str] = Field(min_length=1, max_length=MAX_MTO_LINES)
    work_package_number: str = Field(min_length=1, max_length=60)

    @field_validator("mto_lines")
    @classmethod
    def _keys(cls, value: list[str]) -> list[str]:
        if any(not k.strip() or len(k) > 120 for k in value):
            raise ValueError("a line key is blank or too long")
        return value

    @field_validator("work_package_number")
    @classmethod
    def _wp(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


# --- work packages ---------------------------------------------------------------------------


def work_package_id(conn: Connection, scope: str, number: str) -> str:
    """The id of the CWP or IWP of the project with that number (by type string)."""
    found = conn.execute(
        _WP, {"scope": scope, "key": number, "no": False, "types": list(WORK_PACKAGE_TYPES)}
    ).scalar_one_or_none()
    if found is None or confidentiality.is_hidden(conn, str(found)):
        raise WorkPackageNotFoundError(f"no work package with that number in {scope}")
    return str(found)


# --- the plan ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class MtoRow:
    """One line the publication will create (the target's own creatable object)."""

    mto_key: str
    line_no: int
    project_item_id: str
    qty: Decimal
    uom: str
    tag_id: str | None

    @property
    def key(self) -> str:
        return line_key(self.mto_key, self.line_no)


def mto_base_key(derived: derived_rows.DerivedRow) -> str:
    return f"{derived.source_document_number}@{derived.source_revision_code}/MTO"


def line_key(mto_key: str, line_no: int) -> str:
    return f"{mto_key}/{line_no:03d}"


def _generation(base: str, key: str) -> int | None:
    """1 for ``base``, ``n`` for ``base-n`` (n >= 2), else None."""
    if key == base:
        return 1
    tail = key[len(base) + 1 :] if key.startswith(base + "-") else ""
    if tail.isascii() and tail.isdigit() and int(tail) >= 2:
        return int(tail)
    return None


def current_mto(conn: Connection, scope: str, base: str) -> tuple[str | None, str]:
    """``(id of the live take-off or None, the key a new take-off would take)`` for ``base``."""
    found = conn.execute(_MTOS, {"scope": scope, "type": MTO, "n": len(base), "base": base}).all()
    latest = 0
    for row in found:
        generation = _generation(base, str(row.key))
        if generation is None:
            continue
        if not bool(row.voided):
            return str(row.id), str(row.key)
        latest = max(latest, generation)
    nxt = latest + 1
    return None, base if nxt == 1 else f"{base}-{nxt}"


def _line_nos(conn: Connection, mto_id: str) -> set[int]:
    return {int(r.line_no) for r in conn.execute(_LIVE_LINES, {"mto": mto_id, "no": False})}


def _line_number(raw: str) -> int | None:
    text_ = raw.strip()
    if not (text_.isascii() and text_.isdigit() and len(text_) <= 5):
        return None
    number = int(text_)
    return number if 1 <= number <= MAX_LINE_NO else None


def plan_mto(
    conn: Connection,
    scope: str,
    derived: derived_rows.DerivedRow,
    mapped: Sequence[Any],
) -> tuple[list[PlanRow], list[MtoRow], dict[str, int]]:
    """``(plan rows, creatable rows, counts)`` of the mapped rows of a derived ``mto`` document."""
    base = mto_base_key(derived)
    live_id, mto_key = current_mto(conn, scope, base)
    taken = set() if live_id is None else _line_nos(conn, live_id)
    counts = {"create": 0, "exists": 0, "differs": 0, "invalid": 0}
    plan: list[PlanRow] = []
    creatable: list[MtoRow] = []
    seen: dict[int, int] = {}
    items: dict[str, ProjectItemRow | None] = {}
    for index, (fields, _psets, row_problems) in enumerate(mapped, start=1):
        problems: list[str] = list(row_problems)
        line_no = _line_number(fields.get("number", ""))
        if line_no is None:
            problems.append(f"the line number must be a whole number from 1 to {MAX_LINE_NO}")
        elif line_no in seen:
            problems.append(f"the line number is already used by row {seen[line_no]}")
        else:
            seen[line_no] = index
        code = fields.get("item_code", "").strip()
        item: ProjectItemRow | None = None
        if not code or len(code) > MAX_ITEM_CODE:
            problems.append("no item code")
        else:
            if code not in items:
                found = get_project_item(conn, scope, code)
                hidden = found is not None and confidentiality.is_hidden(conn, found.id)
                items[code] = None if hidden else found
            item = items[code]
            if item is None:
                problems.append("the item is not adopted in the project; adopt it first")
        qty: Decimal | None = None
        try:
            qty = parse_qty(fields.get("qty", "").strip(), "qty")
        except InvalidQuantityError as exc:
            problems.append(str(exc))
        uom = fields.get("uom", "").strip()
        if not uom:
            problems.append("no unit of measure")
        elif item is not None and uom != item.uom:
            problems.append(f"uom must be the unit of the item: {item.uom}")
        tag_id = None
        tag = fields.get("tag", "").strip()
        if tag:
            tag_id = find_record(conn, scope, TAG_TYPE, tag)
            if tag_id is not None and confidentiality.is_hidden(conn, tag_id):
                tag_id = None
        key = None if line_no is None else line_key(mto_key, line_no)
        action: str
        if problems:
            action = "invalid"
        elif live_id is None:
            action = "create"
        elif line_no in taken:
            action = "exists"
        else:
            action = "differs"
        counts[action] += 1
        values: dict[str, Any] = {"item_code": code, "qty": fields.get("qty", ""), "uom": uom}
        if tag:
            values["tag"] = tag
        plan.append(
            PlanRow(
                row=index,
                key=key,
                action=action,  # type: ignore[arg-type]
                problems=problems if action == "invalid" else [],
                values=values,
            )
        )
        if action == "create":
            assert line_no is not None and item is not None and qty is not None
            creatable.append(MtoRow(mto_key, line_no, item.id, qty, uom, tag_id))
    return plan, creatable, counts


# --- creating ----------------------------------------------------------------------------------


def _link(uow: UnitOfWork, base: dict[str, Any], from_id: str, to_id: str, relation: str) -> None:
    handle_add_link(
        uow,
        AddLink(**base, from_id=from_id, to_id=to_id, relation=relation, link_source=LINK_SOURCE),
        by_module=True,
    )


def create_mto(
    uow: UnitOfWork, base: dict[str, Any], built: Any, provenance: dict[str, str]
) -> list[str]:
    """One take-off and its lines for the creatable rows of ``built``; the take-off's id."""
    del provenance  # a take-off takes no property sets: its provenance is its links and source
    lines: list[MtoRow] = list(built.creatable)
    derived: derived_rows.DerivedRow = built.derived
    if not lines:
        raise MtoPublishRefusedError(f"{derived.key} has no line to publish")
    wp_id = _WORK_PACKAGE.get()
    envelope = Command(**base)
    mto_key = lines[0].mto_key
    made = create_module_record(
        uow,
        envelope,
        record_type=MTO,
        title=f"Material take-off {mto_key}",
        key=mto_key,
        composed_key=True,
        extra_events=[
            NewEvent(
                event_type=MTO_DEFINED,
                payload={
                    "derived_document_id": derived.id,
                    "revision_id": derived.source_revision_id,
                    "line_count": len(lines),
                },
            )
        ],
    )
    _link(uow, base, made.stream_id, derived.source_revision_id, DERIVED_FROM)
    for line in lines:
        record = create_module_record(
            uow,
            envelope,
            record_type=MTO_LINE,
            title=f"Take-off line {line.key}",
            key=line.key,
            composed_key=True,
            extra_events=[
                NewEvent(
                    event_type=MTO_LINE_DEFINED,
                    payload={
                        "mto_id": made.stream_id,
                        "line_no": line.line_no,
                        "project_item_id": line.project_item_id,
                        "qty": qty_text(line.qty),
                        "uom": line.uom,
                        "tag_id": line.tag_id,
                        "work_package_id": wp_id,
                    },
                )
            ],
        )
        _link(uow, base, record.stream_id, made.stream_id, BELONGS_TO)
        if wp_id is not None:
            _link(uow, base, record.stream_id, wp_id, BELONGS_TO)
        if line.tag_id is not None:
            _link(uow, base, record.stream_id, line.tag_id, REFERENCES)
    return [made.stream_id]


def handle_publish_derived_mto(uow: UnitOfWork, cmd: PublishDerivedMto) -> CommandResult:
    """Publish the take-off (superuser). Raises ``PublishRefusedError`` listing every reason."""
    require_project(cmd)
    conn = uow.conn()
    wp_id = (
        None
        if cmd.work_package_number is None
        else work_package_id(conn, cmd.scope, cmd.work_package_number)
    )
    token = _WORK_PACKAGE.set(wp_id)
    try:
        return publish_derived(uow, cmd, TARGET_MTO)
    finally:
        _WORK_PACKAGE.reset(token)


# --- compensation ------------------------------------------------------------------------------


def lines_in_use(conn: Connection, mto_id: str) -> bool:
    """Whether any live line of the take-off has a reservation or an issue (``Decimal`` compare)."""
    return any(
        dec(r.reserved_qty) > ZERO or dec(r.issued_qty) > ZERO
        for r in conn.execute(_LIVE_LINES, {"mto": mto_id, "no": False})
    )


def compensation_check(conn: Connection, record_id: str, scope: str) -> tuple[bool, str | None]:
    """``(reversible, problem)`` for a take-off the publication made."""
    row = conn.execute(
        text("SELECT scope, voided FROM cur_core_record WHERE id = :id"), {"id": record_id}
    ).first()
    if row is None or row.scope != scope:
        return False, "the take-off is not there"
    if bool(row.voided):
        return True, None
    if lines_in_use(conn, record_id):
        return False, IN_USE_COMPENSATE
    return True, None


def _retract_links(uow: UnitOfWork, base: dict[str, Any], ids: list[str], reason: str) -> None:
    conn = uow.conn()
    link_ids: list[str] = []
    for start in range(0, len(ids), 500):
        link_ids.extend(
            str(r.link_id) for r in conn.execute(_MODULE_LINKS, {"ids": ids[start : start + 500]})
        )
    for link_id in link_ids:
        retract = RetractLink(**base, link_id=link_id, reason=reason)
        handle_retract_link(uow, retract, by_module=True)


def compensate_mto(uow: UnitOfWork, base: dict[str, Any], mto_id: str, reason: str) -> None:
    """Void the lines, then the take-off, and retract the links the publication wrote.

    Raises ``MtoLineInUseError`` (nothing written) when a line has a reservation or an issue.
    """
    conn = uow.conn()
    if bool(conn.execute(_VOIDED, {"id": mto_id}).scalar_one()):
        return
    if lines_in_use(conn, mto_id):
        raise MtoLineInUseError(IN_USE_COMPENSATE)
    envelope = Command(**base)
    line_ids = [str(r.id) for r in conn.execute(_LIVE_LINES, {"mto": mto_id, "no": False})]
    _retract_links(uow, base, [mto_id, *line_ids], reason)
    voided = [NewEvent(event_type="Record.Voided", payload={"reason": reason})]
    for line_id in line_ids:
        append(uow, envelope, line_id, MTO_LINE, voided)
    append(uow, envelope, mto_id, MTO, voided)


# --- AssignMtoLines ----------------------------------------------------------------------------


@dataclass(frozen=True)
class _Line:
    id: str
    key: str
    work_package_id: str | None


def handle_assign_mto_lines(uow: UnitOfWork, cmd: AssignMtoLines) -> CommandResult:
    """One ``MTOLine.Assigned`` per line that is not on the work package already, all or nothing."""
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    if len(set(cmd.mto_lines)) != len(cmd.mto_lines):
        raise InvalidValueError("mto_lines names a line twice")
    wp_id = work_package_id(conn, cmd.scope, cmd.work_package_number)
    lines: list[_Line] = []
    for i, key in enumerate(cmd.mto_lines):
        row = conn.execute(_LINE_BY_KEY, {"scope": cmd.scope, "key": key, "no": False}).first()
        if row is None or confidentiality.is_hidden(conn, str(row.id)):
            raise MtoLineNotFoundError(f"mto_lines[{i}]: there is no such take-off line")
        if dec(row.reserved_qty) > ZERO or dec(row.issued_qty) > ZERO:
            raise MtoLineInUseError(f"mto_lines[{i}]: {IN_USE_ASSIGN}")
        lines.append(
            _Line(
                str(row.id),
                str(row.key),
                None if row.work_package_id is None else str(row.work_package_id),
            )
        )
    todo = [line for line in lines if line.work_package_id != wp_id]
    if not todo:
        raise NoChangesError("every line is on the work package already")
    events = []
    version = 0
    for line in todo:
        done = append(
            uow,
            cmd,
            line.id,
            MTO_LINE,
            [NewEvent(event_type=MTO_LINE_ASSIGNED, payload={"work_package_id": wp_id})],
        )
        events.extend(done.events)
        version = done.new_version
        if line.work_package_id is not None:
            for old in conn.execute(
                _OLD_WP_LINK, {"line": line.id, "wp": line.work_package_id, "rel": BELONGS_TO}
            ).all():
                handle_retract_link(
                    uow,
                    RetractLink(
                        actor=cmd.actor,
                        source=cmd.source,
                        scope=cmd.scope,
                        correlation_id=cmd.correlation_id,
                        causation_id=cmd.causation_id,
                        link_id=str(old.link_id),
                        reason="assigned to another work package",
                    ),
                    by_module=True,
                )
        handle_add_link(
            uow,
            AddLink(
                actor=cmd.actor,
                source=cmd.source,
                scope=cmd.scope,
                correlation_id=cmd.correlation_id,
                causation_id=cmd.causation_id,
                from_id=line.id,
                to_id=wp_id,
                relation=BELONGS_TO,
                link_source="rule",
            ),
            by_module=True,
        )
    first = todo[0]
    return CommandResult(stream_id=first.id, key=first.key, version=version, events=events)
