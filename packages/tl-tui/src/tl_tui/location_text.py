"""What the storage locations log and its location panel show: pure functions (P2-I3-T06h; D25).

The rows, the panel and the summary line are text built from ``tl_mod_materials.views`` models
and nothing else: no Textual, no client call, no clock, no I/O. The ``LocationScreen`` mounts these
functions and the web twin (``tl_web/present.py``) calls the same ones, so the two never differ in
columns, words or figures.

Quantities are text (counts). A missing value is ``—`` (``EMPTY``), never ``None`` and never a bare
``-``. The Subject column is the title indented two spaces per tree depth; there are no tree glyphs.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from tl_mod_materials.views import LocationView, StockRowView

from tl_tui.display import Labels, humanize
from tl_tui.layout import (
    Page,
    Section,
    TableRow,
    identity_line,
    join_facts,
    plain_lines,
    prop,
)
from tl_tui.layout import (
    shown as _shown,
)
from tl_tui.materials_text import qty_text
from tl_tui.text import unit_label

LOCATION_COLUMNS: tuple[str, ...] = ("Number", "Subject", "Kind", "Lots", "Lines")
LOCATION_DROP: tuple[str, ...] = ("Lines", "Kind", "Lots")  # least needed first
RIGHT: frozenset[str] = frozenset({"Lots", "Lines"})

LOCATION_KEYS = "s stock here  / filter  F5 reload  Esc close"

CONTENT_COLUMNS: tuple[str, ...] = ("Lot", "Item", "On hand")
CHILD_COLUMNS: tuple[str, ...] = ("Code", "Title")
INDENT = "  "  # two spaces per tree depth in the Subject column
PATH_JOIN = " › "


# --- the list ---------------------------------------------------------------


def columns_for(rows: Sequence[LocationView]) -> tuple[str, ...]:
    """``LOCATION_COLUMNS`` without Kind, Lots and Lines when every row has the same value there.
    Number and Subject never drop."""
    drop: set[str] = set()
    if len({r.kind for r in rows}) <= 1:
        drop.add("Kind")
    if len({r.lots for r in rows}) <= 1:
        drop.add("Lots")
    if len({r.lines for r in rows}) <= 1:
        drop.add("Lines")
    return tuple(column for column in LOCATION_COLUMNS if column not in drop)


def row_cells(
    view: LocationView,
    columns: Sequence[str],
    labels: Labels | None = None,
    *,
    technical: bool = False,
) -> tuple[str, ...]:
    """The cells of one location in the order of ``columns``. ``labels`` and ``technical`` do not
    change a cell (the list has no coded value and no technical-only column)."""
    return tuple(_cell(view, column) for column in columns)


def _cell(view: LocationView, column: str) -> str:
    if column == "Number":
        return _shown(view.code)
    if column == "Subject":
        return INDENT * view.depth + _subject_name(view)
    if column == "Kind":
        return _shown(humanize(view.kind))
    if column == "Lots":
        return str(view.lots)
    if column == "Lines":
        return str(view.lines)
    raise ValueError(f"no location column {column!r}")


def _subject_name(view: LocationView) -> str:
    """The title, with ``(retired)`` after it for a retired location."""
    name = _shown(view.title)
    return f"{name} (retired)" if view.retired else name


def summary_line(shown: int, total: int, *, text: str = "") -> str:
    """``Showing 9 of 9 locations · filter "x"``; the filter is named only when it is set."""
    parts = [f"Showing {shown} of {total} locations"]
    stripped = text.strip()
    if stripped:
        parts.append(f'filter "{stripped}"')
    return " · ".join(parts)


# --- the location panel -----------------------------------------------------


def _parent_path(location: LocationView, locations: Sequence[LocationView]) -> str:
    """The codes from the root down to the parent, joined `` › ``, found by following
    ``parent_code`` through the loaded ``locations``. The walk stops at a cycle and after the first
    parent that is not loaded (that code is still named, as the last one reached)."""
    by_code = {row.code: row for row in locations}
    names: list[str] = []
    seen = {location.code}
    parent = location.parent_code
    while parent is not None and parent not in seen:
        seen.add(parent)
        names.append(parent)
        if parent not in by_code:
            break
        parent = by_code[parent].parent_code
    return PATH_JOIN.join(reversed(names))


def _with_unit(value: Decimal, uom: str) -> str:
    """``12 m``; the number alone when the unit is unknown."""
    return f"{qty_text(value)} {unit_label(uom)}".rstrip()


def location_page(
    location: LocationView,
    locations: Sequence[LocationView],
    stock: Sequence[StockRowView],
    labels: Labels | None = None,
    *,
    technical: bool = False,
) -> Page:
    """The location panel: identity ``code · title``, the state ``Active`` or ``Retired``, the
    summary (kind, parent path, lots), then Contents (the stock here) and Children. ``technical``
    adds the location id as a first section, Location."""
    kind = humanize(location.kind)
    where = f"{kind} under {_parent_path(location, locations)}" if location.parent_code else kind
    here = [row for row in stock if row.location == location.code]
    contents = Section(
        "Contents",
        tuple(
            TableRow(
                CONTENT_COLUMNS,
                (
                    _shown(row.heat_no or row.lot),
                    _shown(row.item_code),
                    _with_unit(row.on_hand, row.uom),
                ),
            )
            for row in here
        ),
        note="" if here else "No stock here",
    )
    children = [row for row in locations if row.parent_code == location.code]
    child_section = Section(
        "Children",
        tuple(
            TableRow(CHILD_COLUMNS, (_shown(child.code), _shown(child.title))) for child in children
        ),
        note="" if children else "No child locations",
    )
    sections: list[Section] = []
    if technical:
        sections.append(Section("Location", (prop("Id", location.id),)))
    sections.extend([contents, child_section])
    return Page(
        identity=identity_line(location.code, location.title),
        state="Retired" if location.retired else "Active",
        sections=tuple(sections),
        summary=join_facts(where, f"{location.lots} lots"),
    )


def location_lines(
    location: LocationView,
    locations: Sequence[LocationView],
    stock: Sequence[StockRowView],
    labels: Labels | None = None,
    *,
    technical: bool = False,
    width: int | None = None,
) -> list[str]:
    """The location panel as plain lines."""
    page = location_page(location, locations, stock, labels, technical=technical)
    return plain_lines(page, width=width)
