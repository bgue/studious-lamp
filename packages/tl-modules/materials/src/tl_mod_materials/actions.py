"""Which commands the viewer may run on a record now (m4-materials.md section 6; P1-UX2).

``RULES`` is the one table: a line of section 6 per command, with the state or condition the
record must be in, the label a screen shows and the access word of the command. ``offers`` reads
the record's own rows and the caller's ``holds``; it writes nothing. A rule is offered when its
condition holds for the record, the caller holds the table word of its access word, and the
command is in ``MATERIALS_COMMANDS``. An agent is offered nothing: ``tl_core.actions`` answers
that before any hook runs.

A test holds every rule's word equal to the ``access`` of its command. An offer is advice; the
handler still checks state, quantities and the word when the command runs.

The ``MTO_RULES`` of ``mto.py`` (S4) are accepted by shape: any row with the five attributes of
``rules.Rule`` (``record_type`` or ``type``, ``condition``, ``label``, ``command``, ``word``).
A row repeating a command already offered on the record is dropped.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import Connection, text
from tl_core.actions import ActionOffer, Holds, Level
from tl_core.auth.access_words import table_word
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of

from tl_mod_materials.commands import MATERIALS_COMMANDS
from tl_mod_materials.common import ZERO, dec
from tl_mod_materials.mto import MTO_RULES
from tl_mod_materials.names import (
    ITEM_MASTER,
    ITEM_MASTER_TABLE,
    LOCATION,
    LOCATION_TABLE,
    LOT_TABLE,
    MTO_LINE,
    MTO_LINE_TABLE,
    PROJECT_ITEM_TABLE,
    RECEIPT,
    RECEIPT_LINE_TABLE,
    RESERVATION_TABLE,
    STOCK_LOT,
    STOCK_TABLE,
)
from tl_mod_materials.rules import Rule

RULES: tuple[Rule, ...] = (
    # a receipt
    Rule(RECEIPT, "Received", "Edit", "ReviseReceipt", "materials.receive"),
    Rule(RECEIPT, "Received", "Inspect", "InspectReceipt", "materials.receive"),
    Rule(RECEIPT, "Received", "Reject", "RejectReceipt", "materials.receipt.decide"),
    Rule(
        RECEIPT,
        "Inspected, MTR present or not required",
        "Accept",
        "AcceptReceipt",
        "materials.receipt.decide",
    ),
    Rule(RECEIPT, "Inspected", "Reject", "RejectReceipt", "materials.receipt.decide"),
    Rule(RECEIPT, "Received, Inspected", "Void", "VoidReceipt", "materials.void"),
    # a stock lot
    Rule(STOCK_LOT, "available > 0 at some location", "Issue", "IssueStock", "materials.move"),
    Rule(
        STOCK_LOT, "available > 0 at some location", "Transfer", "TransferStock", "materials.move"
    ),
    Rule(
        STOCK_LOT, "available > 0 at some location", "Reserve", "ReserveStock", "materials.reserve"
    ),
    Rule(STOCK_LOT, "issued_net > 0", "Return", "ReturnStock", "materials.move"),
    Rule(STOCK_LOT, "has a reservation", "Unreserve", "UnreserveStock", "materials.reserve"),
    Rule(STOCK_LOT, "on hand > 0", "Adjust", "AdjustStock", "materials.adjust"),
    Rule(STOCK_LOT, "on hand > 0", "Scrap", "ScrapStock", "materials.adjust"),
    # a take-off line (the assign row is S4's, in MTO_RULES)
    Rule(MTO_LINE, "short", "Reserve from a lot", "ReserveStock", "materials.reserve"),
    # the library and the location tree
    Rule(ITEM_MASTER, "Active", "Retire", "RetireItem", "materials.library.edit"),
    Rule(ITEM_MASTER, "Active", "Adopt into this project", "AdoptItem", "materials.item.adopt"),
    Rule(LOCATION, "Active", "Edit", "ReviseLocation", "materials.location.configure"),
    Rule(LOCATION, "Active", "Retire", "RetireLocation", "materials.location.configure"),
    *MTO_RULES,
)

#: Condition text -> whether it holds, for one record. Each loader below fills its type's texts.
Facts = dict[str, bool]

_RECORD = text("SELECT type, scope, status, voided FROM cur_core_record WHERE id = :id")
_MTR_COUNT = text(
    "SELECT COUNT(*) FROM cur_files WHERE record_id = :id AND slot = 'mtr' "
    "AND status = 'available' AND superseded_by IS NULL"
)
_CATEGORIES = text(
    "SELECT DISTINCT p.category FROM "
    f"{RECEIPT_LINE_TABLE} l JOIN {PROJECT_ITEM_TABLE} p ON p.id = l.project_item_id "
    "WHERE l.receipt_id = :id"
)
_STOCK_OF = text(f"SELECT on_hand, reserved FROM {STOCK_TABLE} WHERE lot_id = :id")
_LOT_NET = text(f"SELECT issued_net FROM {LOT_TABLE} WHERE id = :id")
_HAS_RESERVATION = text(f"SELECT 1 FROM {RESERVATION_TABLE} WHERE lot_id = :id LIMIT 1")
_LINE = text(f"SELECT qty, reserved_qty, issued_qty FROM {MTO_LINE_TABLE} WHERE id = :id")
_ITEM_RETIRED = text(f"SELECT retired FROM {ITEM_MASTER_TABLE} WHERE id = :id")
_LOCATION_RETIRED = text(f"SELECT retired FROM {LOCATION_TABLE} WHERE id = :id")


def _mtr_ok(conn: Connection, scope: str, receipt_id: str) -> bool:
    """The MTR is attached, or no line of the receipt is of a category that needs one."""
    listed = value_of(
        conn, "materials.receipt.mtr_required_categories", project=project_of_scope(scope)
    )
    required = (
        {str(c) for c in cast("Iterable[Any]", listed)} if isinstance(listed, list) else set()
    )
    categories = {str(c) for c in conn.execute(_CATEGORIES, {"id": receipt_id}).scalars()}
    if not categories & required:
        return True
    return int(conn.execute(_MTR_COUNT, {"id": receipt_id}).scalar_one()) > 0


def _receipt_facts(conn: Connection, record_id: str, status: str | None, scope: str) -> Facts:
    state = "Received" if status is None else status
    return {
        "Received": state == "Received",
        "Inspected": state == "Inspected",
        "Received, Inspected": state in ("Received", "Inspected"),
        "Inspected, MTR present or not required": state == "Inspected"
        and _mtr_ok(conn, scope, record_id),
    }


def _lot_facts(conn: Connection, record_id: str, status: str | None, scope: str) -> Facts:
    rows = conn.execute(_STOCK_OF, {"id": record_id}).all()
    net = conn.execute(_LOT_NET, {"id": record_id}).scalar_one_or_none()
    return {
        "available > 0 at some location": any(
            dec(r.on_hand) - dec(r.reserved) > ZERO for r in rows
        ),
        "on hand > 0": any(dec(r.on_hand) > ZERO for r in rows),
        "issued_net > 0": net is not None and dec(net) > ZERO,
        "has a reservation": conn.execute(_HAS_RESERVATION, {"id": record_id}).first() is not None,
    }


def _line_facts(conn: Connection, record_id: str, status: str | None, scope: str) -> Facts:
    row = conn.execute(_LINE, {"id": record_id}).first()
    if row is None:
        return {}
    qty, reserved, issued = dec(row.qty), dec(row.reserved_qty), dec(row.issued_qty)
    return {
        "short": reserved + issued < qty,
        "no reservation": reserved == Decimal(0),
    }


def _item_facts(conn: Connection, record_id: str, status: str | None, scope: str) -> Facts:
    retired = conn.execute(_ITEM_RETIRED, {"id": record_id}).scalar_one_or_none()
    return {"Active": retired is not None and not bool(retired)}


def _location_facts(conn: Connection, record_id: str, status: str | None, scope: str) -> Facts:
    retired = conn.execute(_LOCATION_RETIRED, {"id": record_id}).scalar_one_or_none()
    return {"Active": retired is not None and not bool(retired)}


_FACTS: dict[str, Callable[[Connection, str, str | None, str], Facts]] = {
    RECEIPT: _receipt_facts,
    STOCK_LOT: _lot_facts,
    MTO_LINE: _line_facts,
    ITEM_MASTER: _item_facts,
    LOCATION: _location_facts,
}


def _attr(row: object, *names: str) -> str:
    for name in names:
        value = getattr(row, name, None)
        if isinstance(value, str):
            return value
    return ""


def rule_rows() -> list[Rule]:
    """``RULES`` as ``Rule`` rows (``MTO_RULES`` rows are read by shape)."""
    return [
        row
        if isinstance(row, Rule)
        else Rule(
            _attr(row, "record_type", "type"),
            _attr(row, "condition"),
            _attr(row, "label"),
            _attr(row, "command", "command_name"),
            _attr(row, "word"),
        )
        for row in RULES
    ]


def level_of(word: str) -> Level:
    """The role-table word an access word needs, as the level ``holds`` is asked."""
    found = table_word(word)
    if found in ("user", "controller", "admin"):
        return cast("Level", found)
    return "user" if found == "company" else "controller"


def offers_for(
    record_type: str, facts: Facts, holds: Holds, *, commands: Iterable[str] | None = None
) -> list[ActionOffer]:
    """The offers on a record of ``record_type`` whose condition texts hold in ``facts``."""
    known = (
        set(commands) if commands is not None else {c.model.__name__ for c in MATERIALS_COMMANDS}
    )
    seen: set[str] = set()
    found: list[ActionOffer] = []
    for rule in rule_rows():
        if (
            rule.record_type != record_type
            or rule.command in seen
            or rule.command not in known
            or not facts.get(rule.condition, False)
            or not holds(level_of(rule.word))
        ):
            continue
        seen.add(rule.command)
        found.append(ActionOffer(command=rule.command, label=rule.label))
    return found


def offers(conn: Connection, record_id: str, holds: Holds) -> list[ActionOffer]:
    """The commands the viewer may run on this record now (none for a voided record or a type
    this module offers nothing on)."""
    row = conn.execute(_RECORD, {"id": record_id}).first()
    if row is None or bool(row.voided):
        return []
    loader = _FACTS.get(str(row.type))
    if loader is None:
        return []
    facts = loader(conn, record_id, row.status, str(row.scope))
    return offers_for(str(row.type), facts, holds)


def _hook(record_type: str) -> Callable[[Connection, str, Holds], list[ActionOffer]]:
    def actions(conn: Connection, record_id: str, holds: Holds) -> list[ActionOffer]:
        row = conn.execute(_RECORD, {"id": record_id}).first()
        if row is None or bool(row.voided) or str(row.type) != record_type:
            return []
        facts = _FACTS[record_type](conn, record_id, row.status, str(row.scope))
        return offers_for(record_type, facts, holds)

    return actions


receipt_actions = _hook(RECEIPT)
lot_actions = _hook(STOCK_LOT)
mto_line_actions = _hook(MTO_LINE)
item_actions = _hook(ITEM_MASTER)
location_actions = _hook(LOCATION)

__all__ = [
    "RULES",
    "Rule",
    "item_actions",
    "level_of",
    "location_actions",
    "lot_actions",
    "mto_line_actions",
    "offers",
    "offers_for",
    "receipt_actions",
    "rule_rows",
]
