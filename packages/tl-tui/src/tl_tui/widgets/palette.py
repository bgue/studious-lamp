"""Command palette: fuzzy search over commands and record keys (brief 10.2, sketch 3).

Ctrl+P or `:` opens it. Typing searches records (by key or title, through
`ClientInterface.search_linkable`) and filters the app's commands; Up/Down move, Enter runs the
highlighted entry, Tab narrows to all/records/commands, Esc closes. The palette only chooses: it
dismisses with a `PaletteChoice` and the app opens the record or runs the command.

STUB (P0-I3-T11): the types, layout (`compose`), constructor and key bindings are final; the
functions and methods marked `raise NotImplementedError` are the ticket. Remove this paragraph
when done.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from tl_core.services.link_queries import LinkTarget

from tl_tui.client import ClientInterface
from tl_tui.commands import APP_COMMANDS, AppCommand

Mode = Literal["all", "records", "commands"]
MODES: tuple[Mode, ...] = ("all", "records", "commands")
RECORD_LIMIT = 8


@dataclass(frozen=True)
class PaletteChoice:
    """What the user picked: open a record (``key``) or run an app command (``command_id``)."""

    kind: Literal["record", "command"]
    key: str | None = None
    command_id: str | None = None


@dataclass(frozen=True)
class PaletteRow:
    kind: Literal["header", "record", "command"]
    label: str
    detail: str = ""
    hint: str = ""
    choice: PaletteChoice | None = None


def fuzzy_score(query: str, text: str) -> int | None:
    """How well ``query`` matches ``text``: ``None`` if not at all, else a score (higher is better).

    Case-insensitive subsequence match of the query's non-space characters. Each matched character
    scores 1; +4 when it directly follows the previous match; +6 when it starts a word (the first
    character, or one after a character that is not a letter or digit); and +20 once when the whole
    query is a prefix of the text. An empty query scores 0 for every text.
    """
    raise NotImplementedError


def build_rows(
    query: str,
    commands: Sequence[AppCommand],
    records: Sequence[LinkTarget],
    mode: Mode = "all",
) -> list[PaletteRow]:
    """The rows to show: a ``Records`` section then a ``Commands`` section, each only if non-empty.

    ``records`` are used as given (the caller searched for them) unless ``mode`` is ``commands``.
    Commands are kept when ``fuzzy_score(query, label)`` is not ``None`` and sorted by score
    (highest first, ties in the original order); with an empty query all commands keep their order.
    ``mode`` ``records`` leaves out commands.
    """
    raise NotImplementedError


def row_line(row: PaletteRow, selected: bool, width: int) -> str:
    """One line of exactly ``width`` cells. A header is ``─ Label ───``. Other rows are
    ``▶ label  detail`` (``▶`` replaced by two spaces when not selected) with the hint
    right-aligned; the left part is cut with ``…`` to leave room for the hint and one space."""
    raise NotImplementedError


class CommandPalette(ModalScreen[PaletteChoice | None]):
    """Modal palette. Dismisses with the `PaletteChoice`, or ``None`` on Esc."""

    KEY_HINTS: ClassVar[str] = "↑↓ move  Enter run  Tab filter  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Close"),
        Binding("down", "move(1)", show=False),
        Binding("up", "move(-1)", show=False),
        Binding("tab", "next_mode", show=False),
    ]

    DEFAULT_CSS = """
    CommandPalette { align: center top; }
    CommandPalette > Vertical {
        width: 90%;
        max-width: 100;
        height: auto;
        max-height: 80%;
        margin-top: 2;
        border: round $accent;
        background: $surface;
        padding: 0 1;
    }
    CommandPalette #palette-list { height: auto; max-height: 20; border: none; }
    CommandPalette #palette-foot { color: $text-muted; }
    """

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        commands: Sequence[AppCommand] = APP_COMMANDS,
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.commands = tuple(commands)
        self.mode: Mode = "all"
        self.rows: list[PaletteRow] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Input(placeholder="Search records and commands", id="palette-input")
            yield OptionList(id="palette-list")
            yield Static("", id="palette-foot", markup=False)

    def on_mount(self) -> None:
        raise NotImplementedError

    def _records(self, query: str) -> list[LinkTarget]:
        raise NotImplementedError

    def _refresh(self) -> None:
        raise NotImplementedError

    def on_input_changed(self, event: Input.Changed) -> None:
        raise NotImplementedError

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raise NotImplementedError

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        raise NotImplementedError

    def _choose(self, index: int | None) -> None:
        raise NotImplementedError

    def action_move(self, delta: int) -> None:
        raise NotImplementedError

    def action_next_mode(self) -> None:
        raise NotImplementedError

    def action_cancel(self) -> None:
        raise NotImplementedError
