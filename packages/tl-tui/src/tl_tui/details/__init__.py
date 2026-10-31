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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tl_tui.client import ClientInterface
from tl_tui.display import DisplayMode, Labels, code_label, humanize
from tl_tui.layout import (
    Cell,
    Item,
    Page,
    Prop,
    Section,
    TableRow,
    cut_text,
    group_items,
    limited,
)

NOTE_LABEL = "Note"
NOTE_TEXT = "More details could not be loaded"
TECHNICAL_SECTION = "Technical details"
RECORD_SECTION = "Record"  # when the record was made and last changed
PANEL_TEXT_LIMIT = 300  # characters of a question, an answer or a message in a panel
PANEL_LIST_LIMITS = {"Timeline": 4, "Files": 3}  # rows of these sections in a panel


@dataclass(frozen=True)
class DetailRow:
    label: str
    value: str
    technical: bool = False  # shown only in technical mode
    section: str = ""  # the heading it sits under; "" is a group without a heading
    panel: bool = True  # False: on the record screen only, not in a panel under a log
    columns: tuple[str, ...] = ()  # a table row: the headings of its table...
    cells: tuple[Cell | str, ...] = ()  # ...and its cells (the label and value are then unused)


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
    from tl_tui.details.generic import generic_rows, offline_rows  # noqa: PLC0415

    _load_renderers()
    renderer = _RENDERERS.get(str(record.get("type")))
    if renderer is None:
        rows = generic_rows(record, labels)
    else:
        try:
            rows = renderer(client, project, record, labels)
        except Exception:  # noqa: BLE001  a renderer must never take the screen down
            rows = [*generic_rows(record, labels), DetailRow(NOTE_LABEL, NOTE_TEXT)]
    if mode.technical:  # one read of the record types per call; plain mode never reads them
        rows = [*rows, *offline_rows(client, str(record.get("type")))]
    return [row for row in rows if mode.technical or not row.technical]


def table_rows(
    section: str,
    columns: tuple[str, ...],
    rows: Sequence[Sequence[Cell | str]],
    *,
    technical: bool = False,
) -> list[DetailRow]:
    """The rows of a small table in ``section``: a dim header row, then one line per row."""
    return [
        DetailRow("", "", technical, section, columns=columns, cells=tuple(cells)) for cells in rows
    ]


def _item(row: DetailRow, *, panel: bool) -> Item:
    if row.cells:
        return TableRow(row.columns, row.cells)
    if row.label:
        return Prop(row.label, row.value)
    return cut_text(row.value, PANEL_TEXT_LIMIT) if panel else row.value


def rows_page(
    rows: list[DetailRow],
    *,
    identity: str = "",
    state: str = "",
    summary: str = "",
    technical: bool = False,
    panel: bool = False,
) -> Page:
    """The rows as a ``Page`` of sections, in order of first appearance.

    Technical rows are left out unless ``technical``. A ``panel`` also leaves out the rows that
    are for the record screen only, cuts long text at a word, and shortens the lists named in
    ``PANEL_LIST_LIMITS`` to their first rows and a ``… n more`` line.
    """
    shown = [row for row in rows if (technical or not row.technical) and (row.panel or not panel)]
    grouped = group_items((row.section, _item(row, panel=panel)) for row in shown)
    if panel:
        grouped = tuple(
            Section(
                section.heading,
                limited(section.items, PANEL_LIST_LIMITS.get(section.heading.split(" (")[0])),
                section.note,
            )
            for section in grouped
        )
    return Page(identity, state, grouped, summary if panel else "")


FILE_COLUMNS = ("Name", "Type", "Size", "Pages")
FILE_COLUMNS_NO_PAGES = ("Name", "Type", "Size")
LINK_COLUMNS = ("Relation", "Record", "Title", "Status")


def file_rows(
    client: ClientInterface, record_id: str, pages: Mapping[str, int | None] | None = None
) -> list[DetailRow]:
    """The ``Files (n)`` section as a small table (name, type, size, and the page count when some
    file's is known from ``pages``, a SHA-256 to count map); ``No files`` when there is none or the
    client cannot say."""
    from tl_tui.errors import CLIENT_ERRORS  # noqa: PLC0415
    from tl_tui.file_text import file_kind, file_pages, human_size  # noqa: PLC0415

    try:
        files = client.list_record_files(record_id)
    except (*CLIENT_ERRORS, NotImplementedError):
        files = []
    if not files:
        return [DetailRow("", "No files", section="Files")]
    known = pages or {}
    counts = [known.get(info.sha256) for info in files]
    with_pages = any(count for count in counts)
    table = [
        (
            info.filename,
            file_kind(info.content_type, info.filename),
            human_size(info.size),
            *((file_pages(count),) if with_pages else ()),
        )
        for info, count in zip(files, counts, strict=True)
    ]
    columns = FILE_COLUMNS if with_pages else FILE_COLUMNS_NO_PAGES
    return table_rows(f"Files ({len(files)})", columns, table)


def link_rows(client: ClientInterface, record_id: str) -> list[DetailRow]:
    """The ``Links (n)`` section as a small table (relation, the record at the other end, its
    title, the link's status; a stale link in red); ``No links`` when there is none or the client
    cannot say. A retracted link is not listed."""
    from tl_tui.errors import CLIENT_ERRORS  # noqa: PLC0415
    from tl_tui.layout import state_style  # noqa: PLC0415
    from tl_tui.text import EMPTY  # noqa: PLC0415
    from tl_tui.widgets.links_tab import status_text  # noqa: PLC0415

    try:
        links = client.links_of(record_id)
    except (*CLIENT_ERRORS, NotImplementedError):
        links = []
    if not links:
        return [DetailRow("", "No links", section="Links")]
    table = []
    for link in links:
        status = status_text(link)
        table.append(
            (
                link.label,
                link.other_key or EMPTY,
                link.other_title or EMPTY,
                Cell(status, state_style(status)),
            )
        )
    return table_rows(f"Links ({len(links)})", LINK_COLUMNS, table)


def since_of(client: ClientInterface, record_id: str) -> str | None:
    """The day the record entered its state (``2026-10-13``), or ``None`` when it has no workflow
    or the client cannot say."""
    from tl_tui.errors import CLIENT_ERRORS  # noqa: PLC0415

    try:
        entered = client.workflow_status(record_id).entered_at
    except (*CLIENT_ERRORS, NotImplementedError):
        return None
    return str(entered)[:10] if entered else None


def record_rows(record: dict[str, Any]) -> list[DetailRow]:
    """The ``Record`` section: when the record was created and last updated (not in a panel)."""
    from tl_tui.text import timestamp  # noqa: PLC0415

    return [
        DetailRow(
            "Created", timestamp(record.get("created_at")), section=RECORD_SECTION, panel=False
        ),
        DetailRow(
            "Updated", timestamp(record.get("updated_at")), section=RECORD_SECTION, panel=False
        ),
    ]


def plain_code(labels: Labels, list_name: str, code: str | None) -> str:
    """The code's label; a lower-case code the list does not know reads as a word
    (``internal`` becomes ``Internal``); ``—`` for none."""
    text = code_label(labels, list_name, code)
    return humanize(text) if code and text == code and code.isalpha() and code.islower() else text
