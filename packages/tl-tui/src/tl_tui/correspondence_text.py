"""What the correspondence screen shows, as pure functions (P1-I5; brief 9 M10).

The register rows, the triage inbox, the clocks table and the detail panel are text built from
``tl_mod_correspondence.views`` values and nothing else, so the tests check them without a
terminal. None of it decides anything: which domain a letter belongs to is the suggestion engine's
proposal, and the days left on a clock are the clock engine's figure, shown as they come.

Plain mode (P1-UX-T03) shows domain labels, the item number for a clock and no calendar; the
``technical`` flag puts back the clock key, the calendar and the record id.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_mod_correspondence.views import ClockView, ItemView, RegisterLineView, SuggestionView

from tl_tui.client import ClientInterface
from tl_tui.details import rows_page, since_of
from tl_tui.details.correspondence import (
    clock_content,
    clock_state,
    direction_word,
    item_content,
)
from tl_tui.display import Labels, actor_label, category_label, domain_label, humanize
from tl_tui.layout import Page, identity_line, join_facts, plain_lines, state_line
from tl_tui.text import EMPTY

# Number, Subject (Title) and State first (skill tui-layout); a column that is the same in every
# row (``Dir`` in a register of letters received) is hidden by ``LogScreen``.
REGISTER_COLUMNS = ("Number", "Subject", "State", "In/out", "Category", "Date", "With", "Due")
# columns left out, least needed first, when the register would not fit without scrolling
REGISTER_DROP = ("Due", "Date", "In/out")
CLOCK_DROP = ("Type", "Days", "Left")
CLOCK_COLUMNS = ("Clock", "Label", "State", "Due", "Left", "Days", "Type")
PLAIN_CLOCK_COLUMNS = ("Item", "Label", "State", "Due", "Left", "Days", "Type")
MODES = ("register", "inbox", "clocks")
MODE_TITLES = {"register": "Register", "inbox": "Triage inbox", "clocks": "Response clocks"}
DIRECTION = {"in": "In", "out": "Out", "internal": "Int"}


def _labels(labels: Labels | None) -> Labels:
    return Labels() if labels is None else labels


def register_cells(line: RegisterLineView, labels: Labels | None = None) -> tuple[str, ...]:
    """The eight cells of a register row, in the order of ``REGISTER_COLUMNS``. The category is
    the short name (``RFI``, ``Letter``, ``Transmittal``); the direction reads ``In``, ``Out``,
    ``Int``."""
    if line.kind == "transmittal":
        category = category_label(_labels(labels), "document_control", "transmittal")
    else:
        category = category_label(_labels(labels), line.domain, line.subtype)
    return (
        line.number,
        line.subject,
        humanize(line.state),
        DIRECTION.get(line.direction, line.direction),
        category,
        line.on or EMPTY,
        line.counterparty or EMPTY,
        line.response_due or EMPTY,
    )


def left_text(clock: ClockView) -> str:
    """``5``, ``0`` (due today) or ``-3`` (three days over); ``—`` when the clock is not running."""
    if clock.days_left is None:
        return EMPTY
    return str(clock.days_left)


def clock_cells(clock: ClockView, *, technical: bool = False) -> tuple[str, ...]:
    """The seven cells of a clock row, in the order of ``CLOCK_COLUMNS`` (technical) or
    ``PLAIN_CLOCK_COLUMNS`` (plain: the item number leads, not the clock key)."""
    first = clock.key if technical else clock.item_number
    return (
        first,
        clock.label,
        humanize(clock.effective_state),
        clock.due_on,
        left_text(clock),
        f"{clock.duration_days} {clock.day_type[:3]}",
        clock.kind.replace("_", " "),
    )


def clock_line(clock: ClockView, *, technical: bool = False) -> str:
    """One clock under an item: ``running due 2026-11-02 left 14 (14 calendar days) Reply``.

    Technical mode puts the clock key in front and the calendar code in the brackets.
    """
    key = f"{clock.key} " if technical else ""
    calendar = f", calendar {clock.calendar}" if technical else ""
    line = (
        f"{key}{clock.effective_state} due {clock.due_on} left {left_text(clock)} "
        f"({clock.duration_days} {clock.day_type} days{calendar}) {clock.label}"
    )
    if clock.paused_on:
        line += f"; paused since {clock.paused_on}"
    if clock.closed_on:
        line += f"; closed {clock.closed_on} ({clock.closed_reason or '-'})"
    return line


def suggestion_text(found: SuggestionView, labels: Labels | None = None) -> str:
    """``Letter (score 4): general: 'memo'`` or ``no domain is defined``."""
    if found.domain is None:
        return "no domain is defined"
    head = f"{domain_label(_labels(labels), found.domain, found.subtype)} (score {found.score})"
    return head + (": " + "; ".join(found.reasons) if found.reasons else "")


def item_summary_facts(item: ItemView) -> str:
    """The decision facts of a letter in one line: ``Outgoing · to Acme Construction · reply due
    2026-10-26``; an incoming one reads ``from``."""
    if item.direction == "out":
        names = ", ".join(p.name or p.email or EMPTY for p in item.to)
        with_ = f"to {names}" if names else ""
    else:
        with_ = f"from {item.from_name}" if item.from_name else ""
    due = f"reply due {item.response_due}" if item.response_required and item.response_due else ""
    return join_facts(direction_word(item.direction), with_, due)


def item_page(
    item: ItemView,
    suggestion: SuggestionView | None = None,
    labels: Labels | None = None,
    *,
    technical: bool = False,
    client: ClientInterface | None = None,
    project: str = "",
) -> Page:
    """The panel under the register (skill ``tui-layout``): the identity and state lines, the
    message, what the suggestion engine proposes (a received item), the key facts, people, dates,
    clocks, timeline and files. With a ``client`` the timeline, the files and the day the state
    began are read; ``technical`` adds the record id and the clock keys."""
    shown = _labels(labels)
    since = since_of(client, item.id) if client is not None else None
    return rows_page(
        item_content(
            client,
            project,
            item,
            shown,
            suggestion=suggestion_text(suggestion, shown) if suggestion is not None else "",
        ),
        identity=identity_line(item.number, item.subject),
        state=state_line(humanize(item.state), since),
        summary=item_summary_facts(item),
        technical=technical,
        panel=True,
    )


def item_lines(
    item: ItemView,
    suggestion: SuggestionView | None = None,
    labels: Labels | None = None,
    *,
    technical: bool = False,
) -> list[str]:
    """The panel as plain lines (no client: no timeline and no files)."""
    return plain_lines(item_page(item, suggestion, labels, technical=technical))


def clock_page(clock: ClockView, labels: Labels | None = None, *, technical: bool = False) -> Page:
    """The panel under the clocks table: the item and label, the clock's state and due date, then
    its key facts."""
    lab = _labels(labels)
    left = clock.days_left
    unit = f"{clock.day_type} day{'s' if left is not None and abs(left) != 1 else ''}"
    time = (
        ""
        if left is None or clock.closed_on
        else f"{left} {unit} left"
        if left >= 0
        else f"{-left} {unit} over"
    )
    return rows_page(
        clock_content(clock, lab),
        identity=identity_line(clock.item_number, clock.label),
        state=clock_state(clock),
        summary=join_facts(
            f"due {clock.due_on}",
            time,
            actor_label(lab, clock.owner) if clock.owner else "",
        ),
        technical=technical,
        panel=True,
    )


def clock_lines(
    clock: ClockView, labels: Labels | None = None, *, technical: bool = False
) -> list[str]:
    """The panel under the clocks table as plain lines."""
    return plain_lines(clock_page(clock, labels, technical=technical))


def summary_line(mode: str, shown: int, *, closed_too: bool = False) -> str:
    """``3 items awaiting triage`` and its relatives."""
    if mode == "inbox":
        return f"{shown} item{'s' if shown != 1 else ''} awaiting triage"
    if mode == "clocks":
        scope = "all" if closed_too else "open"
        return f"{shown} {scope} clock{'s' if shown != 1 else ''}"
    return f"{shown} line{'s' if shown != 1 else ''} in the register"


def next_mode(current: str, step: int = 1) -> str:
    """The mode after (or before) ``current``, wrapping around."""
    modes: Sequence[str] = MODES
    return modes[(modes.index(current) + step) % len(modes)]
