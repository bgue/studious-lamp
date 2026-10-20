# ruff: noqa: F401, F841
"""What the RFI log shows, as pure functions (P1-I6; brief 9 M10, brief 16).

The rows of the RFI log, its summary line and the panel under it are text built from
``tl_mod_correspondence.reports_technical`` and ``views_domain`` values and nothing else, so the
tests check them without a terminal. The figures (response days, overdue, on time) are the
report's: this module shows them as they come and decides nothing.

STUB (P1-I6-T07a): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from tl_mod_correspondence.reports_technical import RfiLog, RfiLogLine
from tl_mod_correspondence.views_domain import TechnicalView

from tl_tui.correspondence_text import clock_line

RFI_COLUMNS = (
    "Number",
    "State",
    "Kind",
    "Disc",
    "Raised",
    "Needed",
    "Answered",
    "Days",
    "Timing",
    "Impact",
    "Subject",
)


def timing_text(line: RfiLogLine) -> str:
    """``overdue 3d`` (still waiting, past the date needed), ``late`` or ``on time`` (answered),
    ``-`` otherwise."""
    # STEPS
    # 1. If `line.overdue` is true return `f"overdue {line.days_overdue}d"`.
    # 2. Otherwise, if `line.on_time is None`, return `"-"`.
    # 3. Otherwise return `"on time"` when `line.on_time` is true and `"late"` when it is
    #    false.
    raise NotImplementedError


def impact_text(line: RfiLogLine) -> str:
    """``C:yes S:no`` from the answerer's statement; before an answer the raiser's own flags, in
    brackets: ``C:(unknown) S:(yes)``."""

    # STEPS
    # 1. Define a small inner function `one(answered: str | None, expected: str) -> str`
    #    that returns `answered` when it is not `None` and `f"({expected})"` otherwise.
    # 2. `cost = one(line.cost_impact, line.potential_cost_impact)` and `schedule =
    #    one(line.schedule_impact, line.potential_schedule_impact)`.
    # 3. Return `f"C:{cost} S:{schedule}"`.
    raise NotImplementedError


def rfi_cells(line: RfiLogLine) -> tuple[str, ...]:
    """The eleven cells of a log row, in the order of ``RFI_COLUMNS``."""
    # STEPS
    # 1. Return a tuple of exactly eleven strings, in the order of `RFI_COLUMNS`:
    #    `line.number`, `line.state`, `line.subtype`, `line.discipline or "-"`,
    #    `line.raised_on`, `line.required_by or "-"`, `line.answered_on or "-"`, `"-" if
    #    line.response_days is None else str(line.response_days)` (0 days is `"0"`, not a
    #    dash), `timing_text(line)`, `impact_text(line)`, `line.subject`.
    raise NotImplementedError


def rfi_summary(
    log: RfiLog, *, only_open: bool = False, only_overdue: bool = False, only_impact: bool = False
) -> str:
    """``3 items | answered 1 | open 2 | overdue 1 | impact yes 1 | average answer 6.0 days``, and
    ``| filter: open, overdue`` when a filter is on."""
    # STEPS
    # 1. `parts` is a list of strings, in this order: `f"{log.total} item{'s' if log.total
    #    != 1 else ''}"`, `f"answered {log.answered}"`, `f"open {log.open}"`, `f"overdue
    #    {log.overdue}"`, `f"impact yes {log.impact_yes}"`.
    # 2. When `log.average_response_days is not None` (0.0 counts) append `f"average
    #    answer {log.average_response_days:.1f} days"`.
    # 3. `filters` is the list of the names `"open"`, `"overdue"`, `"impact"` whose flag
    #    (`only_open`, `only_overdue`, `only_impact`) is true, in that order. When it is
    #    not empty append `"filter: " + ", ".join(filters)`.
    # 4. Return `" | ".join(parts)`.
    raise NotImplementedError


def rfi_lines(view: TechnicalView) -> list[str]:
    """The panel under the log: the highlighted RFI, its answer, its review and what it led to."""
    # STEPS
    # 1. Start `lines` with these six strings: `f"{view.number}  {view.state}
    #    {view.subtype or '-'}  class {view.confidentiality}"`; `f"subject:
    #    {view.subject}"`; `f"question: {view.question}"`; `f"proposed:
    #    {view.proposed_solution or '-'}"`; `f"discipline {view.discipline or '-'}  needed
    #    by {view.required_by or '-'}  issued {view.issued_on or '-'}"` (two spaces
    #    between the parts); `f"raiser expects: cost {view.potential_cost_impact},
    #    schedule {view.potential_schedule_impact}"`.
    # 2. When `view.answered_on is not None` append `f"answer ({view.answered_on}):
    #    {view.answer or '-'}"` and then `f"answerer says: cost {view.answer_cost_impact
    #    or '-'}, schedule {view.answer_schedule_impact or '-'}"`.
    # 3. When `view.answer_item_number` is set append `f"answered by item
    #    {view.answer_item_number}"`.
    # 4. When `view.review_decision` is set append `f"reviewed {view.reviewed_on or '-'}:
    #    {view.review_decision}"` followed, only when `view.review_note` is set, by `f"
    #    ({view.review_note})"` (one line).
    # 5. When `view.escalations` is not empty append `"escalated to: " + ",
    #    ".join(f"{e.number} ({e.state})" for e in view.escalations)`.
    # 6. When `view.clocks` is not empty append `"clocks:"` and then, for each clock, `f"
    #    {clock_line(c)}"` (two spaces).
    # 7. Return `lines`.
    raise NotImplementedError
