"""The WBS tree of a project (P2-I1 T05b; spec m3-wbs-cwp §WBS tree, skill ``tui-layout``).

A full-size ``LogScreen``. The tree is read once from the client (``wbs_tree``); the depth keys
``1``-``8`` cut that loaded tree (``0`` shows every depth) and ``u`` keeps only the leaves with no
cost code. The panel describes the highlighted node from ``get_wbs_node`` (one call per
highlighted node). No actions bar in I1: the writes come with P2-I2. ``F5`` reads the tree again.
The text is ``tl_tui.wbs_text``; this module adds only the keys and the calls.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import Input
from tl_mod_awp.views import WbsRow

from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Panel, join_facts, render
from tl_tui.wbs_text import (
    WBS_COLUMNS,
    depth_limited,
    unallocated_leaves,
    wbs_cells,
    wbs_page,
)
from tl_tui.widgets.log_screen import LogAction, LogScreen

MAX_DEPTH = 8


class WbsScreen(LogScreen[WbsRow]):
    """The WBS tree of ``project`` (the id)."""

    LOG_NAME: ClassVar[str] = "WBS tree"
    # every key the log has, in one text (the walking tests read it); the keys row shows KEY_CELLS
    # and F1 lists the rest (HELP_KEYS)
    KEY_HINTS: ClassVar[str] = "/ filter  1-8 depth  0 all  u unallocated  F5 reload  Esc back"
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "1-8 depth", "0 all", "u unallocated")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("1-8", "Show the tree down to that depth (1 is the top nodes)"),
        ("0", "Show every depth"),
        ("u", "Only the leaves with no cost code, or all of them again"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        *(
            Binding(str(n), f"depth({n})", f"Depth {n}", show=False)
            for n in range(1, MAX_DEPTH + 1)
        ),
        Binding("0", "depth(0)", "All depths", show=False),
        Binding("u", "unallocated", "Unallocated", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.depth_limit: int | None = None  # None shows every depth
        self.unallocated_only = False
        self._wbs_tree: list[WbsRow] | None = None  # the whole tree, as the client returned it
        self._stale = True  # the tree is read again before the next list is drawn

    def _tree_rows(self) -> list[WbsRow]:
        return self._wbs_tree or []

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return WBS_COLUMNS

    def load_rows(self) -> Sequence[WbsRow]:
        if self._stale or self._wbs_tree is None:
            self._wbs_tree = list(self.client.wbs_tree(self.project))
            self._stale = False
        # the leaves are worked out on the whole tree, before the depth cut
        rows = unallocated_leaves(self._wbs_tree) if self.unallocated_only else self._wbs_tree
        if self.depth_limit is None:
            return list(rows)
        return depth_limited(rows, self.depth_limit)

    def row_key(self, row: WbsRow) -> str:
        return row.code

    def row_cells(self, row: WbsRow) -> Sequence[str]:
        return wbs_cells(row, self._tree_rows())

    def row_record(self, row: WbsRow) -> tuple[str, str]:
        return (row.code, row.title)

    def panel_text(self, row: WbsRow | None) -> Panel:
        """The highlighted node as ``get_wbs_node`` reads it; the listing's copy when that fails."""
        if row is None:
            return "No node matches."
        try:
            full = self.client.get_wbs_node(self.project, row.code)
        except CLIENT_ERRORS as exc:
            full = row  # the listing's copy: no cost-code or CWP detail beyond the rollup
            self.say(describe_error(exc), error=True)
        technical = mode_of(self.app).technical
        return render(wbs_page(full, self._tree_rows(), panel=True, technical=technical))

    def actions_for(self, row: WbsRow) -> Sequence[LogAction]:
        return []  # no actions in I1; the WBS writes come with P2-I2

    def summary_text(self) -> str:
        parts = [f"{len(self.shown)} of {len(self._tree_rows())} nodes"]
        if self.depth_limit is not None:
            parts.append(f"depth {self.depth_limit}")
        if self.unallocated_only:
            parts.append("unallocated leaves")
        return join_facts(*parts)

    def open_row(self, row: WbsRow) -> None:
        """Enter does nothing in I1: a WBS node has no record screen yet."""

    # --- the log's own keys --------------------------------------------------------------

    def action_depth(self, level: int) -> None:
        """Cut the loaded tree to ``level`` (``1``-``8``); ``0`` shows every depth. No read."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.depth_limit = level if level else None
        self.reload()

    def action_unallocated(self) -> None:
        """Show only the leaves with no cost code, or all of them again. No read."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.unallocated_only = not self.unallocated_only
        self.reload()

    def action_reload(self) -> None:
        """F5 reads the tree again from the client."""
        self._stale = True
        super().action_reload()
