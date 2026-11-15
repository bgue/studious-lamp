"""The toolcrib fast-entry screen: issue or return a tool in one line (P2-I4B-T06; brief §10.5).

A full-size modal, opened from the palette (``toolcrib``). ``F2`` (issue, the default) and ``F3``
or ``Ctrl+R`` (return) choose the mode; the line is ``<tool> <person> [xN]`` and ``Enter`` sends one
``IssueStock`` or ``ReturnStock`` through ``client.materials_command``. The status line says what
happened and the line is cleared with the focus kept in it; a refusal keeps what was typed. Every
word, check and command lives in ``tl_tui.toolcrib_text``; this screen reads the crib's stock and
makes the one command call.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.toolcrib_text import (
    KEYS,
    ToolcribError,
    build_command,
    check_line,
    crib_choices,
    done_text,
    mode_title,
    parse_line,
    resolve_tool,
)

_LINE = "#tc-line"
_NO_CRIB = "No toolcrib {code} in this project. Pick a toolcrib location."


class ToolcribScreen(ModalScreen[None]):
    """Issues and returns tools at one toolcrib. Esc closes it."""

    KEY_HINTS: ClassVar[str] = KEYS

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("f2", "mode('issue')", "Issue", show=False),
        Binding("f3", "mode('return')", "Return", show=False),
        Binding("ctrl+r", "mode('return')", "Return", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    ToolcribScreen { background: $surface; align: center top; }
    ToolcribScreen > Vertical { height: 100%; padding: 0 1; }
    ToolcribScreen #tc-title { text-style: bold; height: 1; }
    ToolcribScreen .tc-row { height: auto; }
    ToolcribScreen .tc-label { width: 14; height: 1; }
    ToolcribScreen .tc-error { height: auto; color: $error; padding-left: 14; }
    ToolcribScreen Input { height: 1; border: none; padding: 0 1; width: 1fr; }
    ToolcribScreen Input:focus { border: none; }
    ToolcribScreen #tc-status { height: auto; min-height: 1; margin-top: 1; }
    ToolcribScreen #tc-keys { height: 1; color: $text-muted; }
    """

    def __init__(self, client: ClientInterface, project: str, actor: str, crib: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.actor = actor
        self.crib = crib
        self.mode = "issue"
        self.ready = False  # True once the crib is found among the project's toolcribs

    # --- layout -----------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._title(), markup=False, id="tc-title")
            with Horizontal(classes="tc-row"):
                yield Static("Tool, person", markup=False, classes="tc-label")
                yield Input(id="tc-line", placeholder="lot or item, person, xN")
            yield Static("", markup=False, classes="tc-error", id="tc-error")
            yield Static("", markup=False, id="tc-status")
            yield Static(KEYS, markup=False, id="tc-keys")

    def on_mount(self) -> None:
        try:
            locations = self.client.list_materials_locations(self.project)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            locations = []
        if self.crib in crib_choices(locations):
            self.ready = True
        else:
            self.say(_NO_CRIB.format(code=self.crib), error=True)
        self.query_one(_LINE, Input).focus()

    def _title(self) -> str:
        return f"{mode_title(self.mode)} · crib {self.crib} · {self.project}"

    # --- the status line and the field error --------------------------------------------------

    def say(self, text: str, *, error: bool = False) -> None:
        """Write the status line; an error is marked ``! ``."""
        self.query_one("#tc-status", Static).update(("! " if error else "") + text)

    def _show_errors(self, messages: list[str]) -> None:
        self.query_one("#tc-error", Static).update("\n".join(messages))

    def _refuse(self, text: str) -> None:
        """A refusal: the text on the status line and under the field; the line keeps its text."""
        self._show_errors([text])
        self.say(text, error=True)

    # --- the keys -----------------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tc-line":
            self._show_errors([])  # the typed line is no longer what was wrong

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if event.input.id == "tc-line":
            self.action_send()

    def action_mode(self, mode: str) -> None:
        """Choose issue or return; the typed line stays and keeps the focus."""
        self.mode = mode
        self.query_one("#tc-title", Static).update(self._title())
        self.query_one(_LINE, Input).focus()

    def action_send(self) -> None:
        """Send one command for the line; on success the line is cleared, on a refusal it keeps
        what was typed."""
        line = self.query_one(_LINE, Input)
        parsed = parse_line(line.value)
        errors = check_line(self.mode, parsed)
        if errors:
            self._show_errors([message for _, message in errors])
            self.say(errors[0][1], error=True)
            return
        if not self.ready:
            self.say(_NO_CRIB.format(code=self.crib), error=True)
            return
        try:
            rows = self.client.list_materials_stock(self.project, location=self.crib)
            row = resolve_tool(parsed.tool, rows)
            cmd = build_command(
                self.mode,
                lot=row.lot,
                uom=row.uom,
                qty=parsed.qty,
                person=parsed.person,
                crib=self.crib,
                actor=self.actor,
                project=self.project,
            )
            name = "IssueStock" if self.mode == "issue" else "ReturnStock"
            self.client.materials_command(name, cmd)
        except ToolcribError as exc:
            self._refuse(str(exc))
            return
        except CLIENT_ERRORS as exc:
            self._refuse(describe_error(exc))
            return
        self.say(done_text(self.mode, parsed.qty, row.uom, row.lot, parsed.person))
        line.value = ""
        line.focus()

    def action_close(self) -> None:
        self.dismiss(None)
