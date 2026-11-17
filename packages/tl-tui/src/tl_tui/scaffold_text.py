"""The text of the scaffold register and of one scaffold's record (P2-I4B-T07b; spec §8).

The values come from ``tl_mod_scaffold.views`` (``ScaffoldRow``, ``ScaffoldDetail``,
``InspectionRow``) and nothing else: no client call, no I/O, and no ``textual`` import. Dates are
formatted by ``tl_tui.awp_text`` (``date_text``). A scaffold's record id is carried for commands
and is never printed here. The register's overdue test takes ``today`` from the caller; this
module never reads the clock.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from tl_mod_scaffold import names
from tl_mod_scaffold.rules import STANDING_STATES

from tl_tui.awp_text import date_text
from tl_tui.display import Labels, actor_label, humanize
from tl_tui.layout import Page, Prop, Section, TableRow, identity_line, prop, shown, state_line

if TYPE_CHECKING:
    from tl_mod_scaffold.views import InspectionRow, ScaffoldDetail, ScaffoldRow

SCAFFOLD_COLUMNS = ("Number", "Subject", "State", "Tag", "Last inspected", "Next due", "Location")
SCAFFOLD_DROP = ("Location", "Last inspected", "Subject")  # dropped first at narrow width
NOUN = "scaffold"
INSPECTIONS_HEADING = "Inspections"
INSPECTION_COLUMNS = ("Date", "Inspector", "Result", "Tag", "Note")
NO_INSPECTIONS = "No inspections yet"
NOT_FOUND = "No such scaffold."

#: The states in the order the summary names them in.
STATE_ORDER: tuple[str, ...] = (
    names.REQUESTED,
    names.DESIGNED_STATE,
    names.ERECTING_STATE,
    names.INSPECTED_STATE,
    names.IN_USE,
    names.MODIFY,
    names.DISMANTLE,
    names.REMOVED,
)


def _labels(labels: Labels | None) -> Labels:
    return Labels() if labels is None else labels


def scaffold_count(total: int) -> str:
    """``1 scaffold``, ``5 scaffolds``, ``0 scaffolds``."""
    return f"{total} {NOUN}" if total == 1 else f"{total} {NOUN}s"


def is_overdue(row: ScaffoldRow, today: str) -> bool:
    """A standing scaffold (Inspected, In Use, Modify) whose next inspection day is before today."""
    return row.state in STANDING_STATES and row.next_due_on is not None and row.next_due_on < today


def scaffold_cells(row: ScaffoldRow) -> tuple[str, ...]:
    """The seven cells of a register row, in the order of ``SCAFFOLD_COLUMNS``. The tag is its
    colour word (``green``, ``yellow``, ``red``): the colour is never the only signal."""
    return (
        row.key,
        shown(row.subject),
        shown(row.state),
        shown(row.tag),
        date_text(row.last_inspected_on),
        date_text(row.next_due_on),
        shown(row.location),
    )


def scaffold_summary(rows: Sequence[ScaffoldRow], total: int, *, today: str) -> str:
    """``5 scaffolds: 2 In Use, 1 Modify; 1 overdue``; the overdue count only when it is not zero.
    The state counts are over ``rows`` (the rows held); the number is ``total``."""
    if total == 0:
        return scaffold_count(0)
    counts = Counter(row.state for row in rows)
    known = [state for state in STATE_ORDER if counts.get(state)]
    extra = sorted(state for state in counts if state not in STATE_ORDER)
    by_state = ", ".join(f"{counts[state]} {state}" for state in [*known, *extra])
    text = f"{scaffold_count(total)}: {by_state}" if by_state else scaffold_count(total)
    overdue = sum(1 for row in rows if is_overdue(row, today))
    if overdue:
        text += f"; {overdue} overdue"
    return text


def register_page(
    rows: Sequence[ScaffoldRow],
    total: int,
    *,
    today: str,
    labels: Labels | None = None,
) -> tuple[list[tuple[str, ...]], str]:
    """The register as its log text: the cells of each row (``scaffold_cells``, in row order) and
    the summary line. ``labels`` is accepted for the screens' common shape; the register shows no
    person, so it is not read."""
    del labels  # the register shows no person; the detail page names inspectors
    cells = [scaffold_cells(row) for row in rows]
    return cells, scaffold_summary(rows, total, today=today)


def _inspection_row(item: InspectionRow, labels: Labels) -> TableRow:
    return TableRow(
        columns=INSPECTION_COLUMNS,
        cells=(
            date_text(item.inspected_on),
            shown(actor_label(labels, item.inspector) if item.inspector else None),
            humanize(item.result),
            shown(item.tag),
            shown(item.note),
        ),
    )


def _reasons(detail: ScaffoldDetail) -> list[Prop]:
    found: list[Prop] = []
    if detail.modify_reason:
        found.append(prop("Modify reason", detail.modify_reason))
    if detail.dismantle_reason:
        found.append(prop("Dismantle reason", detail.dismantle_reason))
    return found


def detail_page(detail: ScaffoldDetail, *, labels: Labels | None = None) -> Page:
    """One scaffold as a page: the identity ``<key> · <subject>``, the state, then the sections
    Status (tag, dates), Where (location, elevation, gridline), Use (load class, the request it
    came from, the record it serves), Reasons when there are any, and Inspections oldest first."""
    lab = _labels(labels)
    row = detail.row
    status = [
        prop("Tag", row.tag),
        prop("Tagged on", date_text(row.tagged_on)),
        prop("Last inspected", date_text(row.last_inspected_on)),
        prop("Next due", date_text(row.next_due_on)),
    ]
    where = [
        prop("Location", row.location),
        prop("Elevation", row.elevation),
        prop("Gridline", row.gridline),
    ]
    use = [
        prop("Load class", row.load_class),
        prop("Requested from", row.request_key),
        prop("Serves", detail.for_key),
    ]
    reasons = _reasons(detail)
    sections: list[Section] = [
        Section("Status", tuple(status)),
        Section("Where", tuple(where)),
        Section("Use", tuple(use)),
    ]
    if reasons:
        sections.append(Section("Reasons", tuple(reasons)))
    items: Iterable[TableRow] = (_inspection_row(item, lab) for item in detail.inspections)
    sections.append(
        Section(
            INSPECTIONS_HEADING, tuple(items), note="" if detail.inspections else NO_INSPECTIONS
        )
    )
    return Page(
        identity=identity_line(row.key, row.subject),
        state=state_line(row.state),
        sections=tuple(sections),
    )


def export_filename(project: str, fmt: str) -> str:
    """The export's file name in the working directory: ``scaffolds-<project>.<fmt>``."""
    return f"scaffolds-{project}.{fmt}"
