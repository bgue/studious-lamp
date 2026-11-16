"""The text of the inspection log and of an inspection's screen, as pure functions (P2-INSP-T10;
spec §8, skill ``tui-layout``).

The values come from ``tl_mod_quality.insp_views`` (``InspectionRow``, ``InspectionDetail``) and
nothing else: no client call, no I/O, and no ``textual`` import. Dates are formatted by
``tl_tui.awp_text`` (``date_text``); the inspection's record id is carried for commands and never
printed here. Scheduling and recording answers stay on the CLI until the runner screen (T11).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, cast

from tl_mod_quality.names import CANCELLED, DONE, PLANNED, SCHEDULED, VERIFIED

from tl_tui.awp_text import date_text
from tl_tui.details import DetailRow, rows_page
from tl_tui.display import Labels, actor_label, humanize
from tl_tui.layout import EMPTY, Page, Section, identity_line, join_facts, state_line

if TYPE_CHECKING:
    from tl_mod_quality.insp_views import InspectionDetail, InspectionRow

INSPECTION_COLUMNS = (
    "Number",
    "Title",
    "State",
    "Point",
    "Result",
    "Scheduled",
    "Inspector",
    "Area",
)
INSPECTION_DROP = ("Inspector", "Area", "Scheduled")  # dropped first at narrow width
INSPECTION_RIGHT: tuple[str, ...] = ()

STATES = (PLANNED, SCHEDULED, DONE, VERIFIED, CANCELLED)  # the order the summary names them in
NOUN = "inspection"
PLAN = "Plan"
WHERE = "Where"
RESULT = "Result"
HISTORY = "History"
PUNCH = "Punch"
NO_PUNCH = "No punch items"


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


def inspection_count(total: int) -> str:
    """``1 inspection``, ``9 inspections``."""
    return f"{total} {NOUN}" if total == 1 else f"{total} {NOUN}s"


def inspection_cells(row: InspectionRow, labels: Labels | None = None) -> tuple[str, ...]:
    """The eight cells of a log row, in the order of ``INSPECTION_COLUMNS``. The state is
    humanized, the scheduled date is ``date_text``, the inspector is a name, and a result that is
    not recorded reads ``-``."""
    return (
        row.key,
        row.title,
        humanize(row.state),
        row.point,
        "-" if row.result is None else row.result,
        date_text(row.scheduled_for),
        EMPTY if not row.inspector else actor_label(_labels(labels), row.inspector),
        _val(row.area),
    )


def _state_counts(counts_or_rows: Mapping[str, int] | Iterable[InspectionRow]) -> Mapping[str, int]:
    """The count of each state: as given, or tallied from the rows the log holds."""
    if isinstance(counts_or_rows, Mapping):
        return cast("Mapping[str, int]", counts_or_rows)
    tally: dict[str, int] = {}
    for row in counts_or_rows:
        tally[row.state] = tally.get(row.state, 0) + 1
    return tally


def inspection_summary(
    counts_or_rows: Mapping[str, int] | Iterable[InspectionRow],
    total: int,
    shown: int,
    *,
    state: str | None = None,
    point: str | None = None,
) -> str:
    """``9 inspections: 2 Planned, 3 Scheduled, 2 Done, 1 Verified, 1 Cancelled``; with a filter
    ``2 of 9 inspections, state Done, point hold``. ``total`` is the page total; the counts are
    the rows the log holds."""
    if state is None and point is None:
        if total == 0:
            return inspection_count(0)
        counts = _state_counts(counts_or_rows)
        by_state = ", ".join(f"{counts.get(name, 0)} {humanize(name)}" for name in STATES)
        return f"{inspection_count(total)}: {by_state}"
    named: list[str] = []
    if state is not None:
        named.append(f"state {humanize(state)}")
    if point is not None:
        named.append(f"point {point}")
    return ", ".join([f"{shown} of {inspection_count(total)}", *named])


def _checklist(detail: InspectionDetail) -> str:
    """``P123-CHK-0002, version 1``; ``—`` when no checklist was pinned."""
    if detail.checklist_key is None:
        return EMPTY
    if detail.checklist_version is None:
        return detail.checklist_key
    return f"{detail.checklist_key}, version {detail.checklist_version}"


def inspection_page(
    detail: InspectionDetail,
    labels: Labels | None = None,
    technical: bool = False,
    panel: bool = False,
) -> Page:
    """The inspection as a page: the identity ``<key> · <title>``, the state line (``Done · hold
    point · reject``), a panel's summary line, then the sections Where (subject, work package,
    area), Plan (planned on, scheduled for, inspector, checklist), Result (recorded by and on,
    note, one line per failed answer: its question text and its note; verified by and on), History
    (reinspection of, cancel reason) and Punch (the keys of the punch items it raised)."""
    lab = _labels(labels)
    row = detail.row
    rows: list[DetailRow] = [
        DetailRow("Subject", _val(row.subject_key), section=WHERE),
        DetailRow("Work package", _val(row.for_key), section=WHERE),
        DetailRow("Area", _val(row.area), section=WHERE),
        DetailRow("Planned on", date_text(row.planned_on), section=PLAN),
        DetailRow("Scheduled for", date_text(row.scheduled_for), section=PLAN),
        DetailRow("Inspector", _who(lab, row.inspector, technical), section=PLAN),
        DetailRow("Checklist", _checklist(detail), section=PLAN),
        DetailRow(
            "Recorded by",
            _val(join_facts(_who(lab, detail.recorded_by, technical), row.done_on)),
            section=RESULT,
        ),
        DetailRow("Note", _val(detail.note), section=RESULT),
        *(DetailRow(item.question, _val(item.note), section=RESULT) for item in detail.failed),
        DetailRow(
            "Verified by",
            _val(join_facts(_who(lab, detail.verified_by, technical), detail.verified_on)),
            section=RESULT,
        ),
        DetailRow("Reinspection of", _val(detail.reinspection_of_key), section=HISTORY),
        DetailRow("Cancel reason", _val(detail.cancel_reason), section=HISTORY),
        DetailRow("Version", str(detail.version), technical=True, section=HISTORY),
    ]
    state = join_facts(humanize(row.state), f"{row.point} point", row.result)
    summary = join_facts(
        _who(lab, row.inspector, technical) if row.inspector else None,
        f"scheduled {row.scheduled_for}" if row.scheduled_for else None,
        row.area,
    )
    page = rows_page(
        rows,
        identity=identity_line(row.key, row.title),
        state=state_line(state),
        summary=summary,
        technical=technical,
        panel=panel,
    )
    punch = Section(PUNCH, tuple(detail.punch_keys), note=NO_PUNCH)
    return Page(page.identity, page.state, (*page.sections, punch), page.summary)
