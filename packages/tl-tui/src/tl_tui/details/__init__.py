"""The Details tab as rows: one renderer per record type, the generic envelope rows otherwise.

A renderer is a function ``(client, project, record, labels) -> list[DetailRow]`` registered for
one or more record types with ``@register("documents.Document")``. Every module of this package
is imported once, the first time ``details_for`` runs, so a screen ticket adds one module here and
nothing else. ``details_for`` never raises: a renderer that fails gives the generic rows and one
note line. Rows marked ``technical`` are dropped unless the display mode is technical.

A row belongs to a named ``section`` (P1-UX3; skill ``tui-layout``). ``rows_page`` turns rows into a
``layout.Page``: a row with a label is a property line, a row without one is a line of text under
its section's heading. The Details tab and the panels under the logs render the same rows through
``tl_tui.layout``, a panel with ``panel=True`` (long text cut, long lists short, bookkeeping rows
left out).
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tl_tui.client import ClientInterface
from tl_tui.display import DisplayMode, Labels
from tl_tui.layout import Page, Section, cut_text, group_rows, limited

NOTE_LABEL = "Note"
NOTE_TEXT = "More details could not be loaded"
TECHNICAL_SECTION = "Technical details"
PANEL_TEXT_LIMIT = 300  # characters of a question, an answer or a message in a panel
PANEL_LIST_LIMITS = {"Timeline": 4, "Files": 3}  # rows of these sections in a panel


@dataclass(frozen=True)
class DetailRow:
    label: str
    value: str
    technical: bool = False  # shown only in technical mode
    section: str = ""  # the heading it sits under; "" is a group without a heading
    panel: bool = True  # False: on the record screen only, not in a panel under a log


DetailRenderer = Callable[[ClientInterface, str, dict[str, Any], Labels], list[DetailRow]]

_RENDERERS: dict[str, DetailRenderer] = {}
_loaded = False


def register(*record_types: str) -> Callable[[DetailRenderer], DetailRenderer]:
    """Register the decorated renderer for these record types (``module.Type``)."""

    def decorate(renderer: DetailRenderer) -> DetailRenderer:
        for record_type in record_types:
            _RENDERERS[record_type] = renderer
        return renderer

    return decorate


def _load_renderers() -> None:
    """Import every module of this package once."""
    global _loaded  # noqa: PLW0603
    if _loaded:
        return
    _loaded = True
    for info in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{info.name}")


def details_for(
    client: ClientInterface,
    project: str,
    record: dict[str, Any],
    labels: Labels,
    mode: DisplayMode,
) -> list[DetailRow]:
    """The rows for ``record``: its type's renderer, else the generic rows (technical by mode)."""
    from tl_tui.details.generic import generic_rows  # noqa: PLC0415

    _load_renderers()
    renderer = _RENDERERS.get(str(record.get("type")))
    if renderer is None:
        rows = generic_rows(record, labels)
    else:
        try:
            rows = renderer(client, project, record, labels)
        except Exception:  # noqa: BLE001  a renderer must never take the screen down
            rows = [*generic_rows(record, labels), DetailRow(NOTE_LABEL, NOTE_TEXT)]
    return [row for row in rows if mode.technical or not row.technical]


def rows_page(
    rows: list[DetailRow],
    *,
    identity: str = "",
    state: str = "",
    technical: bool = False,
    panel: bool = False,
) -> Page:
    """The rows as a ``Page`` of sections, in order of first appearance.

    Technical rows are left out unless ``technical``. A ``panel`` also leaves out the rows that
    are for the record screen only, cuts long text at a word, and shortens the lists named in
    ``PANEL_LIST_LIMITS`` to their first rows and a ``… n more`` line.
    """
    shown = [row for row in rows if (technical or not row.technical) and (row.panel or not panel)]
    grouped = group_rows(
        (
            row.section,
            row.label,
            cut_text(row.value, PANEL_TEXT_LIMIT) if panel and not row.label else row.value,
        )
        for row in shown
    )
    if panel:
        grouped = tuple(
            Section(
                section.heading,
                limited(section.items, PANEL_LIST_LIMITS.get(section.heading.split(" (")[0])),
                section.note,
            )
            for section in grouped
        )
    return Page(identity, state, grouped)


def file_rows(client: ClientInterface, record_id: str) -> list[DetailRow]:
    """The ``Files (n)`` section: one line per current file (name, kind, size); ``No files`` when
    there is none or the client cannot say."""
    from tl_tui.errors import CLIENT_ERRORS  # noqa: PLC0415
    from tl_tui.file_text import file_line  # noqa: PLC0415

    try:
        files = client.list_record_files(record_id)
    except (*CLIENT_ERRORS, NotImplementedError):
        files = []
    if not files:
        return [DetailRow("", "No files", section="Files")]
    heading = f"Files ({len(files)})"
    return [
        DetailRow("", file_line(info.filename, info.content_type, info.size), section=heading)
        for info in files
    ]


def since_of(client: ClientInterface, record_id: str) -> str | None:
    """The day the record entered its state (``2026-10-13``), or ``None`` when it has no workflow
    or the client cannot say."""
    from tl_tui.errors import CLIENT_ERRORS  # noqa: PLC0415

    try:
        entered = client.workflow_status(record_id).entered_at
    except (*CLIENT_ERRORS, NotImplementedError):
        return None
    return str(entered)[:10] if entered else None
