"""Link picker modal: search, choose a relation and a pin, link the sources to the targets.

(P0-I3-T12; brief 7.2, sketch 4.) Opened with `l` on a selection or on the open record. The user
searches records (key or title), ticks one or more with Ctrl+T, chooses the relation (pre-selected
from the record types) and an optional pin and note, and presses Enter. Ctrl+N creates a new record
and links it in place. The picker issues `ClientInterface.add_link` itself and dismisses with a
`LinkPickerResult`.

STUB (P0-I3-T12): the types, layout (`compose`), constructor and key bindings are final; the
functions and methods marked `raise NotImplementedError` are the ticket. Remove this paragraph
when done.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Select, Static
from tl_core.services.link_queries import LinkTarget
from tl_core.services.links import AddLink

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS

RESULT_LIMIT = 20


@dataclass(frozen=True)
class PickerSource:
    """A record the links start from."""

    id: str
    key: str
    type: str
    title: str

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> PickerSource:
        return cls(
            id=str(record["id"]),
            key=str(record.get("key") or record["id"]),
            type=str(record.get("type") or ""),
            title=str(record.get("title") or ""),
        )


class LinkPickerResult(BaseModel):
    """What the picker did: links created, and one message per link that could not be created."""

    created: int
    messages: list[str] = []


def title_text(sources: Sequence[PickerSource]) -> str:
    """``Link FV-1001 →`` for one source, ``Link 3 selected records →`` for several."""
    raise NotImplementedError


def result_line(target: LinkTarget, selected: bool, highlighted: bool, width: int) -> str:
    """One result row of exactly ``width`` cells: ``▶ [x] KEY  Title`` and the status on the right.

    ``▶`` marks the highlighted row (a space otherwise); ``[x]`` a ticked one (``[ ]`` otherwise).
    The left part is cut with ``…`` to leave room for the status and one space; a missing key or
    status shows as ``—``.
    """
    raise NotImplementedError


def preview_text(target: LinkTarget | None) -> str:
    """``KEY · Title · Status · N linked`` for the highlighted record, or a hint when none."""
    raise NotImplementedError


def build_commands(
    sources: Sequence[PickerSource],
    targets: Sequence[LinkTarget],
    *,
    relation: str,
    pin: str | None,
    note: str | None,
    scope: str,
    actor: str,
) -> list[AddLink]:
    """One `AddLink` per (source, target) pair, sources outermost; never a record with itself.

    ``source`` of every command is ``tui`` and ``link_source`` is ``manual``.
    """
    raise NotImplementedError


class LinkPicker(ModalScreen[LinkPickerResult | None]):
    """Dismisses with a `LinkPickerResult` after linking, or ``None`` when cancelled."""

    KEY_HINTS: ClassVar[str] = "Ctrl+T select  Enter link  Ctrl+N create & link  Esc cancel"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("down", "move(1)", show=False),
        Binding("up", "move(-1)", show=False),
        Binding("ctrl+t", "toggle_select", show=False),
        Binding("ctrl+n", "create_and_link", show=False),
    ]

    DEFAULT_CSS = """
    LinkPicker { align: center middle; }
    LinkPicker > Vertical {
        width: 90%;
        max-width: 100;
        height: auto;
        max-height: 90%;
        border: round $accent;
        background: $surface;
        padding: 0 1;
    }
    LinkPicker #picker-title { text-style: bold; }
    LinkPicker #picker-options { height: 3; }
    LinkPicker #picker-relation { width: 34; }
    LinkPicker #picker-pin { width: 24; }
    LinkPicker #picker-results { height: auto; max-height: 10; border: none; }
    LinkPicker #picker-preview { color: $text-muted; }
    LinkPicker #picker-status { color: $error; height: auto; }
    """

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        sources: Sequence[PickerSource],
        *,
        actor: str = "user:dev",
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.sources = tuple(sources)
        self.actor = actor
        self.found: list[LinkTarget] = []
        self.selected: dict[str, LinkTarget] = {}
        self._manual_relation = False
        self._setting_relation = False

    # --- layout --------------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        relations = self._relation_options()
        with Vertical():
            yield Static(title_text(self.sources), id="picker-title", markup=False)
            with Horizontal(id="picker-options"):
                yield Select(
                    relations,
                    allow_blank=False,
                    value=self._default_relation(None),
                    id="picker-relation",
                )
                yield Input(placeholder="pin (blank: floating)", id="picker-pin")
            yield Input(placeholder="Search records by key or title", id="picker-search")
            yield OptionList(id="picker-results")
            yield Static("", id="picker-preview", markup=False)
            yield Input(placeholder="note (optional)", id="picker-note")
            yield Static("", id="picker-status", markup=False)

    def _relation_options(self) -> list[tuple[str, str]]:
        try:
            return [(f"{r.label}", r.code) for r in self.client.relations()]
        except CLIENT_ERRORS:
            return [("references", "references")]

    def _default_relation(self, target: LinkTarget | None) -> str:
        source_type = self.sources[0].type if self.sources else "core.Record"
        try:
            return self.client.default_relation(source_type, target.type if target else source_type)
        except CLIENT_ERRORS:
            return "references"

    def on_mount(self) -> None:
        raise NotImplementedError

    # --- searching and selecting ---------------------------------------------------------------

    def _search(self) -> None:
        raise NotImplementedError

    def _draw(self, keep: int = 0) -> None:
        raise NotImplementedError

    def _highlighted(self) -> LinkTarget | None:
        raise NotImplementedError

    def _on_highlight(self) -> None:
        raise NotImplementedError

    def _set_relation(self, code: str) -> None:
        raise NotImplementedError

    def on_input_changed(self, event: Input.Changed) -> None:
        raise NotImplementedError

    def on_select_changed(self, event: Select.Changed) -> None:
        raise NotImplementedError

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        raise NotImplementedError

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        raise NotImplementedError

    def action_move(self, delta: int) -> None:
        raise NotImplementedError

    def action_toggle_select(self) -> None:
        raise NotImplementedError

    # --- linking -------------------------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raise NotImplementedError

    def _say(self, text: str) -> None:
        raise NotImplementedError

    def _link(self, targets: Sequence[LinkTarget]) -> None:
        raise NotImplementedError

    def action_create_and_link(self) -> None:
        raise NotImplementedError

    def action_cancel(self) -> None:
        raise NotImplementedError
