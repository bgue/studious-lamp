# ruff: noqa: F401, F841
"""What the Commercial register shows, as pure functions (P1-I6; brief 9 M10, brief 16).

The rows of the register, its summary line and the panel under it are text built from
``tl_mod_correspondence.reports_commercial`` and ``views_domain`` values and nothing else. The
figures (days left on the time bar, late, totals by currency) are the report's. Amounts of
different currencies are shown on lines of their own and never added.

STUB (P1-I6-T07b): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from tl_mod_correspondence.reports_commercial import CommercialLine, CommercialRegister
from tl_mod_correspondence.views_domain import CommercialView

from tl_tui.correspondence_text import clock_line

COMMERCIAL_COLUMNS = (
    "Number",
    "State",
    "Kind",
    "Aware",
    "Bar due",
    "Left",
    "Bar",
    "Cur",
    "Estimated",
    "Assessed",
    "Status",
    "Subject",
)


def bar_text(line: CommercialLine) -> str:
    """``LATE`` for a bar that expired or was met after its due day, else the bar's state
    (``running``, ``met``, ...), ``-`` for an item with no bar."""
    # STEPS
    # 1. If `line.time_bar_late` is true return `"LATE"`.
    # 2. Otherwise return `line.time_bar_state or "-"`.
    raise NotImplementedError


def commercial_cells(line: CommercialLine) -> tuple[str, ...]:
    """The twelve cells of a register row, in the order of ``COMMERCIAL_COLUMNS``."""
    # STEPS
    # 1. Return a tuple of exactly twelve strings, in the order of `COMMERCIAL_COLUMNS`:
    #    `line.number`, `line.state`, `line.subtype`, `line.aware_on or "-"`,
    #    `line.time_bar_due or "-"`, `"-" if line.time_bar_days_left is None else
    #    str(line.time_bar_days_left)` (0 days left is `"0"`, a negative number keeps its
    #    sign), `bar_text(line)`, `line.currency or "-"`, `line.estimated_value or "-"`,
    #    `line.assessed_value or "-"`, `(line.assessment_status or "-").replace("_", "
    #    ")`, `line.subject`.
    raise NotImplementedError


def commercial_summary(
    register: CommercialRegister, *, only_open: bool = False, time_bars_only: bool = False
) -> str:
    """``2 notices | time bars running 1, late 1 | USD: 2 estimated 40000.00 assessed 25000.00``,
    one ``CUR:`` part for each currency, and ``| filter: open, time bars`` when a filter is on."""
    # STEPS
    # 1. `count = len(register.lines)`. `parts` starts with `f"{count} notice{'s' if count
    #    != 1 else ''}"` and `f"time bars running {register.time_bars_running}, late
    #    {register.time_bars_late}"`.
    # 2. For each `total` in `register.totals` (all of them, in the order given) append
    #    `f"{total.currency}: {total.count} estimated {total.estimated} assessed
    #    {total.assessed}"`. Amounts of different currencies are never added: one part for
    #    each currency.
    # 3. `filters` is the list of the names `"open"` and `"time bars"` whose flag
    #    (`only_open`, `time_bars_only`) is true, in that order. When it is not empty
    #    append `"filter: " + ", ".join(filters)`.
    # 4. Return `" | ".join(parts)`.
    raise NotImplementedError


def commercial_lines(view: CommercialView) -> list[str]:
    """The panel under the register: the highlighted notice, its figures, assessment and clocks."""
    # STEPS
    # 1. `money = f"{view.currency or '-'} {view.estimated_value or '-'}"` and `days = "-"
    #    if view.schedule_impact_days is None else str(view.schedule_impact_days)`.
    # 2. Start `lines` with these four strings: `f"{view.number}  {view.state}
    #    {view.subtype or '-'}  class {view.confidentiality}"`; `f"subject:
    #    {view.subject}"`; `f"clause {view.clause or '-'}  aware on {view.aware_on or '-'}
    #    issued {view.issued_on or '-'}"`; `f"estimated {money}  hours
    #    {view.estimated_hours or '-'}  schedule {days} days"` (two spaces between the
    #    parts).
    # 3. When `view.cost_code_impacts` is not empty append `"cost codes: " + ",
    #    ".join(...)` where each impact `i` (a dict) gives
    #    `f"{i['cost_code']}={i.get('amount') or i.get('hours') or '-'}"`.
    # 4. When `view.entitlement_basis` is set append `f"basis: {view.entitlement_basis}"`.
    #    When `view.derived_from_number` is set append `f"escalated from
    #    {view.derived_from_number}"`.
    # 5. When `view.assessment_status` is set append `f"assessment ({view.assessed_on or
    #    '-'}): {view.assessment_status.replace('_', ' ')} {view.currency or ''}
    #    {view.assessed_value or '-'}"` followed, only when `view.assessment_note` is set,
    #    by `f" ({view.assessment_note})"` (one line).
    # 6. When `view.clocks` is not empty append `"clocks:"` and then, for each clock, `f"
    #    {clock_line(c)}"` (two spaces). Return `lines`.
    raise NotImplementedError
