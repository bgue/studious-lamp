"""The scaffold register of a project and one scaffold's record (P2-I4B-T07b; spec §8).

``ScaffoldLogScreen`` is a full-size ``LogScreen``: the project's scaffolds by key, with subject,
state, tag, last inspection, next due day and location. The panel describes the highlighted
scaffold. ``s`` shows the next state filter, ``o`` the overdue scaffolds only; each filter is read
again from the client. ``x`` writes the export of the visible filter as CSV to
``./scaffolds-<project>.csv`` in the working directory, ``X`` as JSONL. Enter opens
``ScaffoldScreen`` for the scaffold.

``ScaffoldScreen`` shows one scaffold with its inspections, oldest first. Esc closes it, F5 reads
it again. Both screens only read: the state-changing acts stay on the command door.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static
from tl_core.services.errors import RecordNotFoundError
from tl_mod_scaffold import names
from tl_mod_scaffold.views import ScaffoldDetail, ScaffoldRow

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Page, Panel, render
from tl_tui.scaffold_text import (
    NOT_FOUND,
    SCAFFOLD_COLUMNS,
    SCAFFOLD_DROP,
    detail_page,
    export_filename,
    register_page,
    scaffold_cells,
)
from tl_tui.widgets.log_screen import LogAction, LogScreen

UNREADABLE = "This scaffold could not be read."
#: The state filter's values in the order ``s`` shows them: all, then each state.
FILTER_STATES: tuple[str, ...] = (
    names.REQUESTED,
    names.DESIGNED_STATE,
    names.ERECTING_STATE,
    names.INSPECTED_STATE,
    names.IN_USE,
    names.MODIFY,
    names.DISMANTLE,
    names.REMOVED,
)


def _next_state(current: str | None) -> str | None:
    """The next state filter: all (``None``), then each state in order, then all again."""
    options: list[str | None] = [None, *FILTER_STATES]
    index = options.index(current) if current in options else 0
    return options[(index + 1) % len(options)]


class ScaffoldLogScreen(LogScreen[ScaffoldRow]):
    """The scaffolds of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = "Scaffold register"
    KEY_HINTS: ClassVar[str] = (
        "/ filter  s state  o overdue  x export  X export JSONL  F5 reload  Esc back"
    )
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "s state", "o overdue", "x export")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("s", "Show the next state: all, then each state"),
        ("o", "Show only the overdue scaffolds (again: all)"),
        ("x", "Write the visible list as CSV to scaffolds-<project>.csv"),
        ("X", "Write the visible list as JSONL to scaffolds-<project>.jsonl"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s", "state", "State", show=False),
        Binding("o", "overdue", "Overdue", show=False),
        Binding("x", "export_csv", "Export CSV", show=False),
        Binding("X", "export_jsonl", "Export JSONL", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.state_filter: str | None = None
        self.overdue = False
        self.summary = ""  # the register's summary line, as last read

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return SCAFFOLD_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return SCAFFOLD_DROP

    def load_rows(self) -> Sequence[ScaffoldRow]:
        """The filters go to the list (state, overdue); the summary follows the rows read."""
        page = self.client.list_scaffolds(
            self.project, state=self.state_filter, overdue=self.overdue
        )
        _, self.summary = register_page(page.rows, page.total, today=date.today().isoformat())
        return page.rows

    def row_key(self, row: ScaffoldRow) -> str:
        return row.key

    def row_cells(self, row: ScaffoldRow) -> Sequence[str]:
        return scaffold_cells(row)

    def row_record(self, row: ScaffoldRow) -> tuple[str, str]:
        return (row.key, row.subject)

    def panel_text(self, row: ScaffoldRow | None) -> Panel:
        """The highlighted scaffold in full: one ``get_scaffold`` read for it."""
        if row is None:
            return "No scaffold matches."
        try:
            detail = self.client.get_scaffold(self.project, row.key)
        except RecordNotFoundError:
            self.say(NOT_FOUND, error=True)
            return UNREADABLE
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return UNREADABLE
        return render(detail_page(detail))

    def actions_for(self, row: ScaffoldRow) -> Sequence[LogAction]:
        """No action on the register's rows: the register only reads."""
        return []

    def summary_text(self) -> str:
        """The register's summary, with the filters that are on named after it."""
        named: list[str] = []
        if self.state_filter is not None:
            named.append(f"state {self.state_filter}")
        if self.overdue:
            named.append("overdue only")
        return ", ".join([self.summary, *named]) if named else self.summary

    def open_row(self, row: ScaffoldRow) -> None:
        """Enter on a row opens the scaffold's record."""
        self.app.push_screen(ScaffoldScreen(self.client, self.project, row.key))

    # --- the log's own keys --------------------------------------------------------------

    def action_state(self) -> None:
        """Show the next state: all, then each state."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.state_filter = _next_state(self.state_filter)
        self.reload()

    def action_overdue(self) -> None:
        """Show only the overdue scaffolds, or all of them again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.overdue = not self.overdue
        self.reload()

    def action_export_csv(self) -> None:
        self._export("csv")

    def action_export_jsonl(self) -> None:
        self._export("jsonl")

    # --- helpers -------------------------------------------------------------------------

    def _export(self, fmt: str) -> None:
        """Write the export of the visible filter to the working directory; say where it went."""
        if isinstance(self.focused, Input):
            return  # the key is text
        try:
            text = self.client.export_scaffolds(
                self.project, fmt=fmt, state=self.state_filter, overdue=self.overdue
            )
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return
        name = export_filename(self.project, fmt)
        try:
            with (Path.cwd() / name).open("w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        except OSError:
            self.say(f"The export ./{name} could not be written.", error=True)
            return
        self.say(f"Wrote ./{name}")


class ScaffoldScreen(ModalScreen[None]):
    """One scaffold in full, with its inspections. Esc closes it, F5 reads it again."""

    KEY_HINTS: ClassVar[str] = "Esc back  F5 reload"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
        Binding("f5", "reload", "Reload", show=False),
    ]

    DEFAULT_CSS = """
    ScaffoldScreen { background: $surface; }
    ScaffoldScreen #scaffold-body { height: 1fr; padding: 0 1; }
    ScaffoldScreen #scaffold-keys { height: 1; color: $text-muted; }
    ScaffoldScreen #scaffold-status { height: 1; }
    """

    def __init__(self, client: ClientInterface, project: str, key: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.key = key
        self.detail: ScaffoldDetail | None = None  # as last read
        self._gen = 0

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            with VerticalScroll(id="scaffold-body"):
                yield Static("", markup=False, id="scaffold-page")
            yield Static(self.KEY_HINTS, markup=False, id="scaffold-keys")
            yield Static("", markup=False, id="scaffold-status")

    def on_mount(self) -> None:
        self.reload()

    # --- reads ---------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the scaffold again (off the UI thread)."""
        self._gen += 1
        self.run_worker(self._load(self._gen), group="scaffold", exclusive=True)

    async def _load(self, gen: int) -> None:
        try:
            detail = await asyncio.to_thread(self.client.get_scaffold, self.project, self.key)
        except RecordNotFoundError:
            if gen == self._gen and self.is_attached:
                self.detail = None
                self._show(None, "", body=NOT_FOUND)
            return
        except CLIENT_ERRORS as exc:
            if gen == self._gen and self.is_attached:
                self.detail = None
                self._show(None, describe_error(exc))
            return
        if gen == self._gen and self.is_attached:
            self.detail = detail
            self._show(detail_page(detail), "")

    def _show(self, page: Page | None, error: str, *, body: str = "") -> None:
        body_text: Any = render(page) if page is not None else (body or UNREADABLE)
        self.query_one("#scaffold-page", Static).update(body_text)
        status = self.query_one("#scaffold-status", Static)
        status.update(("! " + error) if error else "")

    # --- the screen's keys ---------------------------------------------------------------

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        self.dismiss(None)


__all__ = ["FILTER_STATES", "ScaffoldLogScreen", "ScaffoldScreen"]
