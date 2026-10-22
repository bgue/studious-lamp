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

from tl_tui.client import ClientInterface
from tl_tui.details import rows_page, since_of
from tl_tui.details.commercial import commercial_content
from tl_tui.display import Labels, domain_label, humanize
from tl_tui.layout import Page, identity_line, plain_lines, state_line
from tl_tui.text import EMPTY

COMMERCIAL_COLUMNS = (
    "Number",
    "Subject",
    "State",
    "Kind",
    "Aware",
    "Bar due",
    "Left",
    "Bar",
    "Cur",
    "Estimated",
    "Assessed",
)


def _labels(labels: Labels | None) -> Labels:
    return labels if labels is not None else Labels()


def bar_text(line: CommercialLine) -> str:
    """``LATE`` for a bar that expired or was met after its due day, else the bar's state
    (``running``, ``met``, ...), ``-`` for an item with no bar."""
    if line.time_bar_late:
        return "LATE"
    return line.time_bar_state or EMPTY


def _bar_plain(line: CommercialLine) -> str:
    """``LATE`` as before; otherwise the bar's state in words (``Running``), ``—`` for no bar."""
    if line.time_bar_late:
        return "LATE"
    return humanize(line.time_bar_state) if line.time_bar_state else EMPTY


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
        kind = domain_label(_labels(labels), "commercial", line.subtype) if line.subtype else EMPTY
        bar = _bar_plain(line)
    return (
        line.number,
        line.subject,
        state,
        kind,
        line.aware_on or EMPTY,
        line.time_bar_due or EMPTY,
        EMPTY if line.time_bar_days_left is None else str(line.time_bar_days_left),
        bar,
        line.currency or EMPTY,
        line.estimated_value or EMPTY,
        line.assessed_value or EMPTY,
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


def commercial_page(
    view: CommercialView,
    labels: Labels | None = None,
    *,
    technical: bool = False,
    client: ClientInterface | None = None,
) -> Page:
    """The panel under the register (skill ``tui-layout``): the identity and state lines, the
    basis, key facts, cost and schedule figures, assessment, clocks and files. With a ``client``
    the files and the day the state began are read; ``technical`` keeps the raw state and adds
    the record id."""
    state = view.state if technical else humanize(view.state)
    since = since_of(client, view.id) if client is not None else None
    return rows_page(
        commercial_content(view, _labels(labels), client=client),
        identity=identity_line(view.number, view.subject),
        state=state_line(state, since),
        technical=technical,
        panel=True,
    )


def commercial_lines(
    view: CommercialView, labels: Labels | None = None, *, technical: bool = False
) -> list[str]:
    """The panel as plain lines (no client: no files)."""
    return plain_lines(commercial_page(view, labels, technical=technical))
