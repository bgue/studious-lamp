"""Grid columns for an extension record type (P0-I8, brief 31.1).

``form.yaml`` names the columns of a type's grid (``grid.columns``, slot names). A column can show
a slot only when its value is a pset value: every slot of a managed type, and the index fields of
an object-backed type. A slot that lives only in the stored body has no cell in the grid, so it is
left out here (the record view shows it).
"""

from __future__ import annotations

from tl_core.extypes.forms import TypeForm, TypeFormField
from tl_core.extypes.service import TypeSummary

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS
from tl_tui.widgets.grid import Align, GridColumn

CORE_TYPE = "core.Record"
MIN_WIDTH = 10
MAX_WIDTH = 24
NUMERIC_KINDS = ("int", "decimal")


def column_for(field: TypeFormField) -> GridColumn | None:
    """The column of one form field, or ``None`` when its value is not a pset value."""
    if not field.path.startswith("psets."):
        return None
    width = min(MAX_WIDTH, max(MIN_WIDTH, len(field.label) + 2))
    numeric = field.kind in NUMERIC_KINDS and not field.multivalued
    align: Align = "right" if numeric else "left"
    return GridColumn(field.path, field.label, width, align)


def columns_for_form(form: TypeForm) -> list[GridColumn]:
    """Key and Title, the form's grid columns that have a cell, then Status and Ver.

    Names in ``form.grid_columns`` that are not fields of the form are skipped, so are fields
    stored only in the body.
    """
    columns = [GridColumn("key", "Key", 12), GridColumn("title", "Title", 18)]
    for name in form.grid_columns:
        field = form.field(name)
        if field is None:
            continue
        column = column_for(field)
        if column is not None:
            columns.append(column)
    columns.append(GridColumn("status", "Status", 9))
    columns.append(GridColumn("version", "Ver", 3, "right"))
    return columns


def _version_key(summary: TypeSummary) -> tuple[int, ...]:
    parts = summary.version.split(".")
    return tuple(int(p) if p.isdigit() else 0 for p in parts)


def newest_active(summaries: list[TypeSummary], type_name: str) -> TypeSummary | None:
    """The highest active version of ``type_name`` (``namespace.Name``), or ``None``."""
    active = [s for s in summaries if s.type_name == type_name and s.status == "active"]
    if not active:
        return None
    return max(active, key=_version_key)


def form_for_type(client: ClientInterface, record_type: str | None) -> TypeForm | None:
    """The form of the newest active version of ``record_type``, or ``None``.

    ``None`` for ``core.Record`` and for no type; also when no active version is registered, the
    version has no form (its files are unavailable) or the client refuses the question.
    """
    if record_type is None or record_type == CORE_TYPE:
        return None
    try:
        chosen = newest_active(client.list_types("active"), record_type)
        if chosen is None:
            return None
        return client.get_type(chosen.type_ref).form
    except CLIENT_ERRORS:
        return None


def columns_for_type(client: ClientInterface, record_type: str | None) -> list[GridColumn] | None:
    """The columns for the grid of ``record_type``, or ``None`` to keep the default columns."""
    form = form_for_type(client, record_type)
    return None if form is None else columns_for_form(form)
