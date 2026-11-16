"""The scan card of an IWP (P2-QR T04; the contract is ``tl_core.qr.types``).

A pure read under the viewer: the card is built inside ``confidentiality.use_viewer``, the hidden
test comes first, then one scope and key lookup, then ``iwp_detail`` (which applies the viewer
filter itself) and ``readiness_of``. It never writes, never raises for a bad id, and answers
``None`` for a record the viewer cannot read, a voided record, a record of another type and an id
that is not a record.
"""

from __future__ import annotations

from datetime import datetime

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

from tl_mod_awp.iwp_views import IwpDetail, iwp_detail
from tl_mod_awp.names import (
    IWP,
    IWP_CANCELLED,
    IWP_CLOSED,
    IWP_FIELD_COMPLETE,
    IWP_IN_PROGRESS,
    IWP_ISSUED,
    IWP_ON_HOLD,
    IWP_SPLIT_STATE,
)
from tl_mod_awp.readiness.views import ReadinessView, readiness_of

#: The access word the viewer needs to read an IWP (``schema/settings/access-words.yaml``).
VIEW_WORD = "awp.view"

_LOOKUP = text(
    "SELECT scope, key FROM cur_core_record WHERE id = :id AND type = :type AND voided = :voided"
)
#: The states that show ISSUED, go.
_GO_STATES: tuple[str, ...] = (IWP_ISSUED, IWP_IN_PROGRESS)
#: The states that show their name in capitals, neutral.
_NEUTRAL_STATES: tuple[str, ...] = (IWP_CLOSED, IWP_FIELD_COMPLETE, IWP_CANCELLED, IWP_SPLIT_STATE)


def _cut(value: str, limit: int) -> str:
    return value[:limit]


def _checks(evaluation: ReadinessView) -> tuple[int, int]:
    """(checks in state ok, checks not n_a)."""
    states = [check.state for check in evaluation.checks]
    ok = sum(1 for state in states if state == "ok")
    counted = sum(1 for state in states if state != "n_a")
    return ok, counted


def _banner(state: str, evaluation: ReadinessView | None) -> tuple[str, Tone]:
    if state in _GO_STATES:
        return "ISSUED", "go"
    if state == IWP_ON_HOLD:
        return "ON HOLD", "stop"
    if state in _NEUTRAL_STATES:
        return state.upper(), "neutral"
    if evaluation is not None:
        ok, counted = _checks(evaluation)
        tone: Tone = "go" if counted > 0 and ok == counted else "caution"
        return f"READY {ok}/{counted}", tone
    return state.upper(), "neutral"


def _lines(detail: IwpDetail, evaluation: ReadinessView | None) -> list[ScanLine]:
    """Label and value pairs; a missing value is left out, never shown as ``None``."""
    lines: list[ScanLine] = []
    if detail.foreman:
        lines.append(ScanLine(label="Foreman", value=_cut(detail.foreman, MAX_VALUE_CHARS)))
    window = " to ".join(v for v in (detail.planned_start, detail.planned_finish) if v)
    if window:
        lines.append(ScanLine(label="Window", value=_cut(window, MAX_VALUE_CHARS)))
    if evaluation is not None:
        ok, counted = _checks(evaluation)
        lines.append(ScanLine(label="Readiness", value=f"{ok}/{counted} checks ok"))
    lines.append(ScanLine(label="Open constraints", value=str(detail.open_constraints)))
    lines.append(ScanLine(label="Scope", value=f"{detail.scope_count} items"))
    if detail.cwp_number:
        lines.append(ScanLine(label="CWP", value=_cut(detail.cwp_number, MAX_VALUE_CHARS)))
    return lines


def _card(detail: IwpDetail, evaluation: ReadinessView | None, now: datetime) -> ScanCard:
    banner, tone = _banner(detail.state, evaluation)
    return ScanCard(
        record_type=IWP,
        key=detail.number,
        title=_cut(detail.title, MAX_TITLE_CHARS),
        banner=_cut(banner, MAX_BANNER_CHARS),
        tone=tone,
        as_of=now,
        valid_until=None,
        lines=_lines(detail, evaluation),
        open_path=None,
    )


class IwpScanCard:
    """The scan card provider of ``awp.IWP``."""

    record_type = IWP
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
            found = conn.execute(_LOOKUP, {"id": record_id, "type": IWP, "voided": False}).first()
            if found is None:
                return None
            detail = iwp_detail(conn, str(found.scope), str(found.key))
            if detail is None:
                return None
            evaluation = readiness_of(conn, record_id)
        return _card(detail, evaluation, now)


def provider() -> ScanCardProvider:
    """The entry point ``throughline.scan_cards`` names for ``awp.IWP``."""
    return IwpScanCard()
