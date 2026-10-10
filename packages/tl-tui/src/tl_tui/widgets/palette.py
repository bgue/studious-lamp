"""Command palette: fuzzy search over commands and record keys (brief 10.2, sketch 3).

Ctrl+P or `:` opens it. Typing searches records (by key or title, through
`ClientInterface.search_linkable`) and filters the app's commands; Up/Down move, Enter runs the
highlighted entry, Tab narrows to all/records/commands, Esc closes. The palette only chooses: it
dismisses with a `PaletteChoice` and the app opens the record or runs the command.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal

from rich.cells import cell_len, set_cell_size
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option
from tl_core.services.link_queries import LinkTarget

from tl_tui.client import ClientInterface
from tl_tui.commands import APP_COMMANDS, AppCommand
from tl_tui.errors import CLIENT_ERRORS
from tl_tui.text import EMPTY

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
    needle = "".join(query.lower().split())
    if not needle:
        return 0
    lowered = text.lower()
    score = 0
    position = 0
    previous = -2
    for char in needle:
        found = lowered.find(char, position)
        if found < 0:
            return None
        score += 1
        if found == previous + 1:
            score += 4
        if found == 0 or not lowered[found - 1].isalnum():
            score += 6
        previous = found
        position = found + 1
    if lowered.startswith(needle):
        score += 20
    return score


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
    rows: list[PaletteRow] = []
    if mode != "commands" and records:
        rows.append(PaletteRow("header", "Records"))
        for target in records:
            rows.append(
                PaletteRow(
                    "record",
                    target.key or EMPTY,
                    f"{target.title} · {target.status or EMPTY}",
                    "Enter",
                    PaletteChoice("record", key=target.key),
                )
            )
    if mode != "records":
        scored: list[tuple[int, int, AppCommand]] = []
        for index, command in enumerate(commands):
            score = fuzzy_score(query, command.label)
            if score is not None:
                scored.append((score, index, command))
        scored.sort(key=lambda item: (-item[0], item[1]))
        if scored:
            rows.append(PaletteRow("header", "Commands"))
            for _, _, command in scored:
                rows.append(
                    PaletteRow(
                        "command",
                        command.label,
                        "",
                        command.keys,
                        PaletteChoice("command", command_id=command.id),
                    )
                )
    return rows


def row_line(row: PaletteRow, selected: bool, width: int) -> str:
    """One line of exactly ``width`` cells. A header is ``─ Label ───``. Other rows are
    ``▶ label  detail`` (``▶`` replaced by two spaces when not selected) with the hint
    right-aligned; the left part is cut with ``…`` to leave room for the hint and one space."""
    if row.kind == "header":
        head = f"─ {row.label} "
        return set_cell_size(head + "─" * (width - cell_len(head)), width)
    left = ("▶ " if selected else "  ") + row.label + (f"  {row.detail}" if row.detail else "")
    room = width - (cell_len(row.hint) + 1 if row.hint else 0)
    if cell_len(left) > room:
        left = set_cell_size(left, room - 1) + "…" if room > 0 else ""
    gap = max(0, width - cell_len(left) - cell_len(row.hint))
    return set_cell_size(left + " " * gap + row.hint, width)


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
        self.query_one("#palette-input", Input).focus()
        self._refresh()

    def _records(self, query: str) -> list[LinkTarget]:
        if not query.strip():
            return []
        try:
            return self.client.search_linkable(self.scope, query, limit=RECORD_LIMIT)
        except CLIENT_ERRORS:
            return []

    def _refresh(self) -> None:
        query = self.query_one("#palette-input", Input).value
        self.rows = build_rows(query, self.commands, self._records(query), self.mode)
        option_list = self.query_one("#palette-list", OptionList)
        width = max(option_list.size.width, 40)
        option_list.clear_options()
        option_list.add_options(
            [
                Option(
                    Text(row_line(row, False, width)),
                    id=str(index),
                    disabled=row.kind == "header",
                )
                for index, row in enumerate(self.rows)
            ]
        )
        option_list.highlighted = next(
            (index for index, row in enumerate(self.rows) if row.kind != "header"), None
        )
        self.query_one("#palette-foot", Static).update(f"Showing: {self.mode}")

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self._choose(self.query_one("#palette-list", OptionList).highlighted)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self._choose(event.option_index)

    def _choose(self, index: int | None) -> None:
        if index is None or not 0 <= index < len(self.rows):
            return
        choice = self.rows[index].choice
        if choice is not None:
            self.dismiss(choice)

    def action_move(self, delta: int) -> None:
        option_list = self.query_one("#palette-list", OptionList)
        if delta > 0:
            option_list.action_cursor_down()
        else:
            option_list.action_cursor_up()

    def action_next_mode(self) -> None:
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
        self._refresh()

    def action_cancel(self) -> None:
        self.dismiss(None)
