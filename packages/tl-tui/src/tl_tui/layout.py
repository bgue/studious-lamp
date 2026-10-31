"""The one renderer of a record's panel and Details tab (P1-UX3; skill ``tui-layout``).

A panel under a log and the Details tab of a record screen are a stack of named sections. The
panel starts with an identity line (``number · subject``) and a state line; the Details tab leaves
those to the record screen's header. Under them come the sections, each a heading line, its lines,
and one blank line before the next heading. Every value that is not the identity or the state is a
property line ``Label  value`` with the values of one section lined up on one column (the longest
label plus two spaces, labels cut at 24 characters wrap their value to the next line).

Pure functions and small dataclasses; no widget, no client. A record type builds a ``Page`` once
and both its panel and its Details tab render it, so the two never differ in order or wording.

A page adapts to the width it is drawn at (P1-UX3 round 3). ``render`` returns an ``Adaptive``: a
Rich renderable that lays the page out again at whatever width its widget has, so a resize re-flows
it with no help from the screen. The label column narrows with the panel, a value wraps under its
own start (a hanging indent), and a small table drops its least-needed column, then shortens a long
one with ``…``, before its last column wraps. ``.plain`` is the layout without a width limit.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from rich.cells import cell_len
from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text

EMPTY = "—"
LABEL_CAP = 24  # the widest label column; a longer label puts its value on the next line
GAP = 2  # cells between the label column and the values
CUT_NOTE = "… (Enter for all)"

IDENTITY_STYLE = "bold"
HEADING_STYLE = "bold grey62"
LABEL_STYLE = "dim"
SUMMARY_JOIN = " · "
SUMMARY_WIDTH = 56  # the longest summary line without a width: a panel beside a log is ~58 wide
MIN_LABEL = 8  # the narrowest label column a narrow panel squeezes to
MIN_VALUE = 12  # the narrowest value column; a narrower panel just overflows
SHORT_MIN = 8  # a shortened table column keeps at least this many cells
SHORT_COMFORT = 20  # a table drops a column before it shortens another below this
WRAP_MIN = 10  # the last column of a table wraps no narrower than this

# Small tables at a narrow width (skill ``tui-layout``, "Repeating rows"). Columns by name, so every
# table that uses a name follows the rule. ``DROP_FIRST`` is least needed first; ``SHORTENABLE``
# columns end in ``…`` when the table is still too wide; the last column wraps as a last resort.
DROP_FIRST: tuple[str, ...] = (
    "Files",
    "Pages",
    "Pin",
    "Size",
    "Days left",
    "Left",
    "Days",
    "Type",
    "Reached by",
    "Confidence",
)
SHORTENABLE: frozenset[str] = frozenset(
    {
        "Purpose",
        "Title",
        "Name",
        "Who",
        "Clock",
        "Label",
        "Property",
        "Value",
        "Record",
        "Path",
        "Message",
        "Note",
    }
)

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


def wrap_words(text: str, width: int | None, indent: int | None = None) -> list[str]:
    """``text`` in lines of at most ``width`` cells, broken between words; a word longer than a
    line is cut. Lines after the first start ``indent`` cells in (default: the text's own leading
    spaces). ``width`` None or too small leaves the text as one line."""
    if width is None or width < 2 or cell_len(text) <= width:
        return [text]
    lead = len(text) - len(text.lstrip(" "))
    hang = " " * (lead if indent is None else indent)
    lines: list[str] = []
    current = text[:lead]
    for word in text.strip(" ").split(" "):
        joined = f"{current}{' ' if current.strip() else ''}{word}"
        if cell_len(joined) <= width:
            current = joined
            continue
        if current.strip():
            lines.append(current)
            current = hang
        while cell_len(current + word) > width and len(word) > 1:  # a word wider than the line
            room = max(width - cell_len(current), 1)
            lines.append(current + word[:room])
            word, current = word[room:], hang
        current += word
    if current.strip():
        lines.append(current)
    return lines or [text]


def _prop_lines(props: Sequence[Prop], width: int | None = None) -> list[Line]:
    """Lines for consecutive properties, values on one column. At a ``width`` the label column
    narrows to two fifths of it (never below ``MIN_LABEL``), a label wider than the column puts its
    value on the next line, and a long value wraps under its own start."""
    label_w = min(max((len(p.label) for p in props), default=0), LABEL_CAP)
    if width is not None:
        label_w = min(label_w, max(MIN_LABEL, width * 2 // 5))
    column = label_w + GAP
    pad = " " * column
    room = None if width is None else max(width - column, MIN_VALUE)
    lines: list[Line] = []
    for p in props:
        parts = [
            part
            for chunk in (p.value.split("\n") if p.value else [""])
            for part in wrap_words(chunk, room, 0)
        ]
        first, *more = parts
        if len(p.label) > label_w:  # too long to line up: the value goes under it
            lines.append([(p.label, LABEL_STYLE)])
            lines.append([(pad + first, "")])
        else:
            line: Line = [(p.label, LABEL_STYLE)]
            if first:
                line.append((" " * (column - len(p.label)) + first, ""))
            lines.append(line)
        lines.extend([(pad + rest, "")] for rest in more)
    return lines


def _pad(text: str, width: int) -> str:
    return text + " " * max(width - cell_len(text), 0)


def shorten(text: str, width: int) -> str:
    """``text`` cut to ``width`` cells and ended with ``…`` when it is longer."""
    if cell_len(text) <= width:
        return text
    out = ""
    for char in text:
        if cell_len(out + char) > width - 1:
            break
        out += char
    return out.rstrip() + "…"


def _plan_columns(
    columns: Sequence[str], natural: list[int], width: int | None
) -> tuple[list[int], list[int]]:
    """Which columns a table keeps at ``width`` and how wide each is (indexes into ``columns``;
    widths by index). Order of resort: drop the least-needed column (``DROP_FIRST``) while the
    long columns could not keep ``SHORT_COMFORT`` cells, then shorten long columns (``SHORTENABLE``)
    down to ``SHORT_MIN``; whatever is still too wide is left to the last column to wrap."""
    keep = list(range(len(columns)))
    widths = list(natural)
    if width is None:
        return keep, widths

    def need(kept: list[int], floor: int) -> int:
        total = GAP * (len(kept) - 1)
        for i in kept:
            if columns[i] in SHORTENABLE:
                total += min(widths[i], max(floor, cell_len(columns[i])))
            else:
                total += widths[i]
        return total

    for name in DROP_FIRST:
        if need(keep, SHORT_COMFORT) <= width or len(keep) <= 2:
            break
        for i in keep[1:]:
            if columns[i] == name:
                keep.remove(i)
                break
    excess = need(keep, 10_000) - width
    while excess > 0:
        # shorten the widest long column that still has room above its floor
        roomy = [
            i
            for i in keep
            if columns[i] in SHORTENABLE and widths[i] > max(SHORT_MIN, cell_len(columns[i]))
        ]
        if not roomy:
            break
        widest = max(roomy, key=lambda i: widths[i])
        widths[widest] -= 1
        excess -= 1
    return keep, widths


def _table_groups(rows: Sequence[TableRow], width: int | None = None) -> list[list[Line]]:
    """A small table: a dim header row, then one line per row; every column but the last as wide as
    its widest cell, two cells between columns. A cell may carry a state colour. At a ``width`` a
    column may be dropped or shortened (``_plan_columns``) and the last column wraps under its own
    start."""
    names = rows[0].columns
    body = [[c if isinstance(c, Cell) else Cell(c) for c in row.cells] for row in rows]
    natural = [cell_len(name) for name in names]
    for cells in body:
        for index, cell in enumerate(cells[: len(natural)]):
            natural[index] = max(natural[index], cell_len(cell.text))
    keep, widths = _plan_columns(names, natural, width)
    gap = " " * GAP
    last = keep[-1]
    start = sum(widths[i] + GAP for i in keep[:-1])  # where the last column begins
    wrap = None if width is None else max(width - start, WRAP_MIN)
    head: Line = []
    for i in keep:
        head.append((names[i] if i == last else _pad(names[i], widths[i]) + gap, LABEL_STYLE))
    groups: list[list[Line]] = [[head]]  # the header, then one group of lines per row
    for cells in body:
        cells = [*cells, *[Cell("")] * (len(names) - len(cells))]
        line: Line = []
        extra: list[Line] = []
        for i in keep:
            cell = cells[i]
            text = shorten(cell.text, widths[i]) if widths[i] < natural[i] else cell.text
            if i == last:
                first, *rest = wrap_words(text, wrap, 0)
                line.append((first, cell.style))
                extra.extend([(" " * start, ""), (more, cell.style)] for more in rest)
            else:  # colour the word, not the padding after it
                line.append((text, cell.style))
                line.append((_pad("", widths[i] - cell_len(text)) + gap, ""))
        groups.append([line, *extra])
    return groups


def _table_lines(rows: Sequence[TableRow], width: int | None = None) -> list[Line]:
    return [line for group in _table_groups(rows, width) for line in group]


def _section_lines(section: Section, width: int | None = None) -> list[Line]:
    lines: list[Line] = []
    if section.heading:
        lines.append([(section.heading, HEADING_STYLE)])
    items = section.items or ((section.note,) if section.note else ())
    props: list[Prop] = []
    table: list[TableRow] = []

    def flush() -> None:
        nonlocal props, table
        if props:
            lines.extend(_prop_lines(props, width))
            props = []
        if table:
            lines.extend(_table_lines(table, width))
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
            for text in item.split("\n"):
                lines.extend([(part, "")] for part in wrap_words(text, width))
    flush()
    return lines


class Adaptive:
    """A page or table that lays itself out at the width it is drawn at.

    A Rich renderable: a Textual ``Static`` that shows it draws it again whenever its width
    changes. ``plain`` and ``text()`` are the layout without a width limit (what a test, the copy
    command and a monochrome terminal read); ``text(width)`` is the layout at that width.
    """

    def __init__(self, build: Callable[[int | None], list[Line]]) -> None:
        self._build = build

    def lines(self, width: int | None = None) -> list[Line]:
        return self._build(width)

    def text(self, width: int | None = None) -> Text:
        text = Text()
        for index, line in enumerate(self._build(width)):
            if index:
                text.append("\n")
            for part, style in line:
                text.append(part, style=style or None)
        return text

    @property
    def plain(self) -> str:
        return self.text().plain

    def __str__(self) -> str:
        return self.plain

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.text(options.max_width)


Panel = str | Text | Adaptive  # what a log's panel hook may return


def table_text(rows: Sequence[TableRow], selected: int | None = None) -> Adaptive:
    """A table on its own (no section around it); the row ``selected`` (counted from the first row
    under the header) is shown reversed."""

    def build(width: int | None) -> list[Line]:
        lines: list[Line] = []
        for index, group in enumerate(_table_groups(rows, width)):
            for line in group:
                if selected is not None and index == selected + 1:
                    line = [(t, f"{st} reverse".strip()) for t, st in line]  # noqa: PLW2901
                lines.append(line)
        return lines

    return Adaptive(build)


def state_segments(state: str) -> Line:
    """The state line as segments: the state in its colour, then what follows it (``since``, an
    ``overdue 3 days`` in red) in its own."""
    first, *rest = state.split(SUMMARY_JOIN)
    line: Line = [(first, state_style(first))]
    for part in rest:
        line.append((SUMMARY_JOIN + part, BAD_STYLE if _BAD.search(part) else ""))
    return line


def page_lines(page: Page, *, identity: bool = True, width: int | None = None) -> list[Line]:
    """The page as lines of styled segments. ``identity=False`` leaves out the identity, state and
    summary lines (the Details tab: the record screen's header already shows them)."""
    lines: list[Line] = []
    if identity and page.identity:
        lines.append([(page.identity, IDENTITY_STYLE)])
    if identity and page.state:
        lines.append(state_segments(page.state))
    if identity and page.summary:
        lines.extend(
            [(row, LABEL_STYLE)] for row in wrap_facts(page.summary, width or SUMMARY_WIDTH)
        )
    blocks = [_section_lines(section, width) for section in page.sections]
    for block in blocks:
        if not block:
            continue
        if lines:
            lines.append([])  # one blank line before a heading
        lines.extend(block)
    return lines


def plain_lines(page: Page, *, identity: bool = True, width: int | None = None) -> list[str]:
    """The page as plain text lines (what a monochrome terminal or a test reads)."""
    lines = page_lines(page, identity=identity, width=width)
    return ["".join(text for text, _ in line).rstrip() for line in lines]


def render(page: Page, *, identity: bool = True, lead: str = "", lead_style: str = "") -> Adaptive:
    """The page as a renderable that re-flows to the width it is shown at; its ``plain`` is
    ``plain_lines`` joined by newlines. ``lead`` is a line above the page, set off by a blank one
    (the schema screen's tab row)."""

    def build(width: int | None) -> list[Line]:
        lines = page_lines(page, identity=identity, width=width)
        return [[(lead, lead_style)], [], *lines] if lead else lines

    return Adaptive(build)


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
