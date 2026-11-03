"""The path of construction of a project (P2-I1 T05c; spec §8 "Path of construction", skill
``tui-layout``).

A full-size ``LogScreen``. It shows one version of the path: its steps (Number, Subject, Reason,
CWPs, Budget h). ``[`` and ``]`` step to the previous and next version (one ``get_path`` each),
``v`` shows the comparison of the previous version with this one instead of the steps, and ``F5``
reads again. The panel describes the highlighted step (or the CWA it compares) with its CWPs, the
changed steps and the versions. No actions bar in I1. The text is ``tl_tui.path_text``; this module
adds only the keys and the calls.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import Input
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp.views import CwaRow, CwpRow, PathVersion, PathView

from tl_tui.client import ClientInterface
from tl_tui.display import Labels
from tl_tui.labels_load import load_labels
from tl_tui.layout import Panel, join_facts, render
from tl_tui.path_text import (
    COMPARE_COLUMNS,
    PATH_COLUMNS,
    Moved,
    PathLine,
    compare_cells,
    compare_versions,
    path_cells,
    path_lines,
    path_page,
)
from tl_tui.text import EMPTY
from tl_tui.widgets.log_screen import LogAction, LogScreen

PathRow = PathLine | Moved
NO_EARLIER = "No earlier version"
NO_LATER = "No later version"


class PathScreen(LogScreen[PathRow]):
    """The path of construction of ``project`` (the id)."""

    LOG_NAME: ClassVar[str] = "Path of construction"
    # every key the log has, in one text (the walking tests read it); the keys row shows KEY_CELLS
    # and F1 lists the rest (HELP_KEYS)
    KEY_HINTS: ClassVar[str] = "/ filter  [ ] version  v compare  F5 reload  Esc back"
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "[ ] version", "v compare")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("[", "Show the previous version of the path"),
        ("]", "Show the next version of the path"),
        ("v", "Compare this version with the previous one, or show the steps again"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("left_square_bracket", "previous_version", "Previous", show=False),
        Binding("right_square_bracket", "next_version", "Next", show=False),
        Binding("v", "compare", "Compare", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.wanted: int | None = None  # the version to show; None is the current one
        self.compare = False  # the body shows the comparison, not the steps
        self.view: PathView | None = None  # the version shown, as last read
        self.previous: PathView | None = None  # the version before it, when it has one
        self.versions: list[PathVersion] = []
        self.cwas: list[CwaRow] = []  # the CWAs as listed (the names of the steps)
        self.cwps: list[CwpRow] = []  # the CWPs as listed (the counts and budgets of the steps)
        self.labels = Labels()  # the labels of the path, loaded with the first rows
        self._labelled = False

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return COMPARE_COLUMNS if self.compare else PATH_COLUMNS

    def load_rows(self) -> Sequence[PathRow]:
        if not self._labelled:
            self.labels = load_labels(self.client, f"project:{self.project}", ("awp.CWP",))
            self._labelled = True
        view = self.client.get_path(self.project, version=self.wanted)
        self.view = view
        self.previous = self._earlier(view)
        self.versions = list(self.client.list_path_versions(self.project))
        self.cwas = list(self.client.list_cwas(self.project))
        self.cwps = list(self.client.list_cwps(self.project))
        if self.compare:
            return compare_versions(self.previous, view) if self.previous is not None else []
        return path_lines(view, self.cwas, self.cwps)

    def _earlier(self, view: PathView) -> PathView | None:
        """The version before ``view``, read once; none for version 1 or when it is not held."""
        if view.version <= 1:
            return None
        try:
            return self.client.get_path(self.project, version=view.version - 1)
        except RecordNotFoundError:
            return None

    def row_key(self, row: PathRow) -> str:
        if isinstance(row, Moved):
            return row.cwa or EMPTY
        return str(row.step.position)

    def row_cells(self, row: PathRow) -> Sequence[str]:
        if isinstance(row, Moved):
            return compare_cells(row)
        return path_cells(row, self.labels)

    def row_record(self, row: PathRow) -> tuple[str, str]:
        if self.view is None:
            return (self.project, "Path of construction")
        return (self.view.key, self.view.title)

    def panel_text(self, row: PathRow | None) -> Panel:
        """The version's page, with the highlighted step's CWPs (from the listing: no call)."""
        if self.view is None:
            return "No path of construction."
        line = self._line_of(row)
        page = path_page(
            self.view,
            self.versions,
            line,
            previous=self.previous,
            labels=self.labels,
            panel=True,
        )
        return render(page)

    def _line_of(self, row: PathRow | None) -> PathLine | None:
        """The step the highlighted row is, or the step of the CWA a comparison row names."""
        if row is None or self.view is None:
            return None
        if isinstance(row, PathLine):
            return row
        return next(
            (
                line
                for line in path_lines(self.view, self.cwas, self.cwps)
                if line.step.cwa == row.cwa
            ),
            None,
        )

    def actions_for(self, row: PathRow) -> Sequence[LogAction]:
        return []  # no actions in I1; the path writes come with P2-I2

    def summary_text(self) -> str:
        if self.view is None:
            return ""
        if self.compare:
            if self.previous is None:
                return NO_EARLIER
            count = len(self.shown)
            return join_facts(
                f"{count} row{'s' if count != 1 else ''}",
                f"against version {self.previous.version}",
            )
        count = len(self.shown)
        return join_facts(
            f"{count} step{'s' if count != 1 else ''}", f"version {self.view.version}"
        )

    def open_row(self, row: PathRow) -> None:
        """Enter does nothing in I1: a step has no record screen yet."""

    # --- the log's own keys --------------------------------------------------------------

    def action_previous_version(self) -> None:
        """Show the version before this one (one read)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        if self.view is None or self.view.version <= 1:
            self.say(NO_EARLIER)
            return
        self.wanted = self.view.version - 1
        if self.wanted == 1:
            self.compare = False  # version 1 has no earlier version to compare with: the steps
        self.reload()

    def action_next_version(self) -> None:
        """Show the version after this one (one read); the current one is shown as the default."""
        if isinstance(self.focused, Input):
            return  # the key is text
        if self.view is None or self.view.version >= self.view.current_version:
            self.say(NO_LATER)
            return
        target = self.view.version + 1
        self.wanted = None if target == self.view.current_version else target
        self.reload()

    def action_compare(self) -> None:
        """Show the comparison with the previous version, or the steps again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        if self.view is None or self.view.version <= 1:
            self.say(NO_EARLIER)
            return
        self.compare = not self.compare
        self.reload()
