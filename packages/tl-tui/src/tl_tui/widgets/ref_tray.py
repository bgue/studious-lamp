"""Reference tray screen: tick collected records and link them to the open record in one action.

(P0-I3-T13b; brief 7.2, sketch 12.) `R` adds records to the app's `ReferenceTray`; `F4` opens
this screen. It lists the tray, lets the user tick or remove entries, and links the ticked ones to
the open record with the chosen relation and pin. It dismisses with the number of links created,
or ``None`` when closed without linking. Links are made with `ClientInterface.add_link`.

STUB (P0-I3-T13b): the layout (`compose`), constructor, key bindings, `title_text` and the relation helpers
are final; the functions and methods marked `raise NotImplementedError` are the ticket. Remove this
paragraph when done.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Select, Static
from tl_core.services.links import AddLink

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS
from tl_tui.tray import ReferenceTray, TrayItem


def tray_line(item: TrayItem, checked: bool, highlighted: bool, width: int) -> str:
    """One row of exactly ``width`` cells: ``▶ [x] KEY  Title`` and the record type on the right.

    ``▶`` marks the highlighted row (a space otherwise); ``[x]`` a ticked one (``[ ]`` otherwise).
    The left part is cut with ``…`` to leave room for the type and one space; an empty type
    shows as ``—``.
    """
    raise NotImplementedError


def title_text(tray: ReferenceTray) -> str:
    """``Reference tray (4)`` with the number of records, ticked or not."""
    return f"Reference tray ({len(tray)})"


def target_text(target: dict[str, Any] | None, ticked: int) -> str:
    """The line that says where the ticked records will go.

    With a target: ``Link N ticked to <key> as:``; without one: ``Open a record to link the ticked
    ones to it``.
    """
    raise NotImplementedError


def build_commands(
    items: Sequence[TrayItem],
    target_id: str,
    *,
    relation: str,
    pin: str | None,
    scope: str,
    actor: str,
) -> list[AddLink]:
    """One `AddLink` from the target to each item (never the target to itself), in the given order.

    ``source`` is ``tui`` and ``link_source`` is ``tray`` (how the link arose, brief 7.1).
    """
    raise NotImplementedError


class TrayList(OptionList):
    """The tray's list: Space ticks (the plain list would treat it like Enter)."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("space", "screen.toggle_select", show=False),
    ]


class ReferenceTrayScreen(ModalScreen[int | None]):
    """Dismisses with the number of links created, or ``None`` when closed without linking."""

    KEY_HINTS: ClassVar[str] = "Space tick  Del remove  Enter link ticked  c clear  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close"),
        Binding("down", "move(1)", show=False),
        Binding("up", "move(-1)", show=False),
        Binding("space", "toggle_select", show=False),
        Binding("delete", "remove", show=False),
        Binding("c", "clear", show=False),
    ]

    DEFAULT_CSS = """
    ReferenceTrayScreen { align: center middle; }
    ReferenceTrayScreen > Vertical {
        width: 80%;
        max-width: 90;
        height: auto;
        max-height: 90%;
        border: round $accent;
        background: $surface;
        padding: 0 1;
    }
    ReferenceTrayScreen #tray-title { text-style: bold; }
    ReferenceTrayScreen #tray-list { height: auto; max-height: 12; border: none; }
    ReferenceTrayScreen #tray-options { height: 3; }
    ReferenceTrayScreen #tray-relation { width: 34; }
    ReferenceTrayScreen #tray-pin { width: 24; }
    ReferenceTrayScreen #tray-status { color: $error; height: auto; }
    """

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        tray: ReferenceTray,
        target: dict[str, Any] | None,
        *,
        actor: str = "user:dev",
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.tray = tray
        self.target = target
        self.actor = actor

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(title_text(self.tray), id="tray-title", markup=False)
            yield TrayList(id="tray-list")
            yield Static("", id="tray-target", markup=False)
            with Horizontal(id="tray-options"):
                yield Select(
                    self._relation_options(),
                    allow_blank=False,
                    value=self._default_relation(),
                    id="tray-relation",
                )
                yield Input(placeholder="pin (blank: floating)", id="tray-pin")
            yield Static("", id="tray-status", markup=False)

    def _relation_options(self) -> list[tuple[str, str]]:
        try:
            return [(r.label, r.code) for r in self.client.relations()]
        except CLIENT_ERRORS:
            return [("references", "references")]

    def _default_relation(self) -> str:
        if self.target is None:
            return "references"
        first = self.tray.items[0].type if len(self.tray) else str(self.target.get("type") or "")
        try:
            return self.client.default_relation(str(self.target.get("type") or ""), first)
        except CLIENT_ERRORS:
            return "references"

    def on_mount(self) -> None:
        raise NotImplementedError

    def _say(self, text: str) -> None:
        raise NotImplementedError

    def _draw(self, keep: int = 0) -> None:
        raise NotImplementedError

    def _highlighted(self) -> TrayItem | None:
        raise NotImplementedError

    def action_move(self, delta: int) -> None:
        raise NotImplementedError

    def action_toggle_select(self) -> None:
        raise NotImplementedError

    def action_remove(self) -> None:
        raise NotImplementedError

    def action_clear(self) -> None:
        raise NotImplementedError

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        raise NotImplementedError

    def _link(self) -> None:
        raise NotImplementedError

    def action_close(self) -> None:
        raise NotImplementedError
