"""The scan card of an inspection (P2-INSP T09; the contract is ``tl_core.qr.types``).

A pure read under the viewer, built as the awp card is: inside ``confidentiality.use_viewer`` the
hidden test comes first, then one scope and key lookup, then ``inspection_detail`` (which applies
the viewer filter itself). It never writes, never raises for a bad id, and answers ``None`` for a
record the viewer cannot read, a voided record, a record of another type and an id that is not a
record.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.qr.types import (
    MAX_BANNER_CHARS,
    MAX_TITLE_CHARS,
    MAX_VALUE_CHARS,
    ScanCard,
    ScanCardProvider,
    ScanLine,
    Tone,
)

from tl_mod_quality.form_source import source as form_source
from tl_mod_quality.insp_views import InspectionDetail, inspection_detail
from tl_mod_quality.names import (
    CANCELLED,
    DONE,
    INSPECTION,
    PLANNED,
    SCHEDULED,
    VERIFIED,
)

#: The access word the viewer needs to read an inspection (``schema/settings/access-words.yaml``).
VIEW_WORD = "quality.view"

#: The point that holds work until it is released (``names.POINTS``).
HOLD = "hold"
#: The results an inspection records (``names.OUTCOMES``).
ACCEPT = "accept"
REJECT = "reject"
CONDITIONAL = "conditional"

_LOOKUP = text(
    "SELECT scope, key FROM cur_core_record WHERE id = :id AND type = :type AND voided = :no"
)
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _cut(value: str, limit: int) -> str:
    return value[:limit]


def _day(value: str | None) -> str | None:
    """``18 Nov`` for ``2026-11-18``; ``None`` when unset or not an ISO date."""
    if not value:
        return None
    try:
        when = date.fromisoformat(value[:10])
    except ValueError:
        return None
    return f"{when.day} {_MONTHS[when.month - 1]}"


def _banner(detail: InspectionDetail) -> tuple[str, Tone]:
    row = detail.row
    if row.state == CANCELLED:
        return "CANCELLED", "neutral"
    if row.state in (PLANNED, SCHEDULED) and row.point == HOLD:
        return "HOLD POINT - not released", "stop"
    if row.state == SCHEDULED:
        day = _day(row.scheduled_for)
        return (f"SCHEDULED {day}" if day else "SCHEDULED"), "neutral"
    if row.state == PLANNED:
        return "PLANNED", "neutral"
    if row.state == DONE:
        if row.result == ACCEPT:
            return "DONE - to verify", "caution"
        if row.result == REJECT:
            return "REJECTED", "stop"
        if row.result == CONDITIONAL:
            return "CONDITIONAL", "caution"
    if row.state == VERIFIED:
        if row.result == ACCEPT:
            return "ACCEPTED", "go"
        if row.result == REJECT:
            return "REJECTED", "stop"
        if row.result == CONDITIONAL:
            return "CONDITIONAL", "caution"
    return row.state.upper(), "neutral"


def _checklist(detail: InspectionDetail) -> str | None:
    key = detail.checklist_key
    if not key:
        return None
    if detail.checklist_version is None:
        return key
    return f"{key} v{detail.checklist_version}"


def _lines(detail: InspectionDetail) -> list[ScanLine]:
    """Label and value pairs; a missing value is left out, never shown as ``None``."""
    row = detail.row
    pairs: list[tuple[str, str | None]] = [
        ("Point", row.point),
        ("Checklist", _checklist(detail)),
        ("Inspector", row.inspector),
        ("Area", row.area),
        ("For", row.for_key),
        ("Subject", row.subject_key),
        ("Punch items", str(row.punch_count) if row.punch_count > 0 else None),
    ]
    return [
        ScanLine(label=label, value=_cut(value, MAX_VALUE_CHARS)) for label, value in pairs if value
    ]


def _open_path(open_form: bool, project: str, key: str) -> str | None:
    """The page that fills the inspection's form, when the record has an open binding."""
    return f"/web/forms/for/{key}?project={project}" if open_form else None


def _card(detail: InspectionDetail, now: datetime, open_path: str | None) -> ScanCard:
    banner, tone = _banner(detail)
    row = detail.row
    return ScanCard(
        record_type=INSPECTION,
        key=row.key,
        title=_cut(row.title, MAX_TITLE_CHARS),
        banner=_cut(banner, MAX_BANNER_CHARS),
        tone=tone,
        as_of=now,
        valid_until=None,
        lines=_lines(detail),
        open_path=open_path,
    )


class InspectionScanCard:
    """The scan card provider of ``quality.Inspection``."""

    record_type = INSPECTION
    view_word = VIEW_WORD

    def card(
        self,
        conn: Connection,
        record_id: str,
        viewer: confidentiality.Viewer,
        now: datetime,
    ) -> ScanCard | None:
        with confidentiality.use_viewer(viewer):
            if confidentiality.is_hidden(conn, record_id, viewer):
                return None
            found = conn.execute(
                _LOOKUP, {"id": record_id, "type": INSPECTION, "no": False}
            ).first()
            if found is None:
                return None
            detail = inspection_detail(conn, str(found.scope), str(found.key), viewer=viewer)
            binding = form_source().binding(conn, record_id, viewer, now)
        if detail is None:
            return None
        project = str(found.scope).removeprefix("project:")
        opens = binding is not None and binding.available and str(found.scope) != project
        return _card(detail, now, _open_path(opens, project, detail.row.key))


def provider() -> ScanCardProvider:
    """The entry point ``throughline.scan_cards`` names for ``quality.Inspection``."""
    return InspectionScanCard()
