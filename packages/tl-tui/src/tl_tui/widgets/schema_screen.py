"""The schema workbench: every package version and what it defines (P1-I8-T04a; brief 10.6, 27.8).

A full-size modal opened with ``Ctrl+O``, a ``LogScreen`` (P1-UX2-S3). The list shows the package
versions, the versions of one package together (``tree_cells``); the panel shows the highlighted
version: who drafted it, and one of three tabs, ``1`` what it defines, ``2`` its lint findings,
``3`` the diff against the version below. ``[`` and ``]`` move between the tabs. The actions bar
offers ``v`` to open the review of the highlighted version (classification, impact, test on a
sample, submit, approve, publish; P1-I8-T04b) and the list is read again when it closes. ``F5``
reads again, ``Esc`` closes. Nothing is stored here and nothing changes here: every read is a
client call, and a refusal or a missing package is shown in the status line.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.binding import Binding, BindingType
from tl_core.settings.layers import project_of_scope
from tl_mod_schemareg.views import PackageDetail, PackageSummary

from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.schema_text import (
    COLUMNS,
    diff_lines,
    header_lines,
    lint_lines,
    plain_ref,
    property_lines,
    tree_cells,
)
from tl_tui.widgets.log_screen import LogAction, LogScreen
from tl_tui.widgets.record_screen import open_record

TABS = ("Properties", "Lint", "Diff")


class SchemaWorkbenchScreen(LogScreen[PackageSummary]):
    """The package versions for ``scope``; ``tab`` is the one shown first."""

    LOG_NAME: ClassVar[str] = "Schema packages"
    KEY_HINTS: ClassVar[str] = "[ ] or 1-3 tab  / filter  F5 reload  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("right_square_bracket", "next_tab(1)", "Next tab", show=False),
        Binding("left_square_bracket", "next_tab(-1)", "Previous tab", show=False),
        *(
            Binding(str(n), f"show_tab({n - 1})", name, show=False)
            for n, name in enumerate(TABS, 1)
        ),
    ]

    DEFAULT_CSS = """
    SchemaWorkbenchScreen #log-table { height: 8; min-height: 4; }
    SchemaWorkbenchScreen #log-panel { height: 1fr; }
    """

    def __init__(self, client: ClientInterface, scope: str, actor: str, *, tab: int = 0) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.actor = actor
        self.tab = tab if 0 <= tab < len(TABS) else 0
        self.details: dict[str, PackageDetail] = {}
        self._tree: dict[str, tuple[str, ...]] = {}  # row id -> cells, for the rows as listed
        self._tree_for: tuple[int, bool] | None = None
        self._flash = ""  # a note for the status line that the reload would replace

    @property
    def listed(self) -> list[PackageSummary]:
        """The package versions as listed, before the filter box."""
        return self.rows

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return project_of_scope(self.scope) or "Company"

    def columns(self) -> Sequence[str]:
        return COLUMNS

    def load_rows(self) -> Sequence[PackageSummary]:
        found = self.client.list_schema_packages()
        self.details = {}
        self._tree_for = None  # the cells are worked out again for the rows just read
        return found

    def row_key(self, row: PackageSummary) -> str:
        return row.id

    def row_cells(self, row: PackageSummary) -> Sequence[str]:
        """The cells of the row; the package name shows once per run of versions, so the cells
        are worked out for all the rows as listed (not for the ones the filter box leaves)."""
        technical = mode_of(self.app).technical
        if self._tree_for != (id(self.rows), technical):
            cells = tree_cells(self.rows, technical=technical)
            self._tree = {r.id: c for r, c in zip(self.rows, cells, strict=True)}
            self._tree_for = (id(self.rows), technical)
        return self._tree[row.id]

    def row_record(self, row: PackageSummary) -> tuple[str, str]:
        return (plain_ref(row.key) if not mode_of(self.app).technical else row.key, row.title or "")

    def summary_text(self) -> str:
        if self._flash:
            flash, self._flash = self._flash, ""
            return flash
        return f"Schema packages ({len(self.rows)})   scope {self.scope}"

    def panel_text(self, row: PackageSummary | None) -> str:
        """The header, the tab line and the tab of the highlighted version."""
        tabs = "  ".join(
            f"[{n} {name}]" if n - 1 == self.tab else f"{n} {name}"
            for n, name in enumerate(TABS, 1)
        )
        technical = mode_of(self.app).technical
        if row is None:
            return "No package versions."
        detail = self.details.get(row.id)
        if detail is None:
            try:
                detail = self.client.get_schema_package(row.id)
            except CLIENT_ERRORS as exc:
                self.say(describe_error(exc), error=True)
                return "\n".join([row.key if technical else plain_ref(row.key), "", tabs])
            self.details[row.id] = detail
        if self.tab == 0:
            lines = property_lines(detail.content, technical=technical)
        elif self.tab == 1:
            lines = lint_lines(detail.lint, technical=technical)
        else:
            lines = diff_lines(detail)
        return "\n".join([*header_lines(detail, technical=technical), "", tabs, "", *lines])

    def open_row(self, row: PackageSummary) -> None:
        """Enter on a version opens its full record; Esc there returns to this row."""
        open_record(
            self,
            self.client,
            self.scope,
            project_of_scope(self.scope) or "",
            self.actor,
            row.id,
        )

    # --- the actions bar: the key the screen has always enabled --------------------------------

    def actions_for(self, row: PackageSummary) -> Sequence[LogAction]:
        return [LogAction("v", "Review and publish", self._review)]

    def _review(self) -> None:
        """Open the review of the highlighted version; read the list again when it closes."""
        row = self.current()
        if row is None:
            return
        from tl_tui.widgets.schema_review_screen import SchemaReviewScreen

        self.app.push_screen(
            SchemaReviewScreen(self.client, self.scope, self.actor, row.id),
            callback=self._review_closed,
        )

    def _review_closed(self, _: None) -> None:
        self.reload()

    # --- the log's own keys --------------------------------------------------------------

    def action_show_tab(self, index: int) -> None:
        """Show the tab at `index` of `TABS`."""
        self.tab = index
        self._show_row(force=False)

    def action_next_tab(self, step: int) -> None:
        """Show the next (or, with a negative `step`, the previous) tab, wrapping round."""
        self.action_show_tab((self.tab + step) % len(TABS))

    def action_reload(self) -> None:
        self._flash = "Reloaded."
        self.reload()
