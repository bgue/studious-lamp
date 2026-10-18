"""Thread composer: a one-line modal that posts a message or previews and confirms a slash command
(P1-I7; brief 21.5, sketch 13).

It reuses the post composer's token rules (`#` records and tags, `@` people) and adds verb
completion after a leading ``/``. Enter sends. A line that starts with ``/`` is *previewed* first:
the panel shows what would run, with the caller's own access, and Enter again confirms exactly that
plan (the preview's token); Esc goes back to editing. A message that does not start with ``/`` is
posted and never dispatches. The composer parses nothing and decides nothing: the server previews
and runs.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option
from tl_core.services.feed_queries import Completion
from tl_core.threads.dispatch import DispatchFromThread
from tl_core.threads.errors import DispatchStaleError
from tl_core.threads.messages import PostThreadMessage

from tl_tui.client import ClientInterface
from tl_tui.compose_text import preview_lines, verb_candidates
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.widgets.composer import apply_completion, completion_token

Stage = Literal["edit", "confirm"]


def verb_token(text: str, cursor: int) -> tuple[str, int] | None:
    """``(prefix, start)`` of the verb being typed after a leading ``/``, else ``None``.

    The text must start with ``/`` (white space before it is allowed) and the cursor must be inside
    the first word: ``"/li"`` at 3 gives ``("li", 1)``; ``"/link A"`` at 7 gives ``None``.
    """
    stripped = text.lstrip()
    lead = len(text) - len(stripped)
    if not stripped.startswith("/") or cursor < lead + 1:
        return None
    rest = stripped[1:]
    word = rest.split(None, 1)[0] if rest.strip() else ""
    end = lead + 1 + len(word)
    if " " in text[lead + 1 : cursor] or cursor > end:
        return None
    return text[lead + 1 : cursor], lead + 1


class ThreadComposer(ModalScreen[str | None]):
    """Dismisses with the id of the new message, or ``None`` when cancelled."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("down", "choose(1)", "Next", show=False),
        Binding("up", "choose(-1)", "Previous", show=False),
        Binding("tab", "accept", "Complete", show=False, priority=True),
        Binding("ctrl+s", "submit", "Send", show=False),
    ]

    DEFAULT_CSS = """
    ThreadComposer { align: center middle; }
    ThreadComposer > Vertical {
        width: 80%;
        height: auto;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    ThreadComposer #tc-title { text-style: bold; }
    ThreadComposer #tc-popup { height: auto; max-height: 8; display: none; }
    ThreadComposer #tc-preview { height: auto; display: none; }
    ThreadComposer #tc-error { color: $error; height: auto; }
    """

    def __init__(
        self,
        client: ClientInterface,
        record: dict[str, Any],
        *,
        actor: str = "user:dev",
        dispatch: bool = True,
        limit: int = 8,
    ) -> None:
        super().__init__()
        self.client = client
        self.record = record
        self.actor = actor
        self.dispatch_on = dispatch
        self.limit = limit
        self.stage: Stage = "edit"
        self.candidates: list[tuple[str, str, str]] = []  # (sigil, text to insert, detail)
        self.token: tuple[str, str, int] | None = None  # (sigil, prefix, start)
        self.popup_closed = False
        self._preview: Any = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Thread · {self.record.get('key') or self.record['id']}", id="tc-title")
            yield Input(
                placeholder="Message. / for commands, # for records, @ for people", id="tc-input"
            )
            yield OptionList(id="tc-popup")
            yield Static("", id="tc-preview", markup=False)
            yield Static("", id="tc-error", markup=False)

    def on_mount(self) -> None:
        self.query_one("#tc-input", Input).focus()

    @property
    def popup_visible(self) -> bool:
        return self.stage == "edit" and bool(self.candidates) and not self.popup_closed

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        if self.stage == "confirm":  # an edit after a preview: the preview no longer applies
            self._back_to_edit()
        self.query_one("#tc-error", Static).update("")
        self.popup_closed = False
        self._refresh_popup()

    def _refresh_popup(self) -> None:
        inp = self.query_one("#tc-input", Input)
        popup = self.query_one("#tc-popup", OptionList)
        self.candidates = []
        self.token = None
        verb = verb_token(inp.value, inp.cursor_position)
        if verb is not None:
            prefix, start = verb
            self.token = ("/", prefix, start)
            self.candidates = [("/", v, h) for v, h in verb_candidates(prefix)]
        else:
            found = completion_token(inp.value, inp.cursor_position)
            if found is not None:
                sigil, prefix, start = found
                self.token = (sigil, prefix, start)
                items: list[Completion] = []
                try:
                    items = self.client.feed_complete(
                        self.record["scope"], sigil, prefix, limit=self.limit
                    )
                except CLIENT_ERRORS as exc:
                    self.query_one("#tc-error", Static).update(describe_error(exc))
                self.candidates = [(sigil, c.text, c.detail) for c in items]
        popup.clear_options()
        popup.add_options(
            [
                Option(Text(f"{text}   {detail}"), id=str(n))
                for n, (_, text, detail) in enumerate(self.candidates)
            ]
        )
        popup.highlighted = 0 if self.candidates else None
        popup.styles.display = "block" if self.popup_visible else "none"

    def action_choose(self, delta: int) -> None:
        if not self.popup_visible:
            return
        popup = self.query_one("#tc-popup", OptionList)
        popup.highlighted = max(0, min(len(self.candidates) - 1, (popup.highlighted or 0) + delta))

    def action_accept(self) -> None:
        """Tab: put the highlighted candidate into the input."""
        if not self.popup_visible or self.token is None:
            return
        popup = self.query_one("#tc-popup", OptionList)
        index = popup.highlighted
        if index is None or index >= len(self.candidates):
            return
        sigil, text, _ = self.candidates[index]
        inp = self.query_one("#tc-input", Input)
        start = self.token[2]
        new_text, cursor = apply_completion(
            inp.value, inp.cursor_position, start, "" if sigil == "/" else sigil, text
        )
        inp.value = new_text
        inp.cursor_position = cursor

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.action_submit()

    def action_submit(self) -> None:
        """Enter or Ctrl+S. Edit stage: post a message, or preview a ``/`` command. Confirm stage:
        run the previewed command."""
        error = self.query_one("#tc-error", Static)
        inp = self.query_one("#tc-input", Input)
        body = inp.value
        if self.stage == "confirm":
            self._confirm(body)
            return
        if not body.strip():
            error.update("Write something first")
            return
        if body.lstrip().startswith("/"):
            self._show_preview(body)
            return
        try:
            result = self.client.thread_post(
                PostThreadMessage(
                    actor=self.actor,
                    source="tui",
                    scope=self.record["scope"],
                    record_id=self.record["id"],
                    body=body,
                )
            )
        except CLIENT_ERRORS as exc:
            error.update(describe_error(exc))
            return
        self.dismiss(result.key)

    def _show_preview(self, body: str) -> None:
        error = self.query_one("#tc-error", Static)
        if not self.dispatch_on:
            error.update("Dispatch is switched off for this record")
            return
        try:
            answer = self.client.thread_preview(self.record["id"], body)
        except CLIENT_ERRORS as exc:
            error.update(describe_error(exc))
            return
        if answer.problem is not None:
            error.update(f"{answer.problem.code}: {answer.problem.message}")
            return
        assert answer.preview is not None
        self._preview = answer.preview
        error.update("")
        panel = self.query_one("#tc-preview", Static)
        panel.update("\n".join(preview_lines(answer.preview)))
        panel.styles.display = "block"
        self.query_one("#tc-popup", OptionList).styles.display = "none"
        self.stage = "confirm"

    def _confirm(self, body: str) -> None:
        error = self.query_one("#tc-error", Static)
        preview = self._preview
        if preview is None or not preview.can_dispatch:
            return
        try:
            result = self.client.thread_dispatch(
                DispatchFromThread(
                    actor=self.actor,
                    source="tui",
                    scope=self.record["scope"],
                    record_id=self.record["id"],
                    text=body,
                    token=preview.token,
                    expires_at=preview.expires_at,
                )
            )
        except DispatchStaleError:
            self._back_to_edit()
            error.update("The plan changed since the preview: preview it again")
            return
        except CLIENT_ERRORS as exc:
            self._back_to_edit()
            error.update(describe_error(exc))
            return
        self.dismiss(result.key)

    def _back_to_edit(self) -> None:
        self.stage = "edit"
        self._preview = None
        panel = self.query_one("#tc-preview", Static)
        panel.update("")
        panel.styles.display = "none"

    def action_cancel(self) -> None:
        """Esc: confirm stage back to edit; an open list closes; otherwise cancel."""
        if self.stage == "confirm":
            self._back_to_edit()
            return
        if self.popup_visible:
            self.popup_closed = True
            self.query_one("#tc-popup", OptionList).styles.display = "none"
            return
        self.dismiss(None)
