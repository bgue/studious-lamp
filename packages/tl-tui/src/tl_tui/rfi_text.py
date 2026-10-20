"""What the RFI log shows, as pure functions (P1-I6; brief 9 M10, brief 16).

The rows of the RFI log, its summary line and the panel under it are text built from
``tl_mod_correspondence.reports_technical`` and ``views_domain`` values and nothing else, so the
tests check them without a terminal. The figures (response days, overdue, on time) are the
report's: this module shows them as they come and decides nothing.
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
    if line.overdue:
        return f"overdue {line.days_overdue}d"
    if line.on_time is None:
        return "-"
    return "on time" if line.on_time else "late"


def impact_text(line: RfiLogLine) -> str:
    """``C:yes S:no`` from the answerer's statement; before an answer the raiser's own flags, in
    brackets: ``C:(unknown) S:(yes)``."""

    def one(answered: str | None, expected: str) -> str:
        return answered if answered is not None else f"({expected})"

    cost = one(line.cost_impact, line.potential_cost_impact)
    schedule = one(line.schedule_impact, line.potential_schedule_impact)
    return f"C:{cost} S:{schedule}"


def rfi_cells(line: RfiLogLine) -> tuple[str, ...]:
    """The eleven cells of a log row, in the order of ``RFI_COLUMNS``."""
    return (
        line.number,
        line.state,
        line.subtype,
        line.discipline or "-",
        line.raised_on,
        line.required_by or "-",
        line.answered_on or "-",
        "-" if line.response_days is None else str(line.response_days),
        timing_text(line),
        impact_text(line),
        line.subject,
    )


def rfi_summary(
    log: RfiLog, *, only_open: bool = False, only_overdue: bool = False, only_impact: bool = False
) -> str:
    """``3 items | answered 1 | open 2 | overdue 1 | impact yes 1 | average answer 6.0 days``, and
    ``| filter: open, overdue`` when a filter is on."""
    parts = [
        f"{log.total} item{'s' if log.total != 1 else ''}",
        f"answered {log.answered}",
        f"open {log.open}",
        f"overdue {log.overdue}",
        f"impact yes {log.impact_yes}",
    ]
    if log.average_response_days is not None:
        parts.append(f"average answer {log.average_response_days:.1f} days")
    filters = [
        name
        for name, flag in (("open", only_open), ("overdue", only_overdue), ("impact", only_impact))
        if flag
    ]
    if filters:
        parts.append("filter: " + ", ".join(filters))
    return " | ".join(parts)


def rfi_lines(view: TechnicalView) -> list[str]:
    """The panel under the log: the highlighted RFI, its answer, its review and what it led to."""
    lines = [
        f"{view.number}  {view.state}  {view.subtype or '-'}  class {view.confidentiality}",
        f"subject: {view.subject}",
        f"question: {view.question}",
        f"proposed: {view.proposed_solution or '-'}",
        f"discipline {view.discipline or '-'}  needed by {view.required_by or '-'}  "
        f"issued {view.issued_on or '-'}",
        f"raiser expects: cost {view.potential_cost_impact}, "
        f"schedule {view.potential_schedule_impact}",
    ]
    if view.answered_on is not None:
        lines.append(f"answer ({view.answered_on}): {view.answer or '-'}")
        lines.append(
            f"answerer says: cost {view.answer_cost_impact or '-'}, "
            f"schedule {view.answer_schedule_impact or '-'}"
        )
    if view.answer_item_number:
        lines.append(f"answered by item {view.answer_item_number}")
    if view.review_decision:
        review = f"reviewed {view.reviewed_on or '-'}: {view.review_decision}"
        if view.review_note:
            review += f" ({view.review_note})"
        lines.append(review)
    if view.escalations:
        lines.append(
            "escalated to: " + ", ".join(f"{e.number} ({e.state})" for e in view.escalations)
        )
    if view.clocks:
        lines.append("clocks:")
        lines.extend(f"  {clock_line(c)}" for c in view.clocks)
    return lines
