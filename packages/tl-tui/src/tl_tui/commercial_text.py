"""What the Commercial register shows, as pure functions (P1-I6; brief 9 M10, brief 16).

The rows of the register, its summary line and the panel under it are text built from
``tl_mod_correspondence.reports_commercial`` and ``views_domain`` values and nothing else. The
figures (days left on the time bar, late, totals by currency) are the report's. Amounts of
different currencies are shown on lines of their own and never added.

By default the text is plain words (domain labels, humanized states); ``technical=True`` gives
the internal keys back (P1-UX-T05, SCOPE clause 3).
"""

from __future__ import annotations

from tl_mod_correspondence.reports_commercial import CommercialLine, CommercialRegister
from tl_mod_correspondence.views_domain import CommercialView

from tl_tui.correspondence_text import clock_line
from tl_tui.display import Labels, code_label, domain_label, humanize

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
    "Subject",
)


def _labels(labels: Labels | None) -> Labels:
    return labels if labels is not None else Labels()


def bar_text(line: CommercialLine) -> str:
    """``LATE`` for a bar that expired or was met after its due day, else the bar's state
    (``running``, ``met``, ...), ``-`` for an item with no bar."""
    if line.time_bar_late:
        return "LATE"
    return line.time_bar_state or "-"


def _bar_plain(line: CommercialLine) -> str:
    """``LATE`` as before; otherwise the bar's state in words (``Running``), ``-`` for no bar."""
    if line.time_bar_late:
        return "LATE"
    return humanize(line.time_bar_state) if line.time_bar_state else "-"


def commercial_cells(
    line: CommercialLine, labels: Labels | None = None, *, technical: bool = True
) -> tuple[str, ...]:
    """The eleven cells of a register row, in the order of ``COMMERCIAL_COLUMNS``. Without
    ``technical`` the State and Kind cells and the bar read as words."""
    if technical:
        state = line.state
        kind = line.subtype
        bar = bar_text(line)
    else:
        state = humanize(line.state)
        kind = domain_label(_labels(labels), "commercial", line.subtype) if line.subtype else "-"
        bar = _bar_plain(line)
    return (
        line.number,
        state,
        kind,
        line.aware_on or "-",
        line.time_bar_due or "-",
        "-" if line.time_bar_days_left is None else str(line.time_bar_days_left),
        bar,
        line.currency or "-",
        line.estimated_value or "-",
        line.assessed_value or "-",
        line.subject,
    )


def commercial_summary(
    register: CommercialRegister, *, only_open: bool = False, time_bars_only: bool = False
) -> str:
    """``2 notices | time bars running 1, late 1 | USD: 2 estimated 40000.00 assessed 25000.00``,
    one ``CUR:`` part for each currency, and ``| filter: open, time bars`` when a filter is on."""
    count = len(register.lines)
    parts = [
        f"{count} notice{'s' if count != 1 else ''}",
        f"time bars running {register.time_bars_running}, late {register.time_bars_late}",
    ]
    parts.extend(
        f"{total.currency}: {total.count} estimated {total.estimated} assessed {total.assessed}"
        for total in register.totals
    )
    filters = [name for name, on in (("open", only_open), ("time bars", time_bars_only)) if on]
    if filters:
        parts.append("filter: " + ", ".join(filters))
    return " | ".join(parts)


def commercial_lines(
    view: CommercialView, labels: Labels | None = None, *, technical: bool = False
) -> list[str]:
    """The panel under the register: the highlighted notice, its figures, assessment and clocks.
    ``technical`` adds the record id and the clock keys, and keeps the raw kind and states."""
    lab = _labels(labels)
    money = f"{view.currency or '-'} {view.estimated_value or '-'}"
    days = "-" if view.schedule_impact_days is None else str(view.schedule_impact_days)
    if technical:
        state, kind, klass = view.state, view.subtype or "-", view.confidentiality
    else:
        state = humanize(view.state)
        kind = domain_label(lab, "commercial", view.subtype) if view.subtype else "-"
        klass = code_label(lab, "confidentiality", view.confidentiality)
    lines = [f"{view.number}  {state}  {kind}  class {klass}"]
    if technical:
        lines.append(f"record {view.id}")
    lines += [
        f"subject: {view.subject}",
        f"clause {view.clause or '-'}  aware on {view.aware_on or '-'}  "
        f"issued {view.issued_on or '-'}",
        f"estimated {money}  hours {view.estimated_hours or '-'}  schedule {days} days",
    ]
    if view.cost_code_impacts:
        lines.append(
            "cost codes: "
            + ", ".join(
                f"{i['cost_code']}={i.get('amount') or i.get('hours') or '-'}"
                for i in view.cost_code_impacts
            )
        )
    if view.entitlement_basis:
        lines.append(f"basis: {view.entitlement_basis}")
    if view.derived_from_number:
        lines.append(f"escalated from {view.derived_from_number}")
    if view.assessment_status:
        status = (
            view.assessment_status.replace("_", " ")
            if technical
            else humanize(view.assessment_status)
        )
        assessment = (
            f"assessment ({view.assessed_on or '-'}): "
            f"{status} {view.currency or ''} "
            f"{view.assessed_value or '-'}"
        )
        if view.assessment_note:
            assessment += f" ({view.assessment_note})"
        lines.append(assessment)
    if view.clocks:
        lines.append("clocks:")
        lines.extend(f"  {clock_line(c, technical=technical)}" for c in view.clocks)
    return lines
