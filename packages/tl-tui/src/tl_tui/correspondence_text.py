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

from tl_tui.display import Labels, actor_label, code_label, domain_label, humanize

REGISTER_COLUMNS = ("Number", "State", "Dir", "Domain", "Date", "With", "Due", "Subject")
CLOCK_COLUMNS = ("Clock", "State", "Due", "Left", "Days", "Type", "Label")
PLAIN_CLOCK_COLUMNS = ("Item", "State", "Due", "Left", "Days", "Type", "Label")
MODES = ("register", "inbox", "clocks")
MODE_TITLES = {"register": "Register", "inbox": "Triage inbox", "clocks": "Response clocks"}
DIRECTION = {"in": "in", "out": "out", "internal": "int"}


def _labels(labels: Labels | None) -> Labels:
    return Labels() if labels is None else labels


def register_cells(line: RegisterLineView, labels: Labels | None = None) -> tuple[str, ...]:
    """The eight cells of a register row, in the order of ``REGISTER_COLUMNS``."""
    where = domain_label(_labels(labels), line.domain, line.subtype) if line.domain else "-"
    kind = "" if line.kind == "item" else f" [{line.kind}]"
    return (
        line.number,
        humanize(line.state),
        DIRECTION.get(line.direction, line.direction),
        where,
        line.on or "-",
        line.counterparty or "-",
        line.response_due or "-",
        line.subject + kind,
    )


def left_text(clock: ClockView) -> str:
    """``5``, ``0`` (due today) or ``-3`` (three days over); ``-`` when the clock is not running."""
    if clock.days_left is None:
        return "-"
    return str(clock.days_left)


def clock_cells(clock: ClockView, *, technical: bool = False) -> tuple[str, ...]:
    """The seven cells of a clock row, in the order of ``CLOCK_COLUMNS`` (technical) or
    ``PLAIN_CLOCK_COLUMNS`` (plain: the item number leads, not the clock key)."""
    first = clock.key if technical else clock.item_number
    return (
        first,
        humanize(clock.effective_state),
        clock.due_on,
        left_text(clock),
        f"{clock.duration_days} {clock.day_type[:3]}",
        clock.kind.replace("_", " "),
        clock.label,
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


def item_lines(
    item: ItemView,
    suggestion: SuggestionView | None = None,
    labels: Labels | None = None,
    *,
    technical: bool = False,
) -> list[str]:
    """The panel under the table: the highlighted item, its clocks and (for a received item) what
    the suggestion engine proposes."""
    shown = _labels(labels)
    domain = domain_label(shown, item.domain, item.subtype) if item.domain else "-"
    lines = [
        f"{item.number}  {humanize(item.state)}  {item.direction}  {item.medium}  "
        f"class {code_label(shown, 'confidentiality', item.confidentiality)}",
        f"subject: {item.subject}",
        f"from {item.from_name or '-'}  to "
        + (", ".join(r.name or r.email or "-" for r in item.to) or "-"),
        f"received {item.received_on or '-'}  sent {item.sent_on or '-'}  "
        f"issued {item.issued_on or '-'}",
        f"domain {domain}  thread {item.thread_number or '-'}  "
        f"answers {item.responds_to_number or '-'}",
        "answer "
        + (f"expected by {item.response_due or '-'}" if item.response_required else "not expected")
        + (f", given {item.responded_on}" if item.responded_on else ""),
    ]
    if technical:
        lines.append(f"record {item.id}")
    if item.delivery != "none":
        lines.append(f"delivery: {item.delivery}")
    if item.clocks:
        lines.append("clocks:")
        lines.extend(f"  {clock_line(c, technical=technical)}" for c in item.clocks)
    if suggestion is not None:
        lines.append("suggestion: " + suggestion_text(suggestion, shown))
    return lines


def clock_lines(
    clock: ClockView, labels: Labels | None = None, *, technical: bool = False
) -> list[str]:
    """The panel under the clocks table."""
    lines = [
        clock_line(clock, technical=technical),
        f"item {clock.item_number}  started {clock.start_on}  warns {clock.warn_days or '-'} "
        f"days before  restarts {clock.restarts}",
    ]
    if clock.owner:
        lines.append(f"owner {actor_label(_labels(labels), clock.owner)}")
    if clock.problem:
        lines.append(f"! {clock.problem}")
    return lines


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
