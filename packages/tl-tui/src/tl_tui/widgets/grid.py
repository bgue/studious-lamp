"""Data grid: virtualised record rows, cursor, sort, multi-select, TSV (brief 10.2, sketch 1).

`RecordGrid` renders only the visible lines (`ScrollView.render_line`) over rows fetched through
`ClientInterface.list_records` in pages. Sorting is client-side over the loaded rows, so a sort
first loads every page (up to `MAX_ROWS`). The grid posts `RecordHighlighted`, `SelectionChanged`,
`OpenRecord` and `StatusMessage`; it never talks to other widgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from rich.cells import cell_len, set_cell_size
from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.binding import Binding, BindingType
from textual.geometry import Size
from textual.scroll_view import ScrollView
from textual.strip import Strip
from tl_schema.forms import FormMetadata

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.messages import OpenRecord, RecordHighlighted, SelectionChanged, StatusMessage
from tl_tui.paths import pset_value
from tl_tui.text import CONFORMANCE_MARK, format_value, timestamp

MAX_ROWS = 50_000
MARKER_WIDTH = 5  # cursor mark, "[x]", and a space
GAP = " "

Align = Literal["left", "right"]


@dataclass(frozen=True)
class GridColumn:
    """One grid column. ``key`` is a record envelope key or a ``psets.…`` path."""

    key: str
    label: str
    width: int
    align: Align = "left"


DEFAULT_COLUMNS: tuple[GridColumn, ...] = (
    GridColumn("key", "Key", 12),
    GridColumn("title", "Title", 18),
    GridColumn("status", "Status", 9),
    GridColumn("version", "Ver", 3, "right"),
    GridColumn("conformance", "Conformance", 15),
)

CORE_COLUMNS: tuple[GridColumn, ...] = (
    *DEFAULT_COLUMNS,
    GridColumn("type", "Type", 12),
    GridColumn("description", "Description", 24),
    GridColumn("updated_at", "Updated", 16),
    GridColumn("created_at", "Created", 16),
)


def available_columns(meta: FormMetadata | None) -> list[GridColumn]:
    """Every column a user may show: the core ones plus one per pset property in ``meta``."""
    columns = list(CORE_COLUMNS)
    if meta is not None:
        for group in meta.psets:
            for fld in group.fields:
                columns.append(GridColumn(fld.path, fld.path.removeprefix("psets."), 14))
    return columns


def cell_text(record: dict[str, Any], column: GridColumn) -> str:
    """The display text of one cell. No colour carries meaning; status also reads as a symbol."""
    if column.key.startswith("psets."):
        return format_value(pset_value(record.get("psets") or {}, column.key))
    value = record.get(column.key)
    if column.key == "conformance":
        return CONFORMANCE_MARK.get(str(value), format_value(value))
    if column.key in ("updated_at", "created_at") and isinstance(value, str) and value:
        return timestamp(value)
    return format_value(value)


def sort_value(record: dict[str, Any], column: GridColumn) -> tuple[int, Any]:
    """Sort key: empty values last, numbers numerically, text case-insensitively."""
    if column.key.startswith("psets."):
        value = pset_value(record.get("psets") or {}, column.key)
    else:
        value = record.get(column.key)
    if value is None or value == "":
        return (2, 0)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (0, float(value))
    return (1, str(value).casefold())


def fit_cell(text: str, width: int, align: Align = "left") -> str:
    """``text`` cut with an ellipsis, or padded, to exactly ``width`` terminal cells."""
    text = text.replace("\t", " ").replace("\n", " ")
    if cell_len(text) > width:
        return set_cell_size(text, max(width - 1, 0)) + ("…" if width > 0 else "")
    padding = " " * (width - cell_len(text))
    return padding + text if align == "right" else text + padding


def to_tsv(columns: list[GridColumn], rows: list[dict[str, Any]]) -> str:
    """Header line plus one line per row, tab-separated, newline-terminated."""

    def clean(text: str) -> str:
        return text.replace("\t", " ").replace("\n", " ").replace("\r", " ")

    lines = ["\t".join(clean(c.label) for c in columns)]
    lines += ["\t".join(clean(cell_text(r, c)) for c in columns) for r in rows]
    return "\n".join(lines) + "\n"


class RecordGrid(ScrollView, can_focus=True):
    """Virtualised, sortable, multi-select grid of records of one scope and record type."""

    KEY_HINTS: ClassVar[str] = (
        "Enter open  Space select  Ctrl+A all  ←→ column  s sort  r reload  F6 panels"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "cursor(-1)", "Up", show=False),
        Binding("down", "cursor(1)", "Down", show=False),
        Binding("pageup", "page(-1)", "Page up", show=False),
        Binding("pagedown", "page(1)", "Page down", show=False),
        Binding("home", "cursor_to(0)", "First", show=False),
        Binding("end", "cursor_to_end", "Last", show=False),
        Binding("left", "column(-1)", "Column left", show=False),
        Binding("right", "column(1)", "Column right", show=False),
        Binding("space", "toggle_select", "Select", show=False),
        Binding("shift+up", "extend(-1)", "Extend up", show=False),
        Binding("shift+down", "extend(1)", "Extend down", show=False),
        Binding("ctrl+a", "select_all", "Select all", show=False),
        Binding("enter", "open", "Open", show=False),
        Binding("s", "sort", "Sort", show=False),
        Binding("r", "reload", "Reload", show=False),
    ]

    COMPONENT_CLASSES: ClassVar[set[str]] = {
        "grid--header",
        "grid--cursor",
        "grid--selected",
        "grid--column",
    }

    DEFAULT_CSS = """
    RecordGrid { height: 1fr; }
    RecordGrid > .grid--header { background: $panel; color: $text; text-style: bold; }
    RecordGrid > .grid--column { background: $primary; color: $text; text-style: bold; }
    RecordGrid > .grid--cursor { background: $accent 50%; }
    RecordGrid > .grid--selected { background: $primary 30%; }
    """

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        *,
        record_type: str | None = "core.Record",
        columns: list[GridColumn] | None = None,
        page_size: int = 200,
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(id=id)
        self.client = client
        self.scope = scope
        self.record_type = record_type
        self.columns: list[GridColumn] = list(columns or DEFAULT_COLUMNS)
        self.page_size = page_size
        self.rows: list[dict[str, Any]] = []
        self.exhausted = False
        self.cursor_row = 0
        self.column_cursor = 0
        self.selected_ids: set[str] = set()
        self.sort_key: str | None = None
        self.sort_descending = False

    # --- data --------------------------------------------------------------------------------

    def on_mount(self) -> None:
        self.load()

    def _fetch(self, limit: int, offset: int) -> list[dict[str, Any]]:
        try:
            return self.client.list_records(
                self.scope, record_type=self.record_type, limit=limit, offset=offset
            )
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return []

    def load(self, *, keep_id: str | None = None) -> None:
        """Replace the rows with the first page in server order and drop any sort."""
        self.sort_key = None
        self.sort_descending = False
        count = max(self.page_size, len(self.rows)) if keep_id else self.page_size
        self.rows = self._fetch(count, 0)
        self.exhausted = len(self.rows) < count
        self.cursor_row = 0
        if keep_id is not None:
            self._move_to_id(keep_id)
        self._after_rows_changed()

    def reload(self) -> None:
        """Re-read the rows, keeping the cursor on the same record when it still exists."""
        current = self.cursor_record
        self.load(keep_id=None if current is None else current["id"])

    def _move_to_id(self, record_id: str) -> None:
        for index, row in enumerate(self.rows):
            if row["id"] == record_id:
                self.cursor_row = index
                return

    def _load_more(self) -> None:
        if self.exhausted or len(self.rows) >= MAX_ROWS:
            return
        page = self._fetch(self.page_size, len(self.rows))
        self.rows.extend(page)
        if len(page) < self.page_size:
            self.exhausted = True
        self._update_virtual_size()

    def _load_all(self) -> None:
        while not self.exhausted and len(self.rows) < MAX_ROWS:
            before = len(self.rows)
            self._load_more()
            if len(self.rows) == before:
                self.exhausted = True

    def _after_rows_changed(self) -> None:
        self._update_virtual_size()
        self.refresh()
        self._announce_cursor()

    def _update_virtual_size(self) -> None:
        width = MARKER_WIDTH + sum(c.width for c in self.columns) + len(GAP) * len(self.columns)
        self.virtual_size = Size(width, len(self.rows) + 1)

    # --- cursor and queries ------------------------------------------------------------------

    @property
    def cursor_record(self) -> dict[str, Any] | None:
        if 0 <= self.cursor_row < len(self.rows):
            return self.rows[self.cursor_row]
        return None

    def selected_records(self) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["id"] in self.selected_ids]

    def neighbor_key(self, key: str, delta: int) -> str | None:
        """The key ``delta`` rows from ``key`` in the loaded list, or ``None`` at either end."""
        for index, row in enumerate(self.rows):
            if row["key"] == key:
                target = index + delta
                if target == len(self.rows) and not self.exhausted:
                    self._load_more()
                if 0 <= target < len(self.rows):
                    return str(self.rows[target]["key"])
                return None
        return None

    def copy_text(self) -> str:
        """TSV of the selected rows, or of the cursor row when nothing is selected."""
        rows = self.selected_records() or ([self.cursor_record] if self.cursor_record else [])
        return to_tsv(self.columns, rows)

    def summary(self) -> str:
        """One line for a status area: "47 rows · sorted Key ▲ · 2 selected"."""
        more = "+" if not self.exhausted else ""
        parts = [f"{len(self.rows)}{more} rows"]
        if self.sort_key is not None:
            label = next((c.label for c in self.columns if c.key == self.sort_key), self.sort_key)
            parts.append(f"sorted {label} {'▼' if self.sort_descending else '▲'}")
        if self.selected_ids:
            parts.append(f"{len(self.selected_ids)} selected")
        return " · ".join(parts)

    def set_columns(self, columns: list[GridColumn]) -> None:
        self.columns = list(columns) or list(DEFAULT_COLUMNS)
        self.column_cursor = min(self.column_cursor, len(self.columns) - 1)
        if self.sort_key not in {c.key for c in self.columns}:
            self.sort_key = None
        self._update_virtual_size()
        self.refresh()

    def _announce_cursor(self) -> None:
        self.post_message(RecordHighlighted(self.cursor_record))

    def _set_cursor(self, row: int) -> None:
        if not self.rows:
            return
        row = max(0, min(row, len(self.rows) - 1))
        if not self.exhausted and row >= len(self.rows) - max(self.page_size // 4, 1):
            self._load_more()
        changed = row != self.cursor_row
        self.cursor_row = row
        self._scroll_to_cursor()
        self.refresh()
        if changed:
            self._announce_cursor()

    def _scroll_to_cursor(self) -> None:
        visible = max(self.size.height - 1, 1)  # line 0 is the header
        top = int(self.scroll_offset.y)
        if self.cursor_row < top:
            self.scroll_to(y=self.cursor_row, animate=False)
        elif self.cursor_row >= top + visible:
            self.scroll_to(y=self.cursor_row - visible + 1, animate=False)

    # --- actions -----------------------------------------------------------------------------

    def action_cursor(self, delta: int) -> None:
        self._set_cursor(self.cursor_row + delta)

    def action_page(self, direction: int) -> None:
        self._set_cursor(self.cursor_row + direction * max(self.size.height - 2, 1))

    def action_cursor_to(self, row: int) -> None:
        self._set_cursor(row)

    def action_cursor_to_end(self) -> None:
        self._load_all()
        self._update_virtual_size()
        self._set_cursor(len(self.rows) - 1)

    def action_column(self, delta: int) -> None:
        self.column_cursor = max(0, min(self.column_cursor + delta, len(self.columns) - 1))
        self.refresh()

    def action_toggle_select(self) -> None:
        record = self.cursor_record
        if record is None:
            return
        self.selected_ids ^= {record["id"]}
        self._selection_changed()

    def action_extend(self, delta: int) -> None:
        record = self.cursor_record
        if record is None:
            return
        self.selected_ids.add(record["id"])
        self._set_cursor(self.cursor_row + delta)
        after = self.cursor_record
        if after is not None:
            self.selected_ids.add(after["id"])
        self._selection_changed()

    def action_select_all(self) -> None:
        self._load_all()
        self._update_virtual_size()
        self.selected_ids = {r["id"] for r in self.rows}
        self._selection_changed()

    def action_open(self) -> None:
        record = self.cursor_record
        if record is not None:
            self.post_message(OpenRecord(self.scope, str(record["key"])))

    def action_sort(self) -> None:
        self.sort_by(self.columns[self.column_cursor].key)

    def action_reload(self) -> None:
        self.reload()

    def _selection_changed(self) -> None:
        self.refresh()
        self.post_message(SelectionChanged(frozenset(self.selected_ids)))

    def sort_by(self, key: str) -> None:
        """Cycle ascending, descending, unsorted (server order) on column ``key``."""
        column = next((c for c in self.columns if c.key == key), None)
        if column is None:
            return
        if self.sort_key != key:
            self.sort_key, self.sort_descending = key, False
        elif not self.sort_descending:
            self.sort_descending = True
        else:
            self.reload()
            return
        current = self.cursor_record
        self._load_all()
        self.rows.sort(key=lambda r: sort_value(r, column), reverse=self.sort_descending)
        if self.sort_descending:  # keep empty values last when reversed
            self.rows.sort(key=lambda r: sort_value(r, column)[0] == 2)
        if current is not None:
            self._move_to_id(current["id"])
        self._update_virtual_size()
        self._scroll_to_cursor()
        self.refresh()

    # --- mouse -------------------------------------------------------------------------------

    def _column_at(self, x: int) -> int | None:
        start = MARKER_WIDTH
        for index, column in enumerate(self.columns):
            if start <= x < start + column.width:
                return index
            start += column.width + len(GAP)
        return None

    def on_click(self, event: events.Click) -> None:
        scroll_x = int(self.scroll_offset.x)
        scroll_y = int(self.scroll_offset.y)
        if event.y == 0:
            index = self._column_at(event.x + scroll_x)
            if index is not None:
                self.column_cursor = index
                self.sort_by(self.columns[index].key)
            return
        row = event.y - 1 + scroll_y
        if row >= len(self.rows):
            return
        self._set_cursor(row)
        if event.chain >= 2:
            self.action_open()

    # --- rendering ---------------------------------------------------------------------------

    def render_line(self, y: int) -> Strip:
        scroll_x = int(self.scroll_offset.x)
        scroll_y = int(self.scroll_offset.y)
        width = self.size.width
        base = self.rich_style
        if y == 0:
            segments = self._header_segments()
        else:
            index = y - 1 + scroll_y
            if index >= len(self.rows):
                return Strip.blank(width, base)
            segments = self._row_segments(index)
        strip = Strip(segments).crop(scroll_x, scroll_x + width)
        return strip.extend_cell_length(width, base)

    def _header_segments(self) -> list[Segment]:
        header = self.get_component_rich_style("grid--header")
        active = self.get_component_rich_style("grid--column")
        segments = [Segment(" " * MARKER_WIDTH, header)]
        for index, column in enumerate(self.columns):
            label = column.label
            if column.key == self.sort_key:
                label += " ▼" if self.sort_descending else " ▲"
            style = active if index == self.column_cursor and self.has_focus else header
            segments.append(Segment(fit_cell(label, column.width, column.align), style))
            segments.append(Segment(GAP, header))
        return segments

    def _row_segments(self, index: int) -> list[Segment]:
        record = self.rows[index]
        is_cursor = index == self.cursor_row
        is_selected = record["id"] in self.selected_ids
        style: Style = self.rich_style
        if is_selected:
            style = style + self.get_component_rich_style("grid--selected")
        if is_cursor:
            style = style + self.get_component_rich_style("grid--cursor")
        marker = f"{'▶' if is_cursor else ' '}{'[x]' if is_selected else '[ ]'} "
        segments = [Segment(marker, style)]
        for column in self.columns:
            segments.append(
                Segment(fit_cell(cell_text(record, column), column.width, column.align), style)
            )
            segments.append(Segment(GAP, style))
        return segments
