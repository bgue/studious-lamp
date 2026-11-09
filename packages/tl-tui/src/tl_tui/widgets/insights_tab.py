"""Insights tab of the record view (P2-INS T03; T02b placed the pane).

Four subtabs: Checks (the record's findings, read off the UI thread), and Suggestions, Analysis
and Ask, each one plain line. ``Left`` and ``Right`` switch subtabs. On the Checks subtab ``Up``
and ``Down`` move the cursor over the findings, and ``Enter`` opens the record the highlighted
finding points to. The first time one of the three unbuilt subtabs is opened in an app session,
``client.note_need`` records the need with the record's type only (never its id); the noted pairs
are kept per app, so a rebuilt tab in the same app does not note them again. The tab reads only
through ``ClientInterface`` and draws the lines of ``tl_tui.insights_text``.
"""

from __future__ import annotations

import weakref
from collections.abc import Callable
from typing import Any, ClassVar

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static
from textual.worker import get_current_worker
from tl_core.insights.types import CheckFinding

from tl_tui.client import ClientInterface
from tl_tui.display import Labels, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.insights_text import (
    REQUEST_KIND,
    SUBTABS,
    checks_rows,
    ordered_findings,
    reference_of,
    subtab_line,
    trigger_of,
    unavailable_line,
)
from tl_tui.labels_load import load_labels
from tl_tui.messages import OpenRecord, StatusMessage

# The (record type, subtab) pairs already noted, per app: a rebuilt tab in the same app notes
# nothing twice. Keyed weakly, so a closed app takes its set with it.
_NOTED: weakref.WeakKeyDictionary[App[Any], set[tuple[str, str]]] = weakref.WeakKeyDictionary()


class InsightsTab(Vertical, can_focus=True):
    """Shows the open subtab of the record that ``show_record`` gave it."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("left", "subtab(-1)", "Previous subtab", show=False),
        Binding("right", "subtab(1)", "Next subtab", show=False),
        Binding("up", "cursor(-1)", "Previous finding", show=False),
        Binding("down", "cursor(1)", "Next finding", show=False),
        Binding("enter", "open_finding", "Open", show=False),
    ]

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        *,
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(id=id)
        self.client = client
        self.scope = scope
        self.record: dict[str, Any] | None = None
        self.subtab = "checks"
        self.findings: list[CheckFinding] | None = None  # None until the first read ends
        self.cursor = 0  # the highlighted finding, in the order the Checks subtab shows them
        self.labels = Labels()
        self._gen = 0  # a read that ends after the record changed is dropped

    def compose(self) -> ComposeResult:
        yield Static("", id="insights-subtabs", markup=False)
        with VerticalScroll():
            yield Static("", id="insights-body", markup=False)

    def on_mount(self) -> None:
        """The service labels once per tab; a failed read leaves the labels empty."""
        self.labels = load_labels(self.client, self.scope, ())

    def refresh_for_display_mode(self) -> None:
        """Draw the Checks lines again in the current mode."""
        self._draw()

    def show_record(self, record: dict[str, Any]) -> None:
        """Keep the record, read its checks off the UI thread, and draw the open subtab."""
        self.record = record
        self.findings = None
        self.cursor = 0
        self._draw()
        self._read_checks()
        self._note_open_subtab()

    # --- reads ----------------------------------------------------------------------------

    def _read_checks(self) -> None:
        if self.record is None:
            return
        self._gen += 1
        self.run_worker(
            self._read(self._gen, str(self.record["id"])),
            thread=True,
            group="insights-checks",
            exclusive=True,
        )

    def _read(self, gen: int, record_id: str) -> Callable[[], None]:
        def work() -> None:
            found: list[CheckFinding] | None
            failure = ""
            try:
                found = self.client.checks(record_id)
            except NotImplementedError:
                found = []
            except CLIENT_ERRORS as exc:
                found, failure = None, describe_error(exc)
            if get_current_worker().is_cancelled:
                return
            self._call(self._loaded, gen, found, failure)

        return work

    def _loaded(self, gen: int, found: list[CheckFinding] | None, failure: str) -> None:
        if gen != self._gen or not self.is_attached:
            return
        if found is not None:
            self.findings = found
            self.cursor = min(self.cursor, max(len(found) - 1, 0))
            self._draw()
        if failure:  # the display stays as it was
            self.post_message(StatusMessage(failure, "error"))

    def _call(self, fn: Callable[..., None], *args: object) -> None:
        """Run ``fn`` on the UI thread (from the worker thread); nothing if the app is gone."""
        try:
            self.app.call_from_thread(fn, *args)
        except RuntimeError:
            pass

    # --- the three unbuilt subtabs --------------------------------------------------------

    def _note_open_subtab(self) -> None:
        """Note the open subtab once per (record type, subtab) for this session. Checks writes
        nothing. ``note_need`` never raises by contract; the screen is safe even if it does."""
        if self.record is None or self.subtab == "checks":
            return
        pair = (str(self.record["type"]), self.subtab)
        noted = _NOTED.setdefault(self.app, set())
        if pair in noted:
            return
        noted.add(pair)
        try:
            self.client.note_need(
                request_kind=REQUEST_KIND[self.subtab],
                trigger=trigger_of(self.subtab),
                record_type=pair[0],
            )
        except Exception:  # noqa: BLE001 - a refused or failed note changes nothing on screen
            return

    # --- actions --------------------------------------------------------------------------

    def action_subtab(self, step: int) -> None:
        """Move to the next (1) or previous (-1) subtab, wrapping around."""
        index = SUBTABS.index(self.subtab)
        self.subtab = SUBTABS[(index + step) % len(SUBTABS)]
        self._draw()
        self._note_open_subtab()

    def action_cursor(self, step: int) -> None:
        """Move the highlight to the next (1) or previous (-1) finding, stopping at the ends."""
        if self.subtab != "checks" or not self.findings:
            return
        self.cursor = min(max(self.cursor + step, 0), len(self.findings) - 1)
        self._draw()

    def action_open_finding(self) -> None:
        """Open the first record the highlighted finding points to (Checks only). A finding with
        no record it points to does nothing."""
        if self.subtab != "checks" or not self.findings:
            return
        ref = reference_of(ordered_findings(self.findings)[self.cursor])
        if ref is None:
            return
        self.post_message(OpenRecord(self.scope, ref.key, follow=True))

    # --- drawing --------------------------------------------------------------------------

    def _draw(self) -> None:
        tabs = self.query_one("#insights-subtabs", Static)
        body = self.query_one("#insights-body", Static)
        tabs.update(subtab_line(self.subtab))
        if self.subtab != "checks":
            body.update(Text(unavailable_line(self.subtab)))
            return
        if self.findings is None:
            body.update(Text(""))
            return
        technical = mode_of(self.app).technical
        text = Text()
        for position, (index, line) in enumerate(
            checks_rows(self.findings, self.labels, technical=technical)
        ):
            if position:
                text.append("\n")
            start = len(text)
            text.append(line)
            if index is not None and index == self.cursor:
                text.stylize("reverse", start, len(text))  # the highlighted finding
        body.update(text)
