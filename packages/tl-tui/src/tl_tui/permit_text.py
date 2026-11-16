"""The text of the permit register and of one permit's screen, as pure functions (P2-PTW-T11; spec
§8, skill ``tui-layout``).

The values come from ``tl_mod_permits.views`` (``PermitRow``, ``PermitDetail``) and
``iso_views`` (``GasRow``) and nothing else: no client call, no I/O, and no ``textual`` import. The
permit's record id is carried for commands and never printed here. Reading values of a gas test
(O2, LEL, H2S, CO) are not shown; the CLI shows them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from tl_mod_permits.names import ACTIVE, HANDED_BACK, LAPSED, REQUESTED, SUSPENDED
from tl_mod_permits.views import SHOWN_STATES

from tl_tui.details import DetailRow, rows_page
from tl_tui.display import Labels, actor_label, humanize
from tl_tui.layout import EMPTY, Page, Section, identity_line, join_facts, state_line

if TYPE_CHECKING:
    from tl_mod_permits.iso_views import GasRow
    from tl_mod_permits.views import PermitDetail, PermitRow

PERMIT_COLUMNS = ("Number", "Subject", "State", "Type", "Area", "Holder", "Valid until", "For")
PERMIT_DROP = ("For", "Holder", "Area")  # dropped first at narrow width
PERMIT_RIGHT: tuple[str, ...] = ()

#: The states a permit is not valid for work in: a stop, said in words on the line.
STOP_TEXT: Final[Mapping[str, str]] = {LAPSED: "STOP, revalidate", SUSPENDED: "STOP"}
#: The states each permit command is offered in on the permit's screen, as the docstrings of
#: ``tl_mod_permits.commands`` state them (a test pins this table against them). Issue, cancel and
#: request are on the CLI and are not here.
ACTIONS: Final[Mapping[str, tuple[str, ...]]] = {
    "ApprovePermit": (REQUESTED,),
    "RejectPermit": (REQUESTED,),
    "SuspendPermit": (ACTIVE, LAPSED),
    "ResumePermit": (SUSPENDED,),
    "RevalidatePermit": (ACTIVE, LAPSED),
    "HandBackPermit": (ACTIVE, LAPSED, SUSPENDED),
    "ClosePermit": (HANDED_BACK,),
}

NOUN = "permit"
WHERE = "Where"
WORK = "Work"
APPROVALS = "Approvals"
GAS_TESTS = "Gas tests"
HISTORY = "History"
NO_GAS_TESTS = "none taken"
GAS_LINES = 5  # the newest gas tests on the page


def _labels(labels: Labels | None) -> Labels:
    return Labels() if labels is None else labels


def _val(value: object) -> str:
    """The value as a reader sees it: ``—`` for none and for an empty text."""
    if value is None:
        return EMPTY
    text = str(value)
    return text if text.strip() else EMPTY


def _who(labels: Labels, actor: str | None, technical: bool) -> str:
    """A person by name; the actor's id in technical mode; ``—`` for none."""
    if not actor:
        return EMPTY
    return actor if technical else actor_label(labels, actor)


def _holder(labels: Labels, holder: str | None) -> str:
    """The holder as stored: a name stays as it is, an actor reads by its name."""
    return EMPTY if not holder else actor_label(labels, holder)


def _utc(value: datetime) -> datetime:
    """An aware moment in UTC (a naive one is taken as UTC)."""
    return (value if value.tzinfo is not None else value.replace(tzinfo=UTC)).astimezone(UTC)


def _clock(value: datetime) -> str:
    """``18:00 UTC``."""
    return _utc(value).strftime("%H:%M UTC")


def permit_count(total: int) -> str:
    """``1 permit``, ``8 permits``."""
    return f"{total} {NOUN}" if total == 1 else f"{total} {NOUN}s"


def permit_cells(row: PermitRow, labels: Labels | None = None) -> tuple[str, ...]:
    """The eight cells of a register row, in the order of ``PERMIT_COLUMNS``. The state and the
    type are humanized (``Hot work``), the holder is a name when it is an actor, ``Valid until``
    is ``YYYY-MM-DD HH:MM UTC`` or ``-`` when there is none."""
    until = "-" if row.valid_until is None else _utc(row.valid_until).strftime("%Y-%m-%d %H:%M UTC")
    return (
        row.key,
        _val(row.subject),
        humanize(row.state),
        humanize(row.permit_type),
        _val(row.area),
        _holder(_labels(labels), row.holder),
        until,
        _val(row.for_key),
    )


