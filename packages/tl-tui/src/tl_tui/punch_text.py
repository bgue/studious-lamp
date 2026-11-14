"""The text of the punch log and of a punch item's screen, as pure functions (P2-PUNCH-T06; spec §8,
skill ``tui-layout``).

The values come from ``tl_mod_quality.views`` (``PunchRow``, ``PunchDetail``) and nothing else: no
client call, no I/O, and no ``textual`` import. Dates are formatted by ``tl_tui.awp_text``
(``date_text``); the item's record id is carried for commands and never printed here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from tl_mod_quality.names import CLEARED, OPEN, VERIFIED, VOID

from tl_tui.awp_text import date_text
from tl_tui.details import DetailRow, rows_page
from tl_tui.display import Labels, actor_label, humanize
from tl_tui.layout import EMPTY, Page, identity_line, join_facts, state_line

if TYPE_CHECKING:
    from tl_mod_quality.views import PunchDetail, PunchRow

PUNCH_COLUMNS = ("Number", "Subject", "State", "Cat", "Area", "System", "Due", "Assignee")
PUNCH_DROP = ("Assignee", "System", "Area")  # dropped first at narrow width
PUNCH_RIGHT: tuple[str, ...] = ()

STATES = (OPEN, CLEARED, VERIFIED, VOID)  # the order the summary names them in
NOUN = "punch item"
WHERE = "Where"
WORK = "Work"
HISTORY = "History"


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


def punch_count(total: int) -> str:
    """``1 punch item``, ``7 punch items``."""
    return f"{total} {NOUN}" if total == 1 else f"{total} {NOUN}s"


def punch_cells(row: PunchRow, labels: Labels | None = None) -> tuple[str, ...]:
    """The eight cells of a log row, in the order of ``PUNCH_COLUMNS``. The state is humanized,
    the due date is ``date_text`` (``—`` for none), the assignee is a name."""
    return (
        row.key,
        _val(row.subject),
        humanize(row.state),
        row.category,
        _val(row.area),
        _val(row.system),
        date_text(row.due_on),
        _who(_labels(labels), row.assignee, technical=False),
    )


def punch_summary(
    counts: Mapping[str, int],
    total: int,
    shown: int,
    *,
    state: str | None = None,
    overdue: bool = False,
) -> str:
    """``7 punch items: 3 Open, 2 Cleared, 1 Verified, 1 Void``; with a filter
    ``2 of 7 punch items, state Open, overdue``. ``overdue`` is named only when it is asked."""
    if state is None and not overdue:
        if total == 0:
            return punch_count(0)
        by_state = ", ".join(f"{counts.get(name, 0)} {name}" for name in STATES)
        return f"{punch_count(total)}: {by_state}"
    named: list[str] = []
    if state is not None:
        named.append(f"state {humanize(state)}")
    if overdue:
        named.append("overdue")
    return ", ".join([f"{shown} of {punch_count(total)}", *named])


def punch_page(
    detail: PunchDetail,
    labels: Labels | None = None,
    technical: bool = False,
    panel: bool = False,
) -> Page:
    """The punch item as a page: the identity ``<key> · <subject>``, the state line (``Open ·
    category A · due 2026-11-20``), a panel's summary line, then the sections Where (area, system,
    raised from), Work (assignee, cleared by and note, verified by) and History (reopened and its
    reason, void reason when there is one)."""
    lab = _labels(labels)
    row = detail.row
    rows: list[DetailRow] = [
        DetailRow("Area", _val(row.area), section=WHERE),
        DetailRow("System", _val(row.system), section=WHERE),
        DetailRow("Raised from", _val(row.source_key), section=WHERE),
        DetailRow("Assignee", _who(lab, row.assignee, technical), section=WORK),
        DetailRow(
            "Cleared by",
            _val(join_facts(_who(lab, detail.cleared_by, technical), detail.cleared_on)),
            section=WORK,
        ),
        DetailRow("Clear note", _val(detail.clear_note), section=WORK),
        DetailRow(
            "Verified by",
            _val(join_facts(_who(lab, detail.verified_by, technical), detail.verified_on)),
            section=WORK,
        ),
        DetailRow("Reopened", str(detail.reopen_count), section=HISTORY),
    ]
    if detail.reopen_count:
        rows.append(DetailRow("Reopen reason", _val(detail.last_reopen_reason), section=HISTORY))
    if detail.void_reason:
        rows.append(DetailRow("Void reason", _val(detail.void_reason), section=HISTORY))
    state = join_facts(
        humanize(row.state),
        f"category {row.category}",
        f"due {date_text(row.due_on)}" if row.due_on else "",
    )
    summary = join_facts(_who(lab, row.assignee, technical), row.area, row.system)
    return rows_page(
        rows,
        identity=identity_line(row.key, row.subject),
        state=state_line(state),
        summary=summary,
        technical=technical,
        panel=panel,
    )
