"""What the RFI log shows, as pure functions (P1-I6; brief 9 M10, brief 16).

The rows of the RFI log, its summary line and the panel under it are text built from
``tl_mod_correspondence.reports_technical`` and ``views_domain`` values and nothing else, so the
tests check them without a terminal. The figures (response days, overdue, on time) are the
report's: this module shows them as they come and decides nothing.
"""

from __future__ import annotations

from tl_mod_correspondence.reports_technical import RfiLog, RfiLogLine
from tl_mod_correspondence.views_domain import TechnicalView

from tl_tui.client import ClientInterface
from tl_tui.details import rows_page, since_of
from tl_tui.details.technical import rfi_content
from tl_tui.display import Labels, code_label, domain_label, humanize
from tl_tui.layout import Page, identity_line, plain_lines, state_line
from tl_tui.text import EMPTY

# The number, the subject and the state come first; the kind shows only when two kinds are listed
# (``LogScreen`` hides a column whose value is the same in every row, P1-UX3).
RFI_COLUMNS = (
    "Number",
    "Subject",
    "State",
    "Kind",
    "Discipline",
    "Raised",
    "Needed by",
    "Answered",
    "Days",
    "Timing",
    "Impact",
)


def timing_text(line: RfiLogLine) -> str:
    """``overdue 3d`` (still waiting, past the date needed), ``late`` or ``on time`` (answered),
    ``—`` otherwise."""
    if line.overdue:
        return f"overdue {line.days_overdue}d"
    if line.on_time is None:
        return EMPTY
    return "on time" if line.on_time else "late"


def impact_text(line: RfiLogLine) -> str:
    """``C:yes S:no`` from the answerer's statement; before an answer the raiser's own flags, in
    brackets: ``C:(unknown) S:(yes)``."""

    def one(answered: str | None, expected: str) -> str:
        return answered if answered is not None else f"({expected})"

    cost = one(line.cost_impact, line.potential_cost_impact)
    schedule = one(line.schedule_impact, line.potential_schedule_impact)
    return f"C:{cost} S:{schedule}"


def rfi_cells(
    line: RfiLogLine, labels: Labels | None = None, *, technical: bool = True
) -> tuple[str, ...]:
    """The eleven cells of a log row, in the order of ``RFI_COLUMNS``. Without ``technical`` the
    State, Kind and Discipline cells read as words (``labels`` gives the labels)."""
    if technical:
        state, kind, discipline = line.state, line.subtype, line.discipline or EMPTY
    else:
        state = humanize(line.state)
        lab = labels if labels is not None else Labels()
        kind = domain_label(lab, "technical", line.subtype) if line.subtype else EMPTY
        discipline = code_label(lab, "discipline", line.discipline) if line.discipline else EMPTY
    return (
        line.number,
        line.subject,
        state,
        kind,
        discipline,
        line.raised_on,
        line.required_by or EMPTY,
        line.answered_on or EMPTY,
        EMPTY if line.response_days is None else str(line.response_days),
        timing_text(line),
        impact_text(line),
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


def rfi_page(
    view: TechnicalView,
    labels: Labels | None = None,
    *,
    technical: bool = False,
    client: ClientInterface | None = None,
    project: str = "",
) -> Page:
    """The panel under the log (skill ``tui-layout``): the identity line, the state line, then
    the question, the answer, the key facts, the clocks, the timeline and the files, the lists
    short. With a ``client`` the timeline, the files and the day the state began are read.
    ``technical`` adds the record id and the clock keys, and keeps the raw state."""
    lab = labels if labels is not None else Labels()
    state = view.state if technical else humanize(view.state)
    since = since_of(client, view.id) if client is not None else None
    return rows_page(
        rfi_content(view, lab, client=client, project=project),
        identity=identity_line(view.number, view.subject),
        state=state_line(state, since),
        technical=technical,
        panel=True,
    )


def rfi_lines(
    view: TechnicalView, labels: Labels | None = None, *, technical: bool = False
) -> list[str]:
    """The panel as plain lines (no client: no timeline and no files)."""
    return plain_lines(rfi_page(view, labels, technical=technical))
