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

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from rich.text import Text

EMPTY = "—"
LABEL_CAP = 24  # the widest label column; a longer label puts its value on the next line
GAP = 2  # cells between the label column and the values
CUT_NOTE = "… (Enter for all)"

IDENTITY_STYLE = "bold"
HEADING_STYLE = "bold grey62"
LABEL_STYLE = "dim"


@dataclass(frozen=True)
class Prop:
    """One property line: ``Needed by      2026-10-23``."""

    label: str
    value: str = ""


Item = Prop | str  # a str is a line of prose or a list entry, printed as it is


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


def shown(value: object) -> str:
    """The value as a reader sees it: ``—`` for none and for an empty text."""
    if value is None:
        return EMPTY
    text = str(value)
    return text if text.strip() else EMPTY


def prop(label: str, value: object) -> Prop:
    """A property line whose empty value reads ``—``."""
    return Prop(label, shown(value))


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


def _section_lines(section: Section) -> list[Line]:
    lines: list[Line] = []
    if section.heading:
        lines.append([(section.heading, HEADING_STYLE)])
    items = section.items or ((section.note,) if section.note else ())
    run: list[Prop] = []
    for item in items:
        if isinstance(item, Prop):
            run.append(item)
            continue
        if run:
            lines.extend(_prop_lines(run))
            run = []
        lines.extend([(text, "")] for text in item.split("\n"))
    if run:
        lines.extend(_prop_lines(run))
    return lines


def page_lines(page: Page, *, identity: bool = True) -> list[Line]:
    """The page as lines of styled segments. ``identity=False`` leaves out the identity and state
    lines (the Details tab: the record screen's header already shows them)."""
    lines: list[Line] = []
    if identity and page.identity:
        lines.append([(page.identity, IDENTITY_STYLE)])
    if identity and page.state:
        lines.append([(page.state, "")])
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


def group_rows(rows: Iterable[tuple[str, str, str]]) -> tuple[Section, ...]:
    """Sections from ``(section heading, label, value)`` rows, in order of first appearance.

    A row with an empty label is a line of text under the heading (prose, a list entry); a row
    with a label is a property line.
    """
    order: list[str] = []
    items: dict[str, list[Item]] = {}
    for heading, label, value in rows:
        if heading not in items:
            order.append(heading)
            items[heading] = []
        items[heading].append(Prop(label, value) if label else value)
    return tuple(Section(heading, tuple(items[heading])) for heading in order)
