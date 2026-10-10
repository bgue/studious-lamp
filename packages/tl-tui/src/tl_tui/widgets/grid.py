"""Data grid: virtualised record rows, cursor, sort, multi-select, TSV (brief 10.2, sketch 1).

`RecordGrid` renders only the visible lines (`ScrollView.render_line`) over rows fetched through
`ClientInterface.list_records` in pages. Sorting is done by the server (`order_by`) and re-reads the
first page; End pages forward in a worker thread up to `END_CAP` rows. The grid posts
`RecordHighlighted`, `SelectionChanged`, `OpenRecord` and `StatusMessage`; it never talks to other
widgets.

Filter (P0-I4): `apply_filter(text)` switches the rows to `ClientInterface.query_records` and keeps
the match count from `count_records`; a syntax error is returned with its position and changes
nothing. Live updates: `refresh_live(ids)` re-reads the loaded rows on a worker thread, applies
them with `call_from_thread`, and marks the rows of `ids` with a bullet for `highlight_seconds`.
"""

from __future__ import annotations

import json
import time
from collections.abc import Collection
from dataclasses import dataclass
from functools import partial
from typing import Any, ClassVar, Literal

from rich.cells import cell_len, set_cell_size
from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.binding import Binding, BindingType
from textual.geometry import Size
from textual.scroll_view import ScrollView
from textual.strip import Strip
from tl_core.query import QuerySyntaxError
from tl_schema.forms import FormMetadata

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.messages import OpenRecord, RecordHighlighted, SelectionChanged, StatusMessage
from tl_tui.paths import pset_value
from tl_tui.text import CONFORMANCE_MARK, format_value, timestamp

END_CAP = 5_000  # rows the End key will load; beyond it the user narrows the list instead
# Envelope columns the server can order by (tl_core.services.queries.SORTABLE_COLUMNS).
SORTABLE_KEYS = frozenset({"key", "title", "status", "type", "created_at", "updated_at", "version"})
MARKER_WIDTH = 5  # cursor mark, "[x]", and a space
GAP = " "
CHANGED_MARK = "•"  # in the last marker cell: the row was changed by someone else a moment ago
HIGHLIGHT_SECONDS = 4.0

Align = Literal["left", "right"]


@dataclass(frozen=True)
class FilterResult:
    """What `RecordGrid.apply_filter` tells the filter bar.

    ``ok`` is false when nothing changed: ``message`` says why and, for a syntax error,
    ``position`` is the 0-based character offset the parser stopped at. ``count`` is the number of
    matching records (``None`` for a blank filter or a failure).
    """

    ok: bool
    count: int | None = None
    message: str = ""
    position: int | None = None


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


def raw_text(record: dict[str, Any], column: GridColumn) -> str:
    """The stored value as plain text without display symbols (``""`` when empty)."""
    if column.key.startswith("psets."):
        value = pset_value(record.get("psets") or {}, column.key)
    else:
        value = record.get(column.key)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def fit_cell(text: str, width: int, align: Align = "left") -> str:
    """``text`` cut with an ellipsis, or padded, to exactly ``width`` terminal cells."""
    text = text.replace("\t", " ").replace("\n", " ")
    if cell_len(text) > width:
        return set_cell_size(text, max(width - 1, 0)) + ("…" if width > 0 else "")
    padding = " " * (width - cell_len(text))
    return padding + text if align == "right" else text + padding


def to_tsv(columns: list[GridColumn], rows: list[dict[str, Any]]) -> str:
    """Header line plus one line per row of raw values, tab-separated, newline-terminated."""

    def clean(text: str) -> str:
        return text.replace("\t", " ").replace("\n", " ").replace("\r", " ")

    lines = ["\t".join(clean(c.label) for c in columns)]
    lines += ["\t".join(clean(raw_text(r, c)) for c in columns) for r in rows]
    return "\n".join(lines) + "\n"


