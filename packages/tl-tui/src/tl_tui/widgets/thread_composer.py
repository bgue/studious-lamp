"""Thread composer: a one-line modal that posts a message or previews and confirms a slash command
(P1-I7; brief 21.5, sketch 13).

It reuses the post composer's token rules (`#` records and tags, `@` people) and adds verb
completion after a leading ``/``. Enter sends. A line that starts with ``/`` is *previewed* first:
the panel shows what would run, with the caller's own access, and Enter again confirms exactly that
plan (the preview's token); Esc goes back to editing. A message that does not start with ``/`` is
posted and never dispatches. The composer parses nothing and decides nothing: the server previews
and runs.

STUB: verb_token and the bodies of ThreadComposer._refresh_popup, action_accept, action_submit,
_show_preview, _confirm and action_cancel are yours to write (ticket P1-I7-T11b). Remove this
paragraph, every STEPS comment and the two lint-silencing lines below when you are done.
"""

# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false

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
    # STEPS
    # 1. stripped = text.lstrip(); lead = len(text) - len(stripped).
    # 2. Return None when stripped does not start with "/" or cursor < lead + 1.
    # 3. word = the first word of stripped[1:] (stripped[1:].split(None, 1)[0]), or "" when
    #    stripped[1:] is blank. end = lead + 1 + len(word).
    # 4. Return None when there is a space in text[lead + 1 : cursor] or cursor > end.
    # 5. Return (text[lead + 1 : cursor], lead + 1).
    raise NotImplementedError


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
        # STEPS
        # 1. inp = #tc-input, popup = #tc-popup. self.candidates = []; self.token = None.
        # 2. verb = verb_token(inp.value, inp.cursor_position). When it is not None: prefix,
        #    start = verb; self.token = ("/", prefix, start); self.candidates = [("/", v, h)
        #    for v, h in verb_candidates(prefix)].
        # 3. Otherwise found = completion_token(inp.value, inp.cursor_position). When it is
        #    not None: sigil, prefix, start = found; self.token = (sigil, prefix, start);
        #    try items = self.client.feed_complete(self.record["scope"], sigil, prefix,
        #    limit=self.limit); on CLIENT_ERRORS show describe_error(exc) in #tc-error and
        #    use items = []. self.candidates = [(sigil, c.text, c.detail) for c in items].
        # 4. popup.clear_options(); add one Option(Text(f"{text}   {detail}"), id=str(n))
        #    per candidate (three spaces); popup.highlighted = 0 when there are candidates,
        #    else None; popup.styles.display = "block" when self.popup_visible, else "none".
        raise NotImplementedError

    def action_choose(self, delta: int) -> None:
        if not self.popup_visible:
            return
        popup = self.query_one("#tc-popup", OptionList)
        popup.highlighted = max(0, min(len(self.candidates) - 1, (popup.highlighted or 0) + delta))

    def action_accept(self) -> None:
        """Tab: put the highlighted candidate into the input."""
        # STEPS
        # 1. Return when not self.popup_visible or self.token is None.
        # 2. popup = #tc-popup; index = popup.highlighted. Return when index is None or
        #    index >= len(self.candidates).
        # 3. sigil, text, _ = self.candidates[index]. inp = #tc-input. start = the third
        #    item of self.token.
        # 4. new_text, cursor = apply_completion(inp.value, inp.cursor_position, start, ""
        #    if sigil == "/" else sigil, text). Set inp.value = new_text and
        #    inp.cursor_position = cursor.
        raise NotImplementedError

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.action_submit()

    def action_submit(self) -> None:
        """Enter or Ctrl+S. Edit stage: post a message, or preview a ``/`` command. Confirm stage:
        run the previewed command."""
        # STEPS
        # 1. error = #tc-error; inp = #tc-input; body = inp.value (not stripped).
        # 2. In the confirm stage (self.stage == "confirm") call self._confirm(body) and
        #    return.
        # 3. A blank body (not body.strip()): error.update("Write something first"); return.
        # 4. A body whose lstrip() starts with "/": self._show_preview(body); return.
        # 5. Otherwise try result =
        #    self.client.thread_post(PostThreadMessage(actor=self.actor, source="tui",
        #    scope=self.record["scope"], record_id=self.record["id"], body=body)); on
        #    CLIENT_ERRORS show describe_error(exc) in error and return (the text stays).
        # 6. self.dismiss(result.key).
        raise NotImplementedError

    def _show_preview(self, body: str) -> None:
        # STEPS
        # 1. error = #tc-error. When not self.dispatch_on: error.update("Dispatch is
        #    switched off for this record"); return.
        # 2. Try answer = self.client.thread_preview(self.record["id"], body); on
        #    CLIENT_ERRORS show describe_error(exc) in error and return.
        # 3. When answer.problem is not None: error.update(f"{answer.problem.code}:
        #    {answer.problem.message}"); return.
        # 4. assert answer.preview is not None. self._preview = answer.preview. panel = #tc-
        #    preview: panel.update("\n".join(preview_lines(answer.preview)));
        #    panel.styles.display = "block".
        # 5. Hide the list (#tc-popup styles.display = "none") and set self.stage =
        #    "confirm".
        raise NotImplementedError

    def _confirm(self, body: str) -> None:
        # STEPS
        # 1. error = #tc-error; preview = self._preview. Return when preview is None or not
        #    preview.can_dispatch.
        # 2. Try result = self.client.thread_dispatch(DispatchFromThread(actor=self.actor,
        #    source="tui", scope=self.record["scope"], record_id=self.record["id"],
        #    text=body, token=preview.token, expires_at=preview.expires_at)).
        # 3. except DispatchStaleError: self._back_to_edit(); error.update("The plan changed
        #    since the preview: preview it again"); return.
        # 4. except CLIENT_ERRORS as exc: self._back_to_edit();
        #    error.update(describe_error(exc)); return.
        # 5. self.dismiss(result.key).
        raise NotImplementedError

    def _back_to_edit(self) -> None:
        self.stage = "edit"
        self._preview = None
        panel = self.query_one("#tc-preview", Static)
        panel.update("")
        panel.styles.display = "none"

    def action_cancel(self) -> None:
        """Esc: confirm stage back to edit; an open list closes; otherwise cancel."""
        # STEPS
        # 1. In the confirm stage: self._back_to_edit(); return.
        # 2. When self.popup_visible: self.popup_closed = True; hide #tc-popup
        #    (styles.display = "none"); return.
        # 3. Otherwise self.dismiss(None).
        raise NotImplementedError