def _tally(rows: Iterable[PermitRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.state] = counts.get(row.state, 0) + 1
    return counts


def permit_summary(
    rows: Iterable[PermitRow],
    total: int,
    shown: int,
    *,
    state: str | None = None,
    permit_type: str | None = None,
) -> str:
    """``8 permits: 1 Active, 1 Lapsed (STOP), 1 Suspended (STOP), ...``; with a filter
    ``2 of 8 permits, state Active, type hot work``. The counts are the rows the log holds;
    ``total`` is the page total."""
    if state is None and permit_type is None:
        if total == 0:
            return permit_count(0)
        counts = _tally(rows)
        parts = []
        for name in SHOWN_STATES:
            label = humanize(name) + (" (STOP)" if name in STOP_TEXT else "")
            parts.append(f"{counts.get(name, 0)} {label}")
        return f"{permit_count(total)}: {', '.join(parts)}"
    named: list[str] = []
    if state is not None:
        named.append(f"state {humanize(state)}")
    if permit_type is not None:
        named.append(f"type {humanize(permit_type).lower()}")
    return ", ".join([f"{shown} of {permit_count(total)}", *named])


def _state_line(row: PermitRow) -> str:
    """``Active · hot work · until 18:00 UTC``; ``Lapsed · STOP, revalidate``;
    ``Suspended · STOP``; any other state with its type."""
    kind = humanize(row.permit_type).lower()
    if row.state in STOP_TEXT:
        return join_facts(humanize(row.state), STOP_TEXT[row.state])
    if row.state == ACTIVE:
        until = None if row.valid_until is None else f"until {_clock(row.valid_until)}"
        return join_facts(humanize(row.state), kind, until)
    return join_facts(humanize(row.state), kind)


def _gas_lines(labels: Labels, gas_tests: Sequence[GasRow], technical: bool) -> list[str]:
    """The newest gas tests, ``Pass 14:05 UTC by Uma``; no reading values."""
    newest = sorted(gas_tests, key=lambda gas: gas.taken_at, reverse=True)[:GAS_LINES]
    return [
        f"{humanize(gas.result)} {_clock(gas.taken_at)} by {_who(labels, gas.tester, technical)}"
        for gas in newest
    ]


def _times(count: int) -> str:
    return f"{count} time" if count == 1 else f"{count} times"


def permit_page(
    detail: PermitDetail,
    gas_tests: Sequence[GasRow],
    labels: Labels | None = None,
    technical: bool = False,
    panel: bool = False,
) -> Page:
    """The permit as a page: the identity ``<key> · <subject>``, the state line (``Active · hot
    work · until 18:00 UTC``, ``Lapsed · STOP, revalidate``), a panel's summary line, then the
    sections Where (area, location, for key), Work (holder, description), Approvals (requested by,
    approved by, issued by, ticked precautions), Gas tests (newest first, at most five, no reading
    values) and History (revalidated, suspend, handback, reject and cancel reasons)."""
    lab = _labels(labels)
    row = detail.row
    rows: list[DetailRow] = [
        DetailRow("Area", _val(row.area), section=WHERE),
        DetailRow("Location", _val(detail.location_text), section=WHERE),
        DetailRow("For", _val(row.for_key), section=WHERE),
        DetailRow("Holder", _holder(lab, row.holder), section=WORK),
        DetailRow("Description", _val(detail.description), section=WORK),
        DetailRow("Requested by", _who(lab, detail.requested_by, technical), section=APPROVALS),
        DetailRow("Approved by", _who(lab, detail.approved_by, technical), section=APPROVALS),
        DetailRow("Issued by", _who(lab, detail.issued_by, technical), section=APPROVALS),
        DetailRow("Precautions", f"{len(detail.precautions)} ticked", section=APPROVALS),
        DetailRow("Revalidated", _times(row.revalidation_count), section=HISTORY),
        DetailRow("Suspend reason", _val(detail.suspend_reason), section=HISTORY),
        DetailRow("Handback note", _val(detail.handback_note), section=HISTORY),
        DetailRow("Reject reason", _val(detail.reject_reason), section=HISTORY),
        DetailRow("Cancel reason", _val(detail.cancel_reason), section=HISTORY),
        DetailRow("Version", str(detail.version), technical=True, section=HISTORY),
    ]
    summary = join_facts(_holder(lab, row.holder), row.area, row.for_key)
    page = rows_page(
        rows,
        identity=identity_line(row.key, row.subject),
        state=state_line(_state_line(row)),
        summary=summary,
        technical=technical,
        panel=panel,
    )
    gas = Section(GAS_TESTS, tuple(_gas_lines(lab, gas_tests, technical)), note=NO_GAS_TESTS)
    sections = list(page.sections)
    at = next((i for i, s in enumerate(sections) if s.heading == HISTORY), len(sections))
    sections.insert(at, gas)
    return Page(page.identity, page.state, tuple(sections), page.summary)
