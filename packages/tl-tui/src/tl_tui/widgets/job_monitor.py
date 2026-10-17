"""The job monitor: the processing jobs of a project and where each stands (P1-I3).

Opened from the derived-documents screen with ``j``. The table lists jobs newest first with their
kind, state, attempt and the derived document they work on; the panel under it describes the
highlighted one (who asked, which extractor, when it ran, what went wrong). The table reads again
every few seconds while the screen is open, so a queued job is seen to run. ``c`` cancels a queued
job (a job a worker has taken cannot be cancelled), ``s`` narrows the list by state.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static
from tl_mod_documents.derivation.derived import CancelJob
from tl_mod_documents.derivation.views import JobView

from tl_tui.client import ClientInterface
from tl_tui.derive_text import JOB_COLUMNS, job_cells, job_detail_lines, jobs_summary, next_choice
from tl_tui.errors import CLIENT_ERRORS, describe_error

MAX_JOBS = 500
REFRESH_S = 2.0


class JobMonitorScreen(ModalScreen[None]):
    """The jobs of ``project`` (the id, not the scope), or of one derived document."""

    KEY_HINTS: ClassVar[str] = "s state  c cancel a queued job  F5 reload  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s", "state_filter", "State", show=False),
        Binding("c", "cancel", "Cancel", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    JobMonitorScreen { background: $surface; }
    JobMonitorScreen > Vertical { padding: 0 1; }
    JobMonitorScreen #jobs-title { text-style: bold; height: 1; }
    JobMonitorScreen #jobs-table { height: 1fr; min-height: 6; }
    JobMonitorScreen #jobs-detail { height: 8; border-top: solid $accent; padding: 0 1; }
    JobMonitorScreen #jobs-status { height: 1; }
    JobMonitorScreen #jobs-hints { height: 1; color: $text-muted; }
    """

    def __init__(
        self, client: ClientInterface, project: str, actor: str, *, derived: str | None = None
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.actor = actor
        self.derived = derived  # a derived document's key: only its jobs
        self.state: str | None = None
        self.views: list[JobView] = []  # as listed, before the screen's own filter
        self.shown: list[JobView] = []

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            what = f" of {self.derived}" if self.derived else ""
            yield Static(f"Jobs{what} in {self.project}", markup=False, id="jobs-title")
            yield DataTable[str](id="jobs-table", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="jobs-detail")
            yield Static("", markup=False, id="jobs-status")
            yield Static(self.KEY_HINTS, markup=False, id="jobs-hints")

    def on_mount(self) -> None:
        self.query_one("#jobs-table", DataTable).add_columns(*JOB_COLUMNS)
        self.reload()
        self.query_one("#jobs-table", DataTable).focus()
        self.set_interval(REFRESH_S, self.reload)  # a queued job is seen to start and finish

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the jobs again and keep the highlighted job where it is."""
        keep = self._key()
        try:
            self.views = self.client.list_processing_jobs(
                self.project, derived=self.derived, limit=MAX_JOBS
            )
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc), error=True)
            return
        self._fill(keep)

    def _fill(self, keep: str | None = None) -> None:
        """Apply the state filter to ``self.views`` and fill the table."""
        self.shown = [v for v in self.views if self.state is None or v.state == self.state]
        table = self.query_one("#jobs-table", DataTable)
        table.clear()
        for job in self.shown:
            # Text, not str: a cell is read as markup, and an error text may contain brackets
            table.add_row(*(Text(cell) for cell in job_cells(job)), key=job.id)
        if self.shown:
            ids = [j.id for j in self.shown]
            table.move_cursor(row=ids.index(keep) if keep in ids else 0)
        self.query_one("#jobs-status", Static).update(
            jobs_summary(len(self.shown), len(self.views), state=self.state)
        )
        self._describe()

    def _key(self) -> str | None:
        job = self.current()
        return job.id if job is not None else None

    def current(self) -> JobView | None:
        table = self.query_one("#jobs-table", DataTable)
        if not self.shown or not 0 <= table.cursor_row < len(self.shown):
            return None
        return self.shown[table.cursor_row]

    def _describe(self) -> None:
        """Show the highlighted job's facts (the listing has all of them: no extra call)."""
        detail = self.query_one("#jobs-detail", Static)
        job = self.current()
        if job is None:
            detail.update("No job matches.")
            return
        detail.update("\n".join(job_detail_lines(job)))

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#jobs-status", Static).update(("! " if error else "") + text)

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    # --- actions -------------------------------------------------------------------------

    def action_state_filter(self) -> None:
        """Show the next state: all, then each state that has a job, then all."""
        self.state = next_choice(self.state, [v.state for v in self.views])
        self._fill(self._key())

    def action_cancel(self) -> None:
        """Cancel the highlighted job when it is still queued (any signed-in person)."""
        job = self.current()
        if job is None:
            self._say("No job is highlighted.")
            return
        if job.state != "queued":
            self._say(f"{job.key} is {job.state}: only a queued job can be cancelled.")
            return
        try:
            self.client.cancel_job(
                CancelJob(
                    actor=self.actor,
                    source="tui",
                    scope=f"project:{self.project}",
                    job_id=job.id,
                    reason="cancelled in the job monitor",
                )
            )
        except CLIENT_ERRORS as exc:
            self.reload()  # the reload rewrites the status line: say the error last
            self._say(describe_error(exc), error=True)
            return
        self.reload()
        self._say(f"Cancelled {job.key}.")  # the reload rewrites the status line: say it last

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        self.dismiss(None)
