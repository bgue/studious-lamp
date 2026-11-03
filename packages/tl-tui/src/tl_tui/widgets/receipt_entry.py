"""The new-receipt form: book a delivery with its lines (P2-I3-T06e; "Receipts").

A full-size modal, not in the navigation yet. The header fields are above; a line is typed in the
entry row (Item, Qty, Heat, Condition) and added to the list with ``Enter`` in the Condition input;
``Ctrl+D`` removes the highlighted line (the list has the focus for it). ``Ctrl+S`` sends
``CreateReceipt`` through ``client.materials_command``. Every word and every check lives in
``tl_tui.receipt_entry_text``; this screen mounts them and makes the one command call. A refusal
from the service goes to the status line and the form stays open with what was typed. After a
save the lines are cleared (so a second save cannot book the same delivery again) and the status
line names what is left: the MTR (D42, no upload call in the client yet).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static
from tl_mod_materials.views import LocationView, MaterialItemView, PoLineView

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.receipt_entry_text import (
    HEADER_FIELDS,
    KEYS,
    LINE_FIELDS,
    NOT_SAVED_TEXT,
    added_text,
    build_command,
    check_count,
    check_header,
    check_line,
    line_summary,
    location_hints,
    po_line_chosen,
    po_line_hints,
    saved_text,
)

#: The inputs in tab order; ``Enter`` moves to the next one, and in the last one adds the line.
_INPUT_ORDER: tuple[str, ...] = tuple(
    [f"h-{key}" for key, _ in HEADER_FIELDS] + [f"l-{key}" for key, _ in LINE_FIELDS]
)
_LINE_INPUT = "l-condition"
_ERROR_IDS: dict[str, str] = {
    **{key: f"err-{key}" for key, _ in HEADER_FIELDS},
    **{key: "err-entry" for key, _ in LINE_FIELDS},
    "lines": "err-lines",
}


class ReceiptEntryScreen(ModalScreen[None]):
    """Books one delivery as a receipt in state Received. Esc closes it."""

    KEY_HINTS: ClassVar[str] = KEYS

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+s", "save", "Save", show=False),
        Binding("ctrl+d", "remove_line", "Remove line", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    ReceiptEntryScreen { background: $surface; align: center top; }
    ReceiptEntryScreen > Vertical { height: 100%; padding: 0 1; }
    ReceiptEntryScreen #entry-title { text-style: bold; height: 1; }
    ReceiptEntryScreen .entry-row { height: auto; }
    ReceiptEntryScreen .entry-label { width: 14; height: 1; }
    ReceiptEntryScreen .entry-hint { height: auto; color: $text-muted; padding-left: 14; }
    ReceiptEntryScreen .entry-error { height: auto; color: $error; padding-left: 14; }
    ReceiptEntryScreen Input { height: 1; border: none; padding: 0 1; }
    ReceiptEntryScreen Input:focus { border: none; }
    ReceiptEntryScreen #entry-lines-title { height: 1; margin-top: 1; text-style: bold; }
    ReceiptEntryScreen #entry-lines { height: 1fr; min-height: 4; }
    ReceiptEntryScreen .entry-cell { width: 1fr; height: auto; }
    ReceiptEntryScreen #entry-status { height: auto; min-height: 1; }
    ReceiptEntryScreen #entry-keys { height: 1; color: $text-muted; }
    """

    def __init__(self, client: ClientInterface, project: str, actor: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.actor = actor
        self.lines: list[dict[str, str]] = []
        self.items: dict[str, MaterialItemView] = {}  # the project's library by code
        self.locations: list[LocationView] = []  # the project's locations, tree order
        self.po_matches: list[PoLineView] = []  # the last PO line completion

    # --- layout -----------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"New receipt · {self.project}", markup=False, id="entry-title")
            for key, label in HEADER_FIELDS:
                with Horizontal(classes="entry-row"):
                    yield Static(label, markup=False, classes="entry-label")
                    yield Input(
                        value=date.today().isoformat() if key == "received_on" else "",
                        id=f"h-{key}",
                    )
                if key in ("po_line", "location"):
                    yield Static("", markup=False, classes="entry-hint", id=f"hint-{key}")
                yield Static("", markup=False, classes="entry-error", id=f"err-{key}")
            with Horizontal(classes="entry-row"):
                yield Static("Item", markup=False, classes="entry-label")
                yield Input(id="l-item", classes="entry-cell")
                yield Static("Qty", markup=False, classes="entry-label")
                yield Input(id="l-qty", classes="entry-cell")
                yield Static("Heat", markup=False, classes="entry-label")
                yield Input(id="l-heat", classes="entry-cell")
                yield Static("Condition", markup=False, classes="entry-label")
                yield Input(value="good", id="l-condition", classes="entry-cell")
            yield Static("", markup=False, classes="entry-error", id="err-entry")
            yield Static("Lines", markup=False, id="entry-lines-title")
            yield DataTable(id="entry-lines", cursor_type="row", zebra_stripes=False)
            yield Static("", markup=False, classes="entry-error", id="err-lines")
            yield Static("", markup=False, id="entry-status")
            yield Static(KEYS, markup=False, id="entry-keys")

    def on_mount(self) -> None:
        table = self.query_one("#entry-lines", DataTable)
        table.add_column("Line", width=5)
        table.add_column("Receipt line")
        try:
            self.locations = self.client.list_materials_locations(self.project)
            library = self.client.list_materials_items(project=self.project)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            library = []
        self.items = {item.code: item for item in library}
        self.query_one("#h-po_line", Input).focus()

    # --- the status line and the field errors -------------------------------------------------

    def say(self, text: str, *, error: bool = False) -> None:
        """Write the status line; an error is marked ``! ``."""
        self.query_one("#entry-status", Static).update(("! " if error else "") + text)

    def _show_errors(self, errors: Sequence[tuple[str, str]]) -> None:
        """Put each message under its field (the entry row's messages under that row)."""
        for error_id in set(_ERROR_IDS.values()):
            self.query_one(f"#{error_id}", Static).update("")
        grouped: dict[str, list[str]] = {}
        for field, message in errors:
            grouped.setdefault(_ERROR_IDS.get(field, "err-lines"), []).append(message)
        for error_id, messages in grouped.items():
            self.query_one(f"#{error_id}", Static).update("\n".join(messages))

    def _header_values(self) -> dict[str, str]:
        return {key: self.query_one(f"#h-{key}", Input).value for key, _ in HEADER_FIELDS}

    def _entry_values(self) -> dict[str, str]:
        return {key: self.query_one(f"#l-{key}", Input).value for key, _ in LINE_FIELDS}

    # --- hints and the PO line completion -----------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        field = (event.input.id or "").removeprefix("h-")
        if event.input.id in {f"h-{key}" for key, _ in HEADER_FIELDS}:
            self.query_one(f"#err-{field}", Static).update("")  # the typed field is no longer wrong
        if event.input.id == "h-po_line":
            self._complete_po_line(event.value)
        elif event.input.id == "h-location":
            hints = location_hints(self.locations, event.value)
            self.query_one("#hint-location", Static).update("\n".join(hints))

    def _complete_po_line(self, text: str) -> None:
        query = text.strip()
        if not query:
            self.po_matches = []
            self.query_one("#hint-po_line", Static).update("")
            return
        try:
            self.po_matches = self.client.list_materials_po_lines(self.project, q=query)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return
        self.query_one("#hint-po_line", Static).update("\n".join(po_line_hints(self.po_matches)))
        chosen = po_line_chosen(self.po_matches, query)
        supplier = self.query_one("#h-supplier", Input)
        if chosen is not None and not supplier.value.strip():
            supplier.value = chosen.supplier_text

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if event.input.id == _LINE_INPUT:
            self.action_add_line()
            return
        index = _INPUT_ORDER.index(event.input.id) if event.input.id in _INPUT_ORDER else -1
        if 0 <= index < len(_INPUT_ORDER) - 1:
            self.query_one(f"#{_INPUT_ORDER[index + 1]}", Input).focus()

    # --- the keys -----------------------------------------------------------------------------

    def action_add_line(self) -> None:
        """Add the entry row as a line; the entry row is then cleared except the condition."""
        values = self._entry_values()
        errors = check_count(len(self.lines) + 1)
        errors += check_line(values, self.items)
        self._show_errors(errors)
        if errors:
            return
        code = values["item"].strip()
        self.lines.append({key: value.strip() for key, value in values.items()})
        self._refresh_lines()
        for key in ("item", "qty", "heat"):
            self.query_one(f"#l-{key}", Input).value = ""
        self.query_one("#l-item", Input).focus()
        self.say(added_text(code))

    def action_remove_line(self) -> None:
        """Remove the highlighted line (the list has the focus)."""
        table = self.query_one("#entry-lines", DataTable)
        if not self.lines or table.cursor_row is None:
            return
        del self.lines[table.cursor_row]
        self._refresh_lines()

    def _refresh_lines(self) -> None:
        table = self.query_one("#entry-lines", DataTable)
        table.clear()
        for number, line in enumerate(self.lines, start=1):
            item = self.items.get(line["item"])
            uom = item.base_uom if item is not None else None
            table.add_row(str(number), line_summary(line, uom), key=str(number))
        if self.lines:
            table.move_cursor(row=min(table.cursor_row or 0, len(self.lines) - 1))

    def action_save(self) -> None:
        """Send ``CreateReceipt``; a refusal stays on the form with what was typed."""
        header = self._header_values()
        locations = [location.code for location in self.locations]
        errors = check_header(header, locations, date.today())
        errors += check_count(len(self.lines))
        self._show_errors(errors)
        if errors:
            self.say(NOT_SAVED_TEXT, error=True)
            return
        try:
            cmd = build_command(header, self.lines, actor=self.actor, project=self.project)
            result = self.client.materials_command("CreateReceipt", cmd)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return
        self.lines = []
        self._refresh_lines()
        self.say(saved_text(result.key or result.stream_id))

    def action_close(self) -> None:
        self.dismiss(None)