class RecordGrid(ScrollView, can_focus=True):
    """Virtualised, sortable, multi-select grid of records of one scope and record type."""

    KEY_HINTS: ClassVar[str] = (
        "Enter open  Space select  Ctrl+A all  ←→ column  s sort  c columns  y copy  F6 panels"
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
        Binding("c", "choose_columns", "Columns", show=False),
        Binding("y", "copy", "Copy", show=False),
        Binding("r", "reload", "Reload", show=False),
    ]

    COMPONENT_CLASSES: ClassVar[set[str]] = {
        "grid--header",
        "grid--cursor",
        "grid--selected",
        "grid--column",
        "grid--changed",
    }

    DEFAULT_CSS = """
    RecordGrid { height: 1fr; }
    RecordGrid > .grid--header { background: $panel; color: $text; text-style: bold; }
    RecordGrid > .grid--column { background: $primary; color: $text; text-style: bold; }
    RecordGrid > .grid--cursor { background: $accent 50%; }
    RecordGrid > .grid--selected { background: $primary 30%; }
    RecordGrid > .grid--changed { background: $warning 35%; }
    """

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        *,
        record_type: str | None = "core.Record",
        columns: list[GridColumn] | None = None,
        page_size: int = 200,
        highlight_seconds: float = HIGHLIGHT_SECONDS,
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
        self._generation = 0  # bumped whenever rows are replaced; late worker results are dropped
        self._loading = False
        self.filter_text = ""  # the filter text in force ("" = none)
        self.match_count: int | None = None  # count_records for `query` as of the last load
        self.highlight_seconds = highlight_seconds
        self.changed_until: dict[str, float] = {}  # record id -> monotonic time the mark ends
        self._live_running = False
        self._live_again = False
        self._live_marks: set[str] = set()

    # --- data --------------------------------------------------------------------------------

    def on_mount(self) -> None:
        self.load()

    def _order(self) -> list[tuple[str, Literal["asc", "desc"]]] | None:
        if self.sort_key is None:
            return None
        return [(self.sort_key, "desc" if self.sort_descending else "asc")]

    def _fetch(self, limit: int, offset: int) -> list[dict[str, Any]] | None:
        """One page, or ``None`` after posting an error status (the caller keeps its state)."""
        try:
            if self.filter_text:
                return self.client.query_records(
                    self.scope, self.filter_text, limit=limit, offset=offset, order_by=self._order()
                )
            return self.client.list_records(
                self.scope,
                record_type=self.record_type,
                limit=limit,
                offset=offset,
                order_by=self._order(),
            )
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return None

    def _count(self) -> int | None:
        """How many records match the filter, or ``None`` after posting an error status."""
        try:
            return self.client.count_records(self.scope, self.filter_text)
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return None

    def load(
        self, *, keep_id: str | None = None, count: int | None = None, matches: int | None = None
    ) -> bool:
        """Replace the rows with the first ``count`` rows (default one page) in the current order.

        Returns ``False``, leaving everything as it was, when the fetch failed. ``matches`` is a
        match count the caller already has for the current filter.
        """
        count = count or self.page_size
        page = self._fetch(count, 0)
        if page is None:
            return False
        if self.filter_text:
            self.match_count = matches if matches is not None else self._count()
        else:
            self.match_count = None
        self._generation += 1
        self.rows = page
        self.exhausted = len(page) < count
        self.cursor_row = 0
        if keep_id is not None:
            self._move_to_id(keep_id)
        self._after_rows_changed()
        return True

    def reload(self) -> None:
        """Re-read the loaded rows, keeping the sort and the cursor record when it still exists."""
        current = self.cursor_record
        size = min(max(self.page_size, len(self.rows)), END_CAP)
        self.load(keep_id=None if current is None else current["id"], count=size)

    def apply_filter(self, text: str) -> FilterResult:
        """Show only the records matching the query-language ``text`` (blank: all of them).

        The text is checked first through ``count_records``; a syntax error or other refusal
        leaves the rows, the filter and the cursor as they were.
        """
        text = text.strip()
        count: int | None = None
        if text:
            try:
                count = self.client.count_records(self.scope, text)
            except QuerySyntaxError as exc:
                return FilterResult(False, None, str(exc), exc.position)
            except CLIENT_ERRORS as exc:
                return FilterResult(False, None, describe_error(exc))
        previous = self.filter_text
        self.filter_text = text
        if not self.load(matches=count):
            self.filter_text = previous
            return FilterResult(False, None, "could not load the records")
        return FilterResult(True, count)

    def refresh_live(self, record_ids: Collection[str] = ()) -> None:
        """Re-read the loaded rows without blocking the UI, marking ``record_ids`` that changed.

        The fetch runs in a worker thread and the result is applied with ``call_from_thread``;
        calls made while one is running are merged into one more pass. A result is dropped when the
        rows were replaced meanwhile (a sort, a filter, End). Rows of ``record_ids`` that are in the
        result get a bullet for ``highlight_seconds`` (``record_ids`` are records someone else
        just changed, so the mark does not depend on what an earlier read already showed).
        """
        self._live_marks.update(record_ids)
        if self._live_running:
            self._live_again = True
            return
        self._live_running = True
        self._live_again = False
        marks = frozenset(self._live_marks)
        self._live_marks.clear()
        count = min(max(self.page_size, len(self.rows)), END_CAP)
        self.run_worker(
            partial(self._live_fetch, self._generation, count, marks),
            thread=True,
            group="grid-live",
        )

    def _live_fetch(self, generation: int, count: int, marks: frozenset[str]) -> None:
        """Worker thread: read the rows (and the match count); hand them to the UI thread."""
        page = self._fetch(count, 0)
        matches = self._count() if self.filter_text and page is not None else None
        try:
            self.app.call_from_thread(self._apply_live, generation, count, marks, page, matches)
        except RuntimeError:
            self._live_running = False  # the app is shutting down; nobody is listening

    def _apply_live(
        self,
        generation: int,
        count: int,
        marks: frozenset[str],
        page: list[dict[str, Any]] | None,
        matches: int | None,
    ) -> None:
        self._live_running = False
        if page is not None and generation == self._generation:
            current = self.cursor_record
            if self.highlight_seconds > 0:
                until = time.monotonic() + self.highlight_seconds
                fresh = [row["id"] for row in page if row["id"] in marks]
                for record_id in fresh:
                    self.changed_until[record_id] = until
                if fresh:
                    self.set_timer(self.highlight_seconds, self._expire_marks)
            old_cursor = self.cursor_row
            self._generation += 1
            self.rows = page
            self.exhausted = len(page) < count
            if self.filter_text:
                self.match_count = matches
            self.cursor_row = max(0, min(old_cursor, len(page) - 1))
            if current is not None:
                self._move_to_id(current["id"])
            self._after_rows_changed()
        if self._live_again or self._live_marks:
            self.refresh_live()

    def _expire_marks(self) -> None:
        """Drop the marks whose time is up, redraw, and re-arm for the ones still running."""
        now = time.monotonic()
        self.changed_until = {i: t for i, t in self.changed_until.items() if t > now}
        self.refresh()
        if self.changed_until:  # a timer can fire a hair early: come back for what is left
            self.set_timer(min(self.changed_until.values()) - now + 0.02, self._expire_marks)

    def is_marked(self, record_id: str) -> bool:
        """Whether the row shows the "changed by someone else" mark now."""
        until = self.changed_until.get(record_id)
        return until is not None and until > time.monotonic()

    def _move_to_id(self, record_id: str) -> None:
        for index, row in enumerate(self.rows):
            if row["id"] == record_id:
                self.cursor_row = index
                return

    def _load_more(self) -> None:
        if self.exhausted or self._loading:
            return  # the End worker owns paging while it runs; two pagers would duplicate rows
        page = self._fetch(self.page_size, len(self.rows))
        if page is None:
            return  # not exhausted: the list is incomplete and a later move retries
        self.rows.extend(page)
        if len(page) < self.page_size:
            self.exhausted = True
        self._update_virtual_size()

    def _load_to_end(self, generation: int, start: int) -> None:
        """Worker thread: page forward from ``start`` up to ``END_CAP`` rows in total."""
        rows: list[dict[str, Any]] = []
        exhausted = failed = False
        while start + len(rows) < END_CAP:
            page = self._fetch(self.page_size, start + len(rows))
            if page is None:
                failed = True
                break
            rows.extend(page)
            if len(page) < self.page_size:
                exhausted = True
                break
            self.post_message(StatusMessage(f"Loading rows… {start + len(rows):,}"))
        del rows[END_CAP - start :]
        self.app.call_from_thread(self._finish_load_to_end, generation, rows, exhausted, failed)

    def _finish_load_to_end(
        self, generation: int, rows: list[dict[str, Any]], exhausted: bool, failed: bool
    ) -> None:
        self._loading = False
        if generation != self._generation:
            return  # the list was replaced while the worker ran
        self.rows.extend(rows)
        self.exhausted = exhausted
        self._update_virtual_size()
        self._set_cursor(len(self.rows) - 1, page_in=False)
        if failed:
            return  # _fetch already posted the error
        if exhausted:
            self.post_message(StatusMessage(f"Loaded {len(self.rows):,} rows"))
        else:
            self.post_message(
                StatusMessage(f"Capped at {END_CAP:,} rows; narrow the list to see more", "warning")
            )

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

    def _set_cursor(self, row: int, *, page_in: bool = True) -> None:
        if not self.rows:
            return
        row = max(0, min(row, len(self.rows) - 1))
        if page_in and not self.exhausted and row >= len(self.rows) - max(self.page_size // 4, 1):
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
        if self.exhausted or len(self.rows) >= END_CAP:
            self._set_cursor(len(self.rows) - 1)
            return
        if self._loading:
            return
        self._loading = True
        self.post_message(StatusMessage("Loading rows…"))
        self.run_worker(
            partial(self._load_to_end, self._generation, len(self.rows)),
            thread=True,
            group="grid-end",
        )

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
        """Select the loaded rows only; say so when more rows exist on the server."""
        self.selected_ids = {r["id"] for r in self.rows}
        self._selection_changed()
        if not self.exhausted:
            self.post_message(
                StatusMessage(f"{len(self.rows):,} loaded rows selected; more not loaded")
            )

    def action_open(self) -> None:
        record = self.cursor_record
        if record is not None:
            self.post_message(OpenRecord(self.scope, str(record["key"])))

    def action_sort(self) -> None:
        self.sort_by(self.columns[self.column_cursor].key)

    def action_reload(self) -> None:
        self.reload()

    def action_choose_columns(self) -> None:
        # Function-level import: column_chooser imports GridColumn from this module.
        from tl_tui.widgets.column_chooser import ColumnChooser  # noqa: PLC0415

        meta: FormMetadata | None
        try:
            meta = self.client.form_metadata(self.scope, self.record_type or "core.Record")
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            meta = None
        except NotImplementedError:
            meta = None
        mapping: dict[str, GridColumn] = {c.key: c for c in available_columns(meta)}
        mapping.update({c.key: c for c in self.columns})  # keep the widths of shown columns

        def apply(keys: list[str] | None) -> None:
            if keys:
                self.set_columns([mapping[key] for key in keys])

        self.app.push_screen(
            ColumnChooser(list(mapping.values()), [c.key for c in self.columns]), apply
        )

    def action_copy(self) -> None:
        count = len(self.selected_records()) or (1 if self.cursor_record is not None else 0)
        if count == 0:
            self.post_message(StatusMessage("Nothing to copy", "warning"))
            return
        self.app.copy_to_clipboard(self.copy_text())
        noun = "row" if count == 1 else "rows"
        self.post_message(StatusMessage(f"Copied {count} {noun} as TSV"))

    def _selection_changed(self) -> None:
        self.refresh()
        self.post_message(SelectionChanged(frozenset(self.selected_ids)))

    def sort_by(self, key: str) -> None:
        """Cycle ascending, descending, unsorted on column ``key``; the server does the ordering."""
        column = next((c for c in self.columns if c.key == key), None)
        if column is None:
            return
        if key.startswith("psets."):
            self.post_message(StatusMessage("Sort on pset columns arrives with the query language"))
            return
        if key not in SORTABLE_KEYS:
            self.post_message(StatusMessage(f"Sorting by {column.label} is not available"))
            return
        previous = (self.sort_key, self.sort_descending)
        if self.sort_key != key:
            self.sort_key, self.sort_descending = key, False
        elif not self.sort_descending:
            self.sort_descending = True
        else:
            self.sort_key, self.sort_descending = None, False
        current = self.cursor_record
        if not self.load(keep_id=None if current is None else current["id"]):
            self.sort_key, self.sort_descending = previous

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
        is_marked = self.is_marked(record["id"])
        style: Style = self.rich_style
        if is_marked:
            style = style + self.get_component_rich_style("grid--changed")
        if is_selected:
            style = style + self.get_component_rich_style("grid--selected")
        if is_cursor:
            style = style + self.get_component_rich_style("grid--cursor")
        marker = (
            f"{'▶' if is_cursor else ' '}{'[x]' if is_selected else '[ ]'}"
            f"{CHANGED_MARK if is_marked else ' '}"
        )
        segments = [Segment(marker, style)]
        for column in self.columns:
            segments.append(
                Segment(fit_cell(cell_text(record, column), column.width, column.align), style)
            )
            segments.append(Segment(GAP, style))
        return segments
