"""The correspondence module's line-level reports (``tl report``; V3-P0): the RFI log and the
correspondence register.

Both read through the module's own views (``reports_technical.rfi_log``, ``views.register``), which
read as the ambient viewer (``tl_core.report_out`` sets it), so an item the viewer may not read is
not a row. The register pages by 500; the RFI log has no offset, so it is read in one call with a
bound far above any project's count. No internal id is a column; the number names the item.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final

from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.modules import Report

from tl_mod_correspondence import reports_technical, views

_PAGE: Final = 500
_RFI_BOUND: Final = 1_000_000
RFI_COLUMNS: Final = (
    "number", "subtype", "state", "discipline", "raised_on", "issued_on", "required_by",
    "answered_on", "response_days", "on_time", "overdue", "days_overdue",
    "potential_cost_impact", "potential_schedule_impact", "cost_impact", "schedule_impact",
    "review_decision", "class", "subject",
)  # fmt: skip
REGISTER_COLUMNS: Final = (
    "number", "kind", "state", "direction", "domain", "subtype", "date", "counterparty",
    "response_due", "class", "subject",
)  # fmt: skip


def rfi_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    log = reports_technical.rfi_log(conn, scope, limit=_RFI_BOUND)
    for line in log.lines:
        row = line.model_dump()
        row["class"] = row.pop("confidentiality")
        yield row


def register_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    offset = 0
    while True:
        page = views.register(conn, scope, limit=_PAGE, offset=offset)
        for line in page:
            yield {
                "number": line.number,
                "kind": line.kind,
                "state": line.state,
                "direction": line.direction,
                "domain": line.domain,
                "subtype": line.subtype,
                "date": line.on,
                "counterparty": line.counterparty,
                "response_due": line.response_due,
                "class": line.confidentiality,
                "subject": line.subject,
            }
        offset += len(page)
        if len(page) < _PAGE:
            return


REPORTS: Final = (
    Report("rfis", "RFIs, technical queries and deviation requests", RFI_COLUMNS, rfi_rows),
    Report("correspondence", "Correspondence register", REGISTER_COLUMNS, register_rows),
)
