# ruff: noqa: F401  (STUB P0-I8-T24: delete this line when the unused imports are gone)
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
from tl_tui.widgets.grid import GridColumn

CORE_TYPE = "core.Record"
MIN_WIDTH = 10
MAX_WIDTH = 24
NUMERIC_KINDS = ("int", "decimal")


def column_for(field: TypeFormField) -> GridColumn | None:
    """The column of one form field, or ``None`` when its value is not a pset value."""
    # Only a path that starts with "psets." has a cell. Width is len(label)+2 clamped to
    # MIN_WIDTH..MAX_WIDTH. Right-align a single-valued int or decimal. Use GridColumn(path,
    # label, width, align).
    raise NotImplementedError("STUB (P0-I8-T24)")


def columns_for_form(form: TypeForm) -> list[GridColumn]:
    """Key and Title, the form's grid columns that have a cell, then Status and Ver.

    Names in ``form.grid_columns`` that are not fields of the form are skipped, so are fields
    stored only in the body.
    """
    # Start with Key (width 12) and Title (width 18) GridColumns, then
    # column_for(form.field(name)) for each name in form.grid_columns that yields a column,
    # then Status (width 9) and Ver (width 3, right).
    raise NotImplementedError("STUB (P0-I8-T24)")


def _version_key(summary: TypeSummary) -> tuple[int, ...]:
    parts = summary.version.split(".")
    return tuple(int(p) if p.isdigit() else 0 for p in parts)


def newest_active(summaries: list[TypeSummary], type_name: str) -> TypeSummary | None:
    """The highest active version of ``type_name`` (``namespace.Name``), or ``None``."""
    # Compare versions with _version_key (given). Keep only summaries whose type_name
    # matches and status is "active".
    raise NotImplementedError("STUB (P0-I8-T24)")


def form_for_type(client: ClientInterface, record_type: str | None) -> TypeForm | None:
    """The form of the newest active version of ``record_type``, or ``None``.

    ``None`` for ``core.Record`` and for no type; also when no active version is registered, the
    version has no form (its files are unavailable) or the client refuses the question.
    """
    # None for no type or core.Record. Otherwise newest_active over
    # client.list_types("active"), then client.get_type(chosen.type_ref).form. Catch
    # CLIENT_ERRORS and answer None. Do not let any other exception hide.
    raise NotImplementedError("STUB (P0-I8-T24)")


def columns_for_type(client: ClientInterface, record_type: str | None) -> list[GridColumn] | None:
    """The columns for the grid of ``record_type``, or ``None`` to keep the default columns."""
    form = form_for_type(client, record_type)
    return None if form is None else columns_for_form(form)
