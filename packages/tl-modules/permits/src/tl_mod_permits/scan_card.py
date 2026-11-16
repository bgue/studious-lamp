"""The scan card of a permit (P2-PTW T09; the contract is ``tl_core.qr.types``).

A pure read under the viewer, as the awp IWP card reads (P2-QR T04): the card is built inside
``confidentiality.use_viewer``, the hidden test comes first, then one scope and key lookup, then
``views.permit_detail`` (which applies the viewer filter itself). The shown state is the view's
(Lapsed in place of Active); the card never recomputes it and reads no clock beyond ``now``. It
never writes, never raises for a bad id, and answers ``None`` for a record the viewer cannot read,
a voided record, a record of another type and an id that is not a record.
"""

from __future__ import annotations

from datetime import UTC, datetime

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

from tl_mod_permits import views
from tl_mod_permits.names import (
    APPROVED,
    CANCELLED,
    CLOSED,
    HANDED_BACK,
    PERMIT,
    REJECTED,
    REQUESTED,
    SUSPENDED,
    VIEW,
)

_LOOKUP = text(
    "SELECT scope, key FROM cur_core_record WHERE id = :id AND type = :t AND voided = :no"
)
#: The states whose validity date is shown on the card.
_DATED_STATES: tuple[str, ...] = ("Active", "Lapsed", "Suspended")
#: The states that show their name in capitals, neutral.
_NEUTRAL_STATES: tuple[str, ...] = (CLOSED, REJECTED, CANCELLED)


def _cut(value: str, limit: int) -> str:
    return value[:limit]


def _banner(row: views.PermitRow, now: datetime) -> tuple[str, Tone]:
    """The banner and tone of a shown state. A safety card fails to the stop side."""
    state = row.state
    if state == "Active":
        if row.valid_until is None:
            return "ACTIVE", "go"
        until = row.valid_until.astimezone(UTC).strftime("%H:%M")
        return f"ACTIVE until {until} UTC", "go"
    if state == "Lapsed":
        return "LAPSED - revalidate", "stop"
    if state == SUSPENDED:
        return "SUSPENDED", "stop"
    if state == APPROVED:
        return "APPROVED - not issued", "caution"
    if state == REQUESTED:
        return "REQUESTED - not approved", "caution"
    if state == HANDED_BACK:
        return "HANDED BACK", "neutral"
    if state in _NEUTRAL_STATES:
        return state.upper(), "neutral"
    return "NOT VALID", "stop"


def _type_word(permit_type: str) -> str:
    """``hot_work`` reads as ``Hot work``."""
    return permit_type.replace("_", " ").capitalize()


def _lines(detail: views.PermitDetail) -> list[ScanLine]:
    """Label and value pairs; a missing value is left out, never shown as ``None``."""
    row = detail.row
    pairs: list[tuple[str, str | None]] = [
        ("Type", _type_word(row.permit_type) if row.permit_type else None),
        ("Area", row.area),
        ("Holder", row.holder),
        ("Location", detail.location_text),
        ("For", row.for_key),
        ("Revalidated", f"{row.revalidation_count} times" if row.revalidation_count > 0 else None),
    ]
    return [
        ScanLine(label=label, value=_cut(value, MAX_VALUE_CHARS)) for label, value in pairs if value
    ]


def _card(detail: views.PermitDetail, now: datetime) -> ScanCard:
    row = detail.row
    banner, tone = _banner(row, now)
    return ScanCard(
        record_type=PERMIT,
        key=row.key,
        title=_cut(row.subject, MAX_TITLE_CHARS),
        banner=_cut(banner, MAX_BANNER_CHARS),
        tone=tone,
        as_of=now,
        valid_until=row.valid_until if row.state in _DATED_STATES else None,
        lines=_lines(detail),
        open_path=None,
    )


class PermitScanCard:
    """The scan card provider of ``permits.Permit``."""

    record_type = PERMIT
    view_word = VIEW

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
            found = conn.execute(_LOOKUP, {"id": record_id, "t": PERMIT, "no": False}).first()
            if found is None:
                return None
            detail = views.permit_detail(
                conn, str(found.scope), str(found.key), now=now, viewer=viewer
            )
            if detail is None:
                return None
        return _card(detail, now)


def provider() -> ScanCardProvider:
    """The entry point ``throughline.scan_cards`` names for ``permits.Permit``."""
    return PermitScanCard()
