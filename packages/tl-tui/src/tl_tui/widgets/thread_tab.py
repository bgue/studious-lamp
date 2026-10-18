"""Thread tab of the record view: the messages of a record, its participants and the dispatch
result cards (P1-I7; brief 21.5, sketch 13).

``c`` composes (the thread composer, which also takes slash commands), ``o`` loads older messages.
The tab reads only through `ClientInterface` and shows the lines of `tl_tui.thread_text`; it decides
nothing about what a command line means.
"""

from __future__ import annotations

from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static
from tl_core.threads.queries import ThreadPage

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.messages import RecordChanged, StatusMessage
from tl_tui.thread_text import header_text, message_lines

PAGE_SIZE = 50


class ThreadTab(Vertical, can_focus=True):
    """Shows ``client.thread_page(record id)``; ``show_record`` loads it."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("c", "compose", "Compose", show=False),
        Binding("o", "older", "Older", show=False),
    ]

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        *,
        actor: str = "user:dev",
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(id=id)
        self.client = client
        self.scope = scope
        self.actor = actor
        self.record: dict[str, Any] | None = None
        self.page: ThreadPage | None = None
        self._older: list[ThreadPage] = []

    def compose(self) -> ComposeResult:
        yield Static("", id="thread-header", markup=False)
        with VerticalScroll():
            yield Static("", id="thread-body", markup=False)
        yield Static("", id="thread-hint", markup=False)

    def show_record(self, record: dict[str, Any]) -> None:
        """Load the newest page of the record's thread and draw it."""
        self.record = record
        self._older = []
        self.reload()

    def reload(self) -> None:
        if self.record is None:
            return
        try:
            self.page = self.client.thread_page(self.record["id"], limit=PAGE_SIZE)
        except NotImplementedError:  # a client with no threads: the tab stays empty
            self.page = None
            self._draw()
            return
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return
        self._draw()

    def _draw(self) -> None:
        page = self.page
        header = self.query_one("#thread-header", Static)
        body = self.query_one("#thread-body", Static)
        hint = self.query_one("#thread-hint", Static)
        if page is None:
            header.update("")
            body.update("")
            hint.update("")
            return
        header.update(header_text(page))
        pages = [*reversed(self._older), page]
        lines = [line for p in pages for line in message_lines(p)]
        if not lines:
            lines = [
                "No messages yet." if page.enabled else "Threads are not switched on for this type."
            ]
        body.update(Text("\n".join(lines)))
        oldest = pages[0]
        more = "  o older" if oldest.next_before is not None else ""
        hint.update("c compose · / for commands" + more if page.enabled else "")

    def action_older(self) -> None:
        """Load the page before the oldest one shown and draw it above."""
        pages = [*reversed(self._older), self.page] if self.page is not None else []
        if not pages or pages[0] is None or pages[0].next_before is None or self.record is None:
            return
        try:
            older = self.client.thread_page(
                self.record["id"], limit=PAGE_SIZE, before_seq=pages[0].next_before
            )
        except CLIENT_ERRORS as exc:
            self.post_message(StatusMessage(describe_error(exc), "error"))
            return
        self._older.append(older)
        self._draw()

    def action_compose(self) -> None:
        """Open the thread composer; a posted or dispatched message reloads the tab."""
        if self.record is None or self.page is None or not self.page.enabled:
            self.post_message(
                StatusMessage("Threads are not switched on for this record", "warning")
            )
            return
        from tl_tui.widgets.thread_composer import ThreadComposer  # noqa: PLC0415

        record = self.record

        def done(message_id: str | None) -> None:
            if message_id:
                self.reload()
                self.post_message(RecordChanged(record["id"]))

        self.app.push_screen(
            ThreadComposer(
                self.client, record, actor=self.actor, dispatch=self.page.dispatch_enabled
            ),
            done,
        )
