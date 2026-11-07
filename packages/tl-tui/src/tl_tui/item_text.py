"""What the item library and its item panel show: pure functions (P2-I3-T06c; D25).

The rows, the panel and the summary line are text built from ``tl_mod_materials.views`` and
``views_detail`` models and nothing else: no Textual, no client call, no clock, no I/O. The
``ItemLibraryScreen`` mounts these functions and the web twin (``tl_web/present.py``) calls the same
ones, so the two never differ in columns, words or figures.

Quantities are ``Decimal`` in and text out (``materials_text.qty_text``). A missing value is ``—``
(``EMPTY``), never ``None`` and never a bare ``-``.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_mod_materials.views import MaterialItemView
from tl_mod_materials.views_detail import ItemProjectView

from tl_tui.display import Labels, humanize
from tl_tui.layout import (
    EMPTY,
    Page,
    Prop,
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

ITEM_COLUMNS: tuple[str, ...] = ("Number", "Subject", "State", "Category", "UOM", "Projects")
ITEM_DROP: tuple[str, ...] = ("Projects", "UOM", "Category")  # least needed first
RIGHT: frozenset[str] = frozenset({"Projects"})

ITEM_KEYS = "r state  / filter  F5 reload  Esc close"

PROJECT_COLUMNS: tuple[str, ...] = ("Project", "On hand", "Reserved", "Available")
_STATES: tuple[str | None, ...] = (None, "Active", "Retired")


# --- the log ----------------------------------------------------------------


def columns_for(rows: Sequence[MaterialItemView]) -> tuple[str, ...]:
    """``ITEM_COLUMNS`` without each of State, Category, UOM and Projects whose value is the same
    in every row (Number and Subject always stay)."""
    drop: set[str] = set()
    if len({r.retired for r in rows}) <= 1:
        drop.add("State")
    if len({r.category for r in rows}) <= 1:
        drop.add("Category")
    if len({r.base_uom for r in rows}) <= 1:
        drop.add("UOM")
    if len({r.projects for r in rows}) <= 1:
        drop.add("Projects")
    return tuple(column for column in ITEM_COLUMNS if column not in drop)


def row_cells(
    view: MaterialItemView,
    columns: Sequence[str],
    labels: Labels | None = None,
    *,
    technical: bool = False,
) -> tuple[str, ...]:
    """The cells of one item in the order of ``columns``. ``labels`` names the category;
    ``technical`` does not change a cell (the log has no technical-only column)."""
    return tuple(_cell(view, column, labels) for column in columns)


def _cell(view: MaterialItemView, column: str, labels: Labels | None) -> str:
    if column == "Number":
        return _shown(view.code)
    if column == "Subject":
        return _shown(view.title)
    if column == "State":
        return _state_word(view)
    if column == "Category":
        return _category(view.category, labels)
    if column == "UOM":
        return _shown(unit_label(view.base_uom))
    if column == "Projects":
        return str(view.projects)
    raise ValueError(f"no item column {column!r}")


def _state_word(view: MaterialItemView) -> str:
    return "Retired" if view.retired else "Active"


def _category(category: str, labels: Labels | None) -> str:
    """The category's label from the code list when ``labels`` knows it, else the humanized word."""
    if not category.strip():
        return EMPTY
    known = labels.code_labels.get("ItemCategory", {}).get(category) if labels else None
    return known or humanize(category) or EMPTY


def summary_line(
    shown: int,
    total: int,
    *,
    state: str | None = None,
    project: str | None = None,
    text: str = "",
) -> str:
    """``Showing 12 of 50 items · Active · project P123 · filter "x"``; only set filters show."""
    parts = [f"Showing {shown} of {total} items"]
    if state:
        parts.append(state)
    if project:
        parts.append(f"project {project}")
    stripped = text.strip()
    if stripped:
        parts.append(f'filter "{stripped}"')
    return " · ".join(parts)


def next_state(current: str | None) -> str | None:
    """The state filter after ``current``: all (``None``), ``Active``, ``Retired``, then all."""
    index = _STATES.index(current) if current in _STATES else 0
    return _STATES[(index + 1) % len(_STATES)]


# --- the item panel ---------------------------------------------------------


def _specification(item: MaterialItemView, technical: bool) -> tuple[Prop, ...]:
    props: list[Prop] = [
        prop("Size", item.size_text),
        prop("Rating", item.rating_text),
        prop("Material", item.material_code),
        prop("Consumable", "Yes" if item.consumable else "No"),
    ]
    if technical:
        props.append(prop("Id", item.id))
    return tuple(props)


def _projects(projects: Sequence[ItemProjectView]) -> Section:
    return Section(
        "Projects",
        tuple(
            TableRow(
                PROJECT_COLUMNS,
                (
                    _shown(p.project),
                    qty_text(p.on_hand),
                    qty_text(p.reserved),
                    qty_text(p.available),
                ),
            )
            for p in projects
        ),
        note="" if projects else "Not used in any project",
    )


def _used_in(count: int) -> str:
    return f"used in {count} project" if count == 1 else f"used in {count} projects"


def item_page(
    item: MaterialItemView,
    projects: Sequence[ItemProjectView],
    labels: Labels | None = None,
    *,
    technical: bool = False,
) -> Page:
    """The item panel: identity ``<code> · <title>``, the state ``Active`` or ``Retired``, the
    summary (category, unit, how many projects use it), then Specification and Projects.
    ``technical`` adds the item id to Specification."""
    return Page(
        identity=identity_line(_shown(item.code), _shown(item.title)),
        state=_state_word(item),
        sections=(
            Section("Specification", _specification(item, technical)),
            _projects(projects),
        ),
        summary=join_facts(
            _category(item.category, labels),
            _shown(unit_label(item.base_uom)),
            _used_in(len(projects)),
        ),
    )


def item_lines(
    item: MaterialItemView,
    projects: Sequence[ItemProjectView],
    labels: Labels | None = None,
    *,
    technical: bool = False,
    width: int | None = None,
) -> list[str]:
    """The item panel as plain lines."""
    return plain_lines(item_page(item, projects, labels, technical=technical), width=width)
