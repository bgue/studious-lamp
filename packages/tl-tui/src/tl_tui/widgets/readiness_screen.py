"""The readiness of one IWP: a full-size ``LogScreen`` of its checks (P2-I2 T07a; spec §8, skill
``tui-layout``).

One row per check, and one row per reference of a check (``resolve_via``). Enter on a reference row
opens that record (``open_record``); on a row with no reference Enter does nothing, and the panel
shows the check's detail. The columns, rows, summary and panel come from ``tl_tui.readiness_text``;
this screen only reads the evaluation. The read drops the references the reader may not open, so
the screen never filters them. A missing, hidden or never-evaluated IWP shows one line:
``not_evaluated_text``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, ClassVar

from tl_core.services.errors import RecordNotFoundError

from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.layout import Panel, Section, render
from tl_tui.readiness_text import (
    READINESS_COLUMNS,
    READINESS_DROP,
    not_evaluated_text,
    readiness_page,
    readiness_rows,
    readiness_summary,
)
from tl_tui.widgets.log_screen import LogAction, LogScreen
from tl_tui.widgets.record_screen import open_record

if TYPE_CHECKING:
    from tl_api.routes.awp import ReadinessBody

DETAIL_COLUMN = READINESS_COLUMNS.index("Detail")
DETAIL_SECTION = "Detail"


@dataclass(frozen=True)
class ReadinessLine:
    """One row of the table: its cells, the reference it opens (``None``: none), its place."""

    position: int
    cells: tuple[str, ...]
    record_id: str | None


class ReadinessScreen(LogScreen[ReadinessLine]):
    """The checks of IWP ``number`` of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = "Readiness"
    KEY_HINTS: ClassVar[str] = "Enter open  F5 reload  Esc back"
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("Enter open", "F5 reload", "Esc back")

    def __init__(self, client: ClientInterface, project: str, number: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.number = number
        self.view: ReadinessBody | None = None  # the last read; None when not evaluated

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return READINESS_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return READINESS_DROP

    def load_rows(self) -> Sequence[ReadinessLine]:
        try:
            self.view = self.client.get_iwp_readiness(self.project, self.number)
        except RecordNotFoundError:  # missing, hidden or never evaluated: one answer
            self.view = None
            return []
        return [
            ReadinessLine(position, cells, record_id)
            for position, (cells, record_id) in enumerate(readiness_rows(self.view))
        ]

    def row_key(self, row: ReadinessLine) -> str:
        return str(row.position)

    def row_cells(self, row: ReadinessLine) -> Sequence[str]:
        return row.cells

    def row_record(self, row: ReadinessLine) -> tuple[str, str]:
        return (self.number, "")

    def panel_text(self, row: ReadinessLine | None) -> Panel:
        """The page of the IWP's readiness; on a check with no reference, that check's detail."""
        if self.view is None:
            return not_evaluated_text(self.number)
        technical = mode_of(self.app).technical
        page = readiness_page(self.number, self.view, technical=technical, panel=True)
        if row is not None and row.record_id is None:
            detail = row.cells[DETAIL_COLUMN]
            page = replace(page, sections=(*page.sections, Section(DETAIL_SECTION, (detail,))))
        return render(page)

    def actions_for(self, row: ReadinessLine) -> Sequence[LogAction]:
        """No action on a readiness check: the release command is the writes' home."""
        return []

    def summary_text(self) -> str:
        if self.view is None:
            return not_evaluated_text(self.number)
        return readiness_summary(self.view)

    def open_row(self, row: ReadinessLine) -> None:
        """Enter on a reference row opens that record; Esc there returns to this row."""
        if row.record_id is None:
            return
        actor = str(getattr(self.app, "actor", "user:dev"))
        open_record(
            self, self.client, f"project:{self.project}", self.project, actor, row.record_id
        )
