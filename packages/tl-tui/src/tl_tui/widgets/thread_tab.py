"""Thread tab of the record view: the messages of a record, its participants and the dispatch
result cards (P1-I7; brief 21.5, sketch 13).

``c`` composes (the thread composer, which also takes slash commands), ``o`` loads older messages.
The tab reads only through `ClientInterface` and shows the lines of `tl_tui.thread_text`; it decides
nothing about what a command line means.

STUB: reload, _draw, action_older and action_compose are yours to write (ticket P1-I7-T11a).
Remove this paragraph, every STEPS comment and the two lint-silencing lines below when you are
done.
"""

# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false

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
        # STEPS
        # 1. When self.record is None return.
        # 2. Try self.page = self.client.thread_page(self.record["id"], limit=PAGE_SIZE).
        # 3. except NotImplementedError (a client with no threads): self.page = None;
        #    self._draw(); return.
        # 4. except CLIENT_ERRORS as exc: post StatusMessage(describe_error(exc), "error")
        #    and return (the display is kept).
        # 5. After the try call self._draw().
        raise NotImplementedError

    def _draw(self) -> None:
        # STEPS
        # 1. header, body and hint are the Statics #thread-header, #thread-body and #thread-
        #    hint (query_one(..., Static)). page = self.page.
        # 2. page is None: update all three with "" and return.
        # 3. header.update(header_text(page)). pages = [*reversed(self._older), page]; lines
        #    = every line of message_lines(p) for p in pages, in order.
        # 4. No lines: lines = ["No messages yet."] when page.enabled, else ["Threads are
        #    not switched on for this type."].
        # 5. body.update(Text("\n".join(lines))). oldest = pages[0]; more = "  o older" when
        #    oldest.next_before is not None, else "".
        # 6. hint.update("c compose · / for commands" + more) when page.enabled, else
        #    hint.update("").
        raise NotImplementedError

    def action_older(self) -> None:
        """Load the page before the oldest one shown and draw it above."""
        # STEPS
        # 1. pages = [*reversed(self._older), self.page] when self.page is not None, else
        #    [].
        # 2. Return when pages is empty, when pages[0] is None, when pages[0].next_before is
        #    None or when self.record is None.
        # 3. Try older = self.client.thread_page(self.record["id"], limit=PAGE_SIZE,
        #    before_seq=pages[0].next_before); on CLIENT_ERRORS post
        #    StatusMessage(describe_error(exc), "error") and return.
        # 4. self._older.append(older); self._draw().
        raise NotImplementedError

    def action_compose(self) -> None:
        """Open the thread composer; a posted or dispatched message reloads the tab."""
        # STEPS
        # 1. When self.record is None, self.page is None or not self.page.enabled: post
        #    StatusMessage("Threads are not switched on for this record", "warning") and
        #    return.
        # 2. Import ThreadComposer from tl_tui.widgets.thread_composer inside the function
        #    (as written). record = self.record.
        # 3. Define done(message_id: str | None): when message_id is set, self.reload() and
        #    post RecordChanged(record["id"]).
        # 4. self.app.push_screen(ThreadComposer(self.client, record, actor=self.actor,
        #    dispatch=self.page.dispatch_enabled), done).
        raise NotImplementedError
