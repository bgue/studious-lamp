"""The one renderer of a record's panel and Details tab (P1-UX3; skill ``tui-layout``).

A panel under a log and the Details tab of a record screen are a stack of named sections. The
panel starts with an identity line (``number · subject``) and a state line; the Details tab leaves
those to the record screen's header. Under them come the sections, each a heading line, its lines,
and one blank line before the next heading. Every value that is not the identity or the state is a
property line ``Label  value`` with the values of one section lined up on one column (the longest
label plus two spaces, labels cut at 24 characters wrap their value to the next line).

Pure functions and small dataclasses; no widget, no client. A record type builds a ``Page`` once
and both its panel and its Details tab render it, so the two never differ in order or wording.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from rich.cells import cell_len
from rich.text import Text

EMPTY = "—"
LABEL_CAP = 24  # the widest label column; a longer label puts its value on the next line
GAP = 2  # cells between the label column and the values
CUT_NOTE = "… (Enter for all)"

IDENTITY_STYLE = "bold"
HEADING_STYLE = "bold grey62"
LABEL_STYLE = "dim"
SUMMARY_JOIN = " · "
SUMMARY_WIDTH = 56  # the longest summary line: a panel beside a log is about 58 cells wide

# State colour (skill ``tui-layout``): green done, amber waiting or running, red overdue or refused.
# The terminal's own palette colours, so a theme sets the exact shade; the word is always there.
DONE_STYLE = "green"
WAITING_STYLE = "yellow"
BAD_STYLE = "red"
_BAD = re.compile(
    r"\b(overdue|late|refused|rejected|failed|expired|killed|breached|nonconformant|disputed)\b"
    r"|does not fit",
    re.I,
)
_DONE = re.compile(
    r"\b(answered|closed|done|complete|completed|met|accepted|approved|issued|responded|"
    r"published|applied|current|agreed)\b",
    re.I,
)
_WAITING = re.compile(
    r"\b(awaiting|waiting|running|review|submitted|received|paused|pending|processing|uploaded|"
    r"proposed|assessment)\b",
    re.I,
)


@dataclass(frozen=True)
class Prop:
    """One property line: ``Needed by      2026-10-23``."""

    label: str
    value: str = ""


@dataclass(frozen=True)
class Cell:
    """A table cell with a style (a state colour); a plain ``str`` cell has none."""

    text: str
    style: str = ""


@dataclass(frozen=True)
class TableRow:
    """One row of a small table. Consecutive rows with the same ``columns`` in one section are
    drawn as one table: a dim header row, then the rows, cells lined up on the widest."""

    columns: tuple[str, ...]
    cells: tuple[Cell | str, ...]


Item = Prop | str | TableRow  # a str is a line of prose or a list entry, printed as it is


@dataclass(frozen=True)
class Section:
    """A named group. ``note`` is the one line shown when the group has no items (``No files``)."""

    heading: str
    items: tuple[Item, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class Page:
    """What a panel or a Details tab shows, top to bottom."""

    identity: str = ""
    state: str = ""
    sections: tuple[Section, ...] = ()
    summary: str = ""  # a panel only: the decision facts joined with `SUMMARY_JOIN`


def shown(value: object) -> str:
    """The value as a reader sees it: ``—`` for none and for an empty text."""
    if value is None:
        return EMPTY
    text = str(value)
    return text if text.strip() else EMPTY


def prop(label: str, value: object) -> Prop:
    """A property line whose empty value reads ``—``."""
    return Prop(label, shown(value))


def join_facts(*facts: object) -> str:
    """The panel's summary: the facts that are not empty, joined with `` · ``
    (``Structural · needed by 2026-10-22 · to Meridian``)."""
    return SUMMARY_JOIN.join(str(f) for f in facts if f is not None and str(f).strip())


def wrap_facts(summary: str, width: int = SUMMARY_WIDTH) -> list[str]:
    """The summary in lines of at most ``width`` characters, broken between facts (at `` · ``),
    never inside one; a fact longer than ``width`` is a line of its own."""
    lines: list[str] = []
    for fact in summary.split(SUMMARY_JOIN):
        if lines and len(lines[-1]) + len(SUMMARY_JOIN) + len(fact) <= width:
            lines[-1] += SUMMARY_JOIN + fact
        else:
            lines.append(fact)
    return lines


def state_style(text: str) -> str:
    """The colour of a state: green done (answered, closed, met, issued), amber waiting or running,
    red overdue, late or refused; none for a state that is none of these (a draft, void).

    Red wins over green over amber, so ``Answer rejected`` is red. A mark leads some cells
    (``✓ on``, ``! failed``, ``… waiting``) and decides first.
    """
    stripped = text.strip()
    if stripped.startswith("!"):  # a warning is amber, a failure red
        return WAITING_STYLE if re.search(r"\bwarn", stripped, re.I) else BAD_STYLE
    if stripped.startswith("✗"):  # a cross is a failure, except "off" and "retired" (not a fault)
        return "" if re.search(r"\b(off|retired)\b", stripped) else BAD_STYLE
    if stripped.startswith("✓"):
        return DONE_STYLE
    if stripped.startswith("…"):
        return WAITING_STYLE
    if _BAD.search(stripped):
        return BAD_STYLE
    if _DONE.search(stripped):
        return DONE_STYLE
    if _WAITING.search(stripped):
        return WAITING_STYLE
    return ""


def identity_line(number: str, title: str) -> str:
    """``P123-RFI-0328 · Conflict in piling and utilities``; the number alone without a title."""
    return f"{number} · {title}" if title else number


def state_line(state: str, since: str | None = None) -> str:
    """``Awaiting response · since 2026-10-13``."""
    return f"{state} · since {since}" if since else state


def cut_text(text: str, limit: int) -> str:
    """``text`` as it is when it fits in ``limit`` characters, else cut at a word and ended with
    ``… (Enter for all)``."""
    flat = text.strip()
    if len(flat) <= limit:
        return flat
    head = flat[:limit].rsplit(None, 1)[0] if " " in flat[:limit] else flat[:limit]
    return head.rstrip(" ,;:.-") + CUT_NOTE


def more_note(count: int) -> str:
    """The closing line of a list cut short: ``… 3 more (Enter for all)``."""
    return f"… {count} more (Enter for all)"


def limited(items: Sequence[Item], limit: int | None) -> tuple[Item, ...]:
    """The first ``limit`` items (all when ``limit`` is None) and a ``… n more`` line after them."""
    if limit is None or len(items) <= limit:
        return tuple(items)
    return (*items[:limit], more_note(len(items) - limit))


# --- rendering -------------------------------------------------------------------------------

Segment = tuple[str, str]  # (text, style)
Line = list[Segment]


def _prop_lines(props: Sequence[Prop]) -> list[Line]:
    """Lines for consecutive properties, values on one column."""
    width = min(max((len(p.label) for p in props), default=0), LABEL_CAP) + GAP
    lines: list[Line] = []
    for p in props:
        first, *more = p.value.split("\n") if p.value else [""]
        pad = " " * width
        if len(p.label) > LABEL_CAP:  # too long to line up: the value goes under it
            lines.append([(p.label, LABEL_STYLE)])
            lines.append([(pad + first, "")])
        else:
            gap = " " * (width - len(p.label))
            line: Line = [(p.label, LABEL_STYLE)]
            if first:
                line.append((gap + first, ""))
            lines.append(line)
        lines.extend([(pad + rest, "")] for rest in more)
    return lines


def _pad(text: str, width: int) -> str:
    return text + " " * max(width - cell_len(text), 0)


def _table_lines(rows: Sequence[TableRow]) -> list[Line]:
    """A small table: a dim header row, then one line per row; every column but the last as wide as
    its widest cell, two cells between columns. A cell may carry a state colour."""
    columns = rows[0].columns
    body = [[c if isinstance(c, Cell) else Cell(c) for c in row.cells] for row in rows]
    widths = [cell_len(name) for name in columns]
    for cells in body:
        for index, cell in enumerate(cells[: len(widths)]):
            widths[index] = max(widths[index], cell_len(cell.text))
    gap = " " * GAP
    last = len(widths) - 1
    head: Line = []
    for index, name in enumerate(columns):
        head.append((name if index == last else _pad(name, widths[index]) + gap, LABEL_STYLE))
    lines: list[Line] = [head]
    for cells in body:
        line: Line = []
        for index, cell in enumerate(cells[: len(widths)]):
            if index == last:
                line.append((cell.text, cell.style))
            else:  # colour the word, not the padding after it
                line.append((cell.text, cell.style))
                line.append((_pad("", widths[index] - cell_len(cell.text)) + gap, ""))
        lines.append(line)
    return lines


def _section_lines(section: Section) -> list[Line]:
    lines: list[Line] = []
    if section.heading:
        lines.append([(section.heading, HEADING_STYLE)])
    items = section.items or ((section.note,) if section.note else ())
    props: list[Prop] = []
    table: list[TableRow] = []

    def flush() -> None:
        nonlocal props, table
        if props:
            lines.extend(_prop_lines(props))
            props = []
        if table:
            lines.extend(_table_lines(table))
            table = []

    for item in items:
        if isinstance(item, Prop):
            if table:
                flush()
            props.append(item)
        elif isinstance(item, TableRow):
            if props or (table and table[0].columns != item.columns):
                flush()
            table.append(item)
        else:
            flush()
            lines.extend([(text, "")] for text in item.split("\n"))
    flush()
    return lines


def table_text(rows: Sequence[TableRow], selected: int | None = None) -> Text:
    """A table on its own (no section around it) as styled text; the row ``selected`` (counted
    from the first row under the header) is shown reversed."""
    text = Text()
    for index, line in enumerate(_table_lines(rows)):
        if index:
            text.append("\n")
        for part, style in line:
            if selected is not None and index == selected + 1:
                style = f"{style} reverse".strip()
            text.append(part, style=style or None)
    return text


def state_segments(state: str) -> Line:
    """The state line as segments: the state in its colour, then what follows it (``since``, an
    ``overdue 3 days`` in red) in its own."""
    first, *rest = state.split(SUMMARY_JOIN)
    line: Line = [(first, state_style(first))]
    for part in rest:
        line.append((SUMMARY_JOIN + part, BAD_STYLE if _BAD.search(part) else ""))
    return line


def page_lines(page: Page, *, identity: bool = True) -> list[Line]:
    """The page as lines of styled segments. ``identity=False`` leaves out the identity, state and
    summary lines (the Details tab: the record screen's header already shows them)."""
    lines: list[Line] = []
    if identity and page.identity:
        lines.append([(page.identity, IDENTITY_STYLE)])
    if identity and page.state:
        lines.append(state_segments(page.state))
    if identity and page.summary:
        lines.extend([(row, LABEL_STYLE)] for row in wrap_facts(page.summary))
    blocks = [_section_lines(section) for section in page.sections]
    for block in blocks:
        if not block:
            continue
        if lines:
            lines.append([])  # one blank line before a heading
        lines.extend(block)
    return lines


def plain_lines(page: Page, *, identity: bool = True) -> list[str]:
    """The page as plain text lines (what a monochrome terminal or a test reads)."""
    lines = page_lines(page, identity=identity)
    return ["".join(text for text, _ in line).rstrip() for line in lines]


def render(page: Page, *, identity: bool = True) -> Text:
    """The page as one styled ``Text``; its ``plain`` is ``plain_lines`` joined by newlines."""
    text = Text()
    for index, line in enumerate(page_lines(page, identity=identity)):
        if index:
            text.append("\n")
        for part, style in line:
            text.append(part, style=style or None)
    return text


def group_items(entries: Iterable[tuple[str, Item]]) -> tuple[Section, ...]:
    """Sections from ``(section heading, item)`` pairs, in order of first appearance."""
    order: list[str] = []
    items: dict[str, list[Item]] = {}
    for heading, item in entries:
        if heading not in items:
            order.append(heading)
            items[heading] = []
        items[heading].append(item)
    return tuple(Section(heading, tuple(items[heading])) for heading in order)


def group_rows(rows: Iterable[tuple[str, str, str]]) -> tuple[Section, ...]:
    """Sections from ``(section heading, label, value)`` rows, in order of first appearance.

    A row with an empty label is a line of text under the heading (prose, a list entry); a row
    with a label is a property line.
    """
    return group_items(
        (heading, Prop(label, value) if label else value) for heading, label, value in rows
    )
