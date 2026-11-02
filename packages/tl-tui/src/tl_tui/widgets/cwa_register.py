"""The CWA register of a project: its construction work areas in path order (P2-I1 T05e; spec §8
"CWA register", skill ``tui-layout``).

A full-size ``LogScreen``. The screen reads three lists from the client, once per read: the areas
(``list_cwas``), the path of construction (``get_path``; no path yet means no positions) and the
CWPs (``list_cwps``). No call is made per row. The panel describes the highlighted area. There is
no actions bar in I1 and Enter does nothing (no area record screen yet). ``r`` shows or hides the
retired areas; ``F5`` reads the lists again. The text is ``tl_tui.cwa_text``; this module adds
only the keys and the calls.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import Input
from tl_core.services.errors import RecordNotFoundError

from tl_tui.client import ClientInterface
from tl_tui.cwa_text import (
    CWA_COLUMNS,
    CWA_DROP,
    NO_CWA,
    CwaLine,
    cwa_cells,
    cwa_lines,
    cwa_page,
    visible_lines,
)
from tl_tui.display import mode_of
from tl_tui.layout import Panel, render
from tl_tui.widgets.log_screen import LogAction, LogScreen


class CwaRegisterScreen(LogScreen[CwaLine]):
    """The CWAs of ``project`` (the id), in path order."""

    LOG_NAME: ClassVar[str] = "CWA register"
    # every key the log has, in one text (the walking tests read it); the keys row shows KEY_CELLS
    # and F1 lists the rest (HELP_KEYS)
    KEY_HINTS: ClassVar[str] = "/ filter  r retired  F5 reload  Esc back"
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "r retired")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("r", "Show the retired areas too, or hide them again"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("r", "retired", "Retired", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.show_retired = False
        self.lines: list[CwaLine] = []  # every area as read, retired ones too, before the filters

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return CWA_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return CWA_DROP

    def load_rows(self) -> Sequence[CwaLine]:
        cwas = self.client.list_cwas(self.project)
        try:
            path = self.client.get_path(self.project)
        except RecordNotFoundError:
            path = None  # no path of construction yet: every position reads —
        cwps = self.client.list_cwps(self.project)
        self.lines = cwa_lines(cwas, path, cwps)
        return visible_lines(self.lines, self.show_retired)

    def row_key(self, row: CwaLine) -> str:
        return row.row.id

    def row_cells(self, row: CwaLine) -> Sequence[str]:
        return cwa_cells(row)

    def row_record(self, row: CwaLine) -> tuple[str, str]:
        return (row.row.code, row.row.title)

    def panel_text(self, row: CwaLine | None) -> Panel:
        """The highlighted area: its location, path position and CWPs (no client call)."""
        if row is None:
            return NO_CWA
        technical = mode_of(self.app).technical
        return render(cwa_page(row, panel=True, technical=technical))

    def actions_for(self, row: CwaLine) -> Sequence[LogAction]:
        return []  # no actions in I1

    def summary_text(self) -> str:
        retired = "shown" if self.show_retired else "hidden"
        return f"{len(self.shown)} of {len(self.lines)} CWAs; retired {retired}"

    def open_row(self, row: CwaLine) -> None:
        """Enter does nothing: an area has no record screen in I1."""

    # --- the log's own keys --------------------------------------------------------------

    def action_retired(self) -> None:
        """Show the retired areas, or hide them again (reads the lists again)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.show_retired = not self.show_retired
        self.reload()
