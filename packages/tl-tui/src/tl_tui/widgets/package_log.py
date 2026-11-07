"""The external packages log: a project's EWPs and PWPs (P2-I1 T05f; spec §8 "External packages").

A full-size modal, a ``LogScreen``. The list shows the packages by number; the panel describes the
highlighted package: its forecast and actual dates, its source system and the CWPs that require
it. ``t`` cycles the type (all, EWP, PWP), ``c`` keeps only the constraint sources, F5 reads the
list again. The packages are read once per read of the list; ``t`` and ``c`` narrow the rows
already read. No actions are offered in this increment, and Enter has no record screen to open.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import Input
from tl_mod_awp.views import PackageRow

from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.layout import Panel, render
from tl_tui.package_text import (
    PACKAGE_COLUMNS,
    next_type,
    package_cells,
    package_page,
    summary_line,
)
from tl_tui.widgets.log_screen import LogAction, LogScreen


class PackageLogScreen(LogScreen[PackageRow]):
    """The packages of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = "Packages"
    # every key the log has, in one text (the walking tests read it); the keys row shows KEY_CELLS
    # and F1 lists the rest (HELP_KEYS)
    KEY_HINTS: ClassVar[str] = "/ filter  t type  c constraints  F5 reload  Esc back"
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "t type", "c constraints")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("t", "Show the next type: all, then EWP, then PWP"),
        ("c", "Only the packages that are a constraint source"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("t", "type_filter", "Type", show=False),
        Binding("c", "constraints", "Constraint sources", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.kind: str | None = None  # None: all types
        self.constraints_only = False
        self.views: list[PackageRow] = []  # as listed, before the screen's own filters

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return PACKAGE_COLUMNS

    def load_rows(self) -> Sequence[PackageRow]:
        """Runs off the UI thread: it reads the list and sets nothing on the screen. The
        screen takes the list over in ``_fill`` on the UI thread (see there)."""
        return self.client.list_packages(self.project)

    def row_key(self, row: PackageRow) -> str:
        return row.id

    def row_cells(self, row: PackageRow) -> Sequence[str]:
        return package_cells(row)

    def row_record(self, row: PackageRow) -> tuple[str, str]:
        return (row.package_no, row.title)

    def panel_text(self, row: PackageRow | None) -> Panel:
        """The highlighted package; it reads nothing more than the row it is given."""
        if row is None:
            return "No package matches."
        technical = mode_of(self.app).technical
        return render(package_page(row, panel=True, technical=technical))

    def actions_for(self, row: PackageRow) -> Sequence[LogAction]:
        return []  # no actions bar entries in this increment

    def summary_text(self) -> str:
        return summary_line(
            len(self.shown),
            len(self.views),
            kind=self.kind,
            constraints_only=self.constraints_only,
            text=self.filter_text,
        )

    def open_row(self, row: PackageRow) -> None:
        """Enter does nothing yet: a package has no record screen in this increment."""

    # --- the screen's own filters --------------------------------------------------------

    def _narrowed(self) -> list[PackageRow]:
        """The rows the type and constraint filters keep, from the rows already read."""
        return [
            view
            for view in self.views
            if (self.kind is None or view.kind == self.kind)
            and (not self.constraints_only or view.constraint_source)
        ]

    def _fill(self, keep: str | None = None, *, reread: bool = False) -> None:
        """The base applies the rows here on the UI thread. A fresh read (``reread``) is the
        whole list: it becomes ``views``, and ``rows`` is that list after the screen's filters."""
        if reread:
            self.views = list(self.rows)
            self.rows = self._narrowed()
        super()._fill(keep, reread=reread)

    def _refilter(self) -> None:
        """Narrow the rows already read (no call to the client); the cursor stays on its row."""
        self.rows = self._narrowed()
        self._fill(self._key())

    # --- the log's own keys --------------------------------------------------------------

    def action_type_filter(self) -> None:
        """Show the next type: all, then EWP, then PWP, then all again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.kind = next_type(self.kind)
        self._refilter()

    def action_constraints(self) -> None:
        """Show only the constraint sources, or all packages again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.constraints_only = not self.constraints_only
        self._refilter()
