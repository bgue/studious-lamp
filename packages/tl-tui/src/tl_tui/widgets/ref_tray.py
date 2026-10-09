"""Reference tray screen: tick collected records and link them to the open record in one action.

(P0-I3-T13b; brief 7.2, sketch 12.) `R` adds records to the app's `ReferenceTray`; `F4` opens
this screen. It lists the tray, lets the user tick or remove entries, and links the ticked ones to
the open record with the chosen relation and pin. It dismisses with the number of links created,
or ``None`` when closed without linking. Links are made with `ClientInterface.add_link`.
When some links are refused the screen stays open with those records still ticked and the
reasons shown; closing it then reports the links already made.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from rich.cells import cell_len, set_cell_size
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Select, Static
from textual.widgets.option_list import Option
from tl_core.services.links import AddLink

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.text import EMPTY
from tl_tui.tray import ReferenceTray, TrayItem


def tray_line(item: TrayItem, checked: bool, highlighted: bool, width: int) -> str:
    """One row of exactly ``width`` cells: ``▶ [x] KEY  Title`` and the record type on the right.

    ``▶`` marks the highlighted row (a space otherwise); ``[x]`` a ticked one (``[ ]`` otherwise).
    The left part is cut with ``…`` to leave room for the type and one space; an empty type
    shows as ``—``.
    """
    mark = f"{'▶' if highlighted else ' '} [{'x' if checked else ' '}]"
    left = f"{mark} {item.key}  {item.title}"
    right = item.type or EMPTY
    room = width - cell_len(right) - 1
    if cell_len(left) > room:
        left = set_cell_size(left, room - 1) + "…" if room > 0 else ""
    spaces = " " * max(0, width - cell_len(left) - cell_len(right))
    return set_cell_size(left + spaces + right, width)


def title_text(tray: ReferenceTray) -> str:
    """``Reference tray (4)`` with the number of records, ticked or not."""
    return f"Reference tray ({len(tray)})"


def target_text(target: dict[str, Any] | None, ticked: int) -> str:
    """The line that says where the ticked records will go.

    With a target: ``Link N ticked to <key> as:``; without one: ``Open a record to link the ticked
    ones to it``.
    """
    if target is None:
        return "Open a record to link the ticked ones to it"
    return f"Link {ticked} ticked to {target.get('key') or target['id']} as:"


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
    return [
        AddLink(
            actor=actor,
            source="tui",
            scope=scope,
            from_id=target_id,
            to_id=item.record_id,
            relation=relation,
            pin=pin,
            link_source="tray",
        )
        for item in items
        if item.record_id != target_id
    ]


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
        self._created = 0  # links made so far, including before a refusal kept the screen open

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
        self.query_one("#tray-list", OptionList).focus()
        self._draw()

    def _say(self, text: str) -> None:
        self.query_one("#tray-status", Static).update(text)

    def _draw(self, keep: int = 0) -> None:
        results = self.query_one("#tray-list", OptionList)
        width = max(results.size.width, 60)
        highlighted = results.highlighted if results.highlighted is not None else keep
        items = self.tray.items
        results.clear_options()
        results.add_options(
            [
                Option(
                    Text(
                        tray_line(
                            item,
                            self.tray.is_checked(item.record_id),
                            n == highlighted,
                            width,
                        )
                    ),
                    id=item.record_id,
                )
                for n, item in enumerate(items)
            ]
        )
        if items:
            results.highlighted = min(highlighted, len(items) - 1)
        self.query_one("#tray-title", Static).update(title_text(self.tray))
        self.query_one("#tray-target", Static).update(
            target_text(self.target, len(self.tray.checked_items()))
        )
        if not items:
            self._say("The tray is empty. Press R on a record to add it.")

    def _highlighted(self) -> TrayItem | None:
        index = self.query_one("#tray-list", OptionList).highlighted
        items = self.tray.items
        if index is None or not 0 <= index < len(items):
            return None
        return items[index]

    def action_move(self, delta: int) -> None:
        results = self.query_one("#tray-list", OptionList)
        if delta > 0:
            results.action_cursor_down()
        else:
            results.action_cursor_up()
        self._draw(results.highlighted or 0)

    def action_toggle_select(self) -> None:
        item = self._highlighted()
        if item is not None:
            self.tray.toggle(item.record_id)
        results = self.query_one("#tray-list", OptionList)
        self._draw(results.highlighted or 0)

    def action_remove(self) -> None:
        item = self._highlighted()
        if item is not None:
            self.tray.remove(item.record_id)
        results = self.query_one("#tray-list", OptionList)
        self._draw(results.highlighted or 0)

    def action_clear(self) -> None:
        self.tray.clear()
        self._draw()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self._link()

    def _link(self) -> None:
        if self.target is None:
            self._say("Open a record first: the ticked records link to it")
            return
        ticked = self.tray.checked_items()
        if not ticked:
            self._say("Tick at least one record")
            return
        select: Select[str] = self.query_one("#tray-relation", Select)
        pin = self.query_one("#tray-pin", Input).value.strip() or None
        commands = build_commands(
            ticked,
            str(self.target["id"]),
            relation=str(select.value),
            pin=pin,
            scope=self.scope,
            actor=self.actor,
        )
        keys = {item.record_id: item.key for item in ticked}
        messages: list[str] = []
        for cmd in commands:
            try:
                self.client.add_link(cmd)
            except CLIENT_ERRORS as exc:
                messages.append(f"{keys.get(cmd.to_id, cmd.to_id)}: {describe_error(exc)}")
            else:
                self._created += 1
                self.tray.remove(cmd.to_id)
        if not messages:
            self.dismiss(self._created)
            return
        # Some links were refused: stay open with the refused records still ticked and say why.
        self._draw()
        self._say("; ".join(messages))

    def action_close(self) -> None:
        self.dismiss(self._created or None)
