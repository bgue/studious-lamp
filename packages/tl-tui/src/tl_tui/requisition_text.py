"""The text of the requisition log and of a requisition's screen, as pure functions (P2-I4A T07a;
spec §8, skill ``tui-layout``).

The values come from ``tl_mod_requisitions.api`` (``RequisitionRow``, ``WorkOrderRow``) and
``tl_api.routes.requisitions.RequisitionDetailBody`` and nothing else: no client call, no I/O, and
no ``textual`` import, so the web client can use the same words. Dates are formatted by
``tl_tui.awp_text.date_text``. A requisition is named by its key and its subject, never by its id;
the id is shown only in technical mode. The kind is said as a word: ``labour`` for the labour kind
(the record type says ``labor``; a reader never sees that spelling).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tl_tui.awp_text import date_text
from tl_tui.display import Labels, actor_label, humanize
from tl_tui.layout import Page, Section, identity_line, join_facts, prop, shown, state_line

if TYPE_CHECKING:
    from tl_api.routes.requisitions import RequisitionDetailBody
    from tl_mod_requisitions.api import RequisitionRow

REQ_COLUMNS = ("Number", "Subject", "Kind", "State", "Priority", "Need by", "Requester")
REQ_DROP = ("Requester", "Need by", "Priority")  # dropped first at narrow width
REQ_RIGHT = ()

KIND_WORDS = {
    "labor": "labour",
    "material": "material",
    "general": "general",
    "scaffold": "scaffold",
}  # the kind code (the ``kind`` slot value) to the word a reader sees
DETAIL = "Detail"
WORK_ORDER = "Work order"
TECHNICAL = "Technical"
NO_DETAIL = "No details"
NO_WORK_ORDER = "none yet"
NOUN = "requisition"


def _labels(labels: Labels | None) -> Labels:
    return Labels() if labels is None else labels


def kind_word(kind: str) -> str:
    """``labour`` for ``labor``; a kind with no word reads humanized."""
    return KIND_WORDS.get(kind) or humanize(kind)


def req_cells(row: RequisitionRow, labels: Labels | None = None) -> tuple[str, ...]:
    """The seven cells of a log row, in the order of ``REQ_COLUMNS``. The number is the key, the
    kind is a word, the state and priority are humanized, the need-by date is ``date_text`` and
    the requester is a name."""
    return (
        row.key,
        shown(row.subject),
        kind_word(row.kind),
        humanize(row.state),
        humanize(row.priority),
        date_text(row.need_by),
        actor_label(_labels(labels), row.requester),
    )


def req_summary(
    total: int, shown: int, *, kind: str | None = None, state: str | None = None
) -> str:
    """``7 requisitions``; with a filter ``3 of 7 requisitions, state Requested``. ``kind`` is the
    kind code (``labor``), said as its word."""
    count = f"{total} {NOUN}" if total == 1 else f"{total} {NOUN}s"
    if kind is None and state is None:
        return count
    named: list[str] = []
    if kind is not None:
        named.append(f"kind {kind_word(kind)}")
    if state is not None:
        named.append(f"state {humanize(state)}")
    return ", ".join([f"{shown} of {count}", *named])


def req_page(
    detail: RequisitionDetailBody,
    labels: Labels | None = None,
    technical: bool = False,
    panel: bool = False,
) -> Page:
    """The requisition as a page: the identity line (``<key> · <subject>``), the state line, the
    summary line (kind, need by, requester, priority), then the sections Detail (the kind fields
    as ``Label  value`` lines), Work order (``<key> · <state>`` or ``none yet``) and, in technical
    mode only, Technical (the id and the version). The panel and the screen show the same page: a
    requisition is short enough that the panel cuts nothing."""
    row = detail.row
    lab = _labels(labels)
    summary = join_facts(
        kind_word(row.kind),
        f"Need by {row.need_by}" if row.need_by else "",
        actor_label(lab, row.requester),
        humanize(row.priority),
    )
    fields = tuple(prop(humanize(name), shown(value)) for name, value in detail.fields.items())
    work = detail.work_order
    sections = [
        Section(DETAIL, fields, note=NO_DETAIL),
        Section(
            WORK_ORDER,
            () if work is None else (f"{work.key} · {humanize(work.state)}",),
            note=NO_WORK_ORDER,
        ),
    ]
    if technical:
        sections.append(Section(TECHNICAL, (prop("Id", row.id), prop("Version", str(row.version)))))
    return Page(
        identity=identity_line(row.key, row.subject),
        state=state_line(humanize(row.state)),
        summary=summary,
        sections=tuple(sections),
    )
