"""The Commercial register as pending and approved changes for the cost system (brief 9, M10 / M11).

"The register exports to the cost system as pending/approved changes." One row per Commercial
item that has been given to the other party:

* **approved**: the other party agreed it or partly agreed it; the value is the assessed value;
* **pending**: issued and awaiting assessment, disputed, or escalated; the value is the estimate.

An item that is not issued yet (Draft, Commercial review, PM approval), a void item and a closed
item that was never assessed are not changes and are not exported. The cost codes are listed in
one cell, ``code=amount`` separated by semicolons, so that a sum over the file counts each notice
once. Amounts are exact decimal texts.

**This is a bulk export (brief 18.10, ADR-0016).** Only the classes the caller names are written
(default ``internal``, which is none of the Commercial items, as they are ``restricted``: a
controller says ``restricted``). Naming ``restricted`` needs a document controller or admin viewer
(``ForbiddenError`` otherwise); ``privileged`` is never exported. Whatever is named, the caller
gets only what their viewer may read, and the count of items left out for their class is of items
they could read. A cell that a spreadsheet would run as a formula is written with a leading quote:
a subject and a cost code are somebody else's text.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Final

from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.auth.errors import ForbiddenError

from tl_mod_correspondence import registry, registry_domain, views
from tl_mod_correspondence.errors import ExportClassError
from tl_mod_correspondence.handlers.common import today as module_today
from tl_mod_correspondence.names import (
    ST_AWAITING_ASSESSMENT,
    ST_DISPUTED,
    ST_ESCALATED,
    ST_ISSUED,
)

COLUMNS: Final = (
    "number",
    "kind",
    "title",
    "cost_status",
    "state",
    "currency",
    "value",
    "value_basis",
    "hours",
    "schedule_impact_days",
    "cost_codes",
    "clause",
    "aware_on",
    "issued_on",
    "time_bar_due",
    "time_bar_late",
    "source_rfi",
    "class",
)
EXPORTABLE_CLASSES: Final = ("internal", "restricted")
_FORMULA_STARTS: Final = ("=", "+", "-", "@", "|", "\t", "\r")
_NUMBER: Final = re.compile(r"-?[0-9]+(\.[0-9]+)?")
_PENDING_STATES: Final = (ST_ISSUED, ST_AWAITING_ASSESSMENT, ST_DISPUTED, ST_ESCALATED)


@dataclass
class ExportResult:
    """The rows (in ``COLUMNS`` order) and how many items of each class the export left out
    because the caller did not name the class."""

    rows: list[list[str]]
    left_out: dict[str, int] = field(default_factory=dict)


def safe_cell(value: str | None) -> str:
    """``value`` as a spreadsheet cell: a text that starts like a formula gets a leading quote.
    A plain number is left as it is (``-3`` is a number, not a formula)."""
    text = "" if value is None else value
    if _NUMBER.fullmatch(text):
        return text
    return "'" + text if text.startswith(_FORMULA_STARTS) else text


def _cost_status(state: str, assessment: str | None) -> str | None:
    """``approved``, ``pending`` or ``None`` (not a change the cost system should hear of)."""
    if assessment in ("agreed", "partially_agreed"):
        return "approved"
    if assessment == "disputed" or state in _PENDING_STATES:
        return "pending"
    return None


def _check_classes(classes: Sequence[str]) -> tuple[str, ...]:
    named = tuple(dict.fromkeys(classes))
    if "privileged" in named:
        raise ExportClassError("privileged items are never exported")
    unknown = [c for c in named if c not in EXPORTABLE_CLASSES]
    if unknown:
        raise ExportClassError(
            f"unknown class {unknown[0]!r}; an export may name {', '.join(EXPORTABLE_CLASSES)}"
        )
    if "restricted" in named and confidentiality.current_viewer().level < 1:
        raise ForbiddenError(
            "exporting restricted items needs the document_controller or admin role"
        )
    return named


def commercial_export(
    conn: Connection,
    scope: str,
    *,
    classes: Sequence[str] = ("internal",),
    today: str | None = None,
) -> ExportResult:
    """The pending and approved changes of ``scope`` for the classes named.

    Raises ``ExportClassError`` (``privileged``, or a class that is none) and ``ForbiddenError``
    (``restricted`` for a viewer below a document controller).
    """
    named = _check_classes(classes)
    day = date.fromisoformat(today or module_today())
    rows: list[list[str]] = []
    left_out: dict[str, int] = {}
    for row in registry_domain.list_commercial(conn, scope, limit=5000):
        item, data = row.item, row.data
        status = _cost_status(item.state, data.assessment_status)
        if status is None:
            continue
        if item.confidentiality not in named:
            left_out[item.confidentiality] = left_out.get(item.confidentiality, 0) + 1
            continue
        approved = status == "approved"
        value = data.assessed_value if approved else data.estimated_value
        bar = next(
            (
                views.clock_view(conn, c, day)
                for c in registry.clocks_of(conn, item.id)
                if c.kind == "time_bar"
            ),
            None,
        )
        clause = (
            registry.get_clause(conn, data.contract_clause_id) if data.contract_clause_id else None
        )
        source = registry.get_item(conn, data.derived_from_id) if data.derived_from_id else None
        codes = ";".join(
            f"{i['cost_code']}={i['amount']}" if i.get("amount") else str(i["cost_code"])
            for i in data.cost_code_impacts
        )
        late = bar is not None and (
            bar.effective_state == "expired"
            or (bar.state == "met" and bar.closed_on is not None and bar.closed_on > bar.due_on)
        )
        cells = [
            item.number,
            item.subtype or "",
            item.subject,
            status,
            item.state,
            data.currency or "",
            value or "",
            "assessed" if approved else "estimated",
            data.estimated_hours or "",
            "" if data.schedule_impact_days is None else str(data.schedule_impact_days),
            codes,
            f"{clause.contract}/{clause.clause_number}" if clause else "",
            data.aware_on or "",
            item.issued_on or "",
            bar.due_on if bar else "",
            "yes" if late else "no",
            source.number if source else "",
            item.confidentiality,
        ]
        rows.append([safe_cell(cell) for cell in cells])
    return ExportResult(rows=rows, left_out=left_out)


def csv_text(result: ExportResult) -> str:
    """The export as CSV text: the header, then one line per row; ``\\n`` line ends."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerows(result.rows)
    return buffer.getvalue()
