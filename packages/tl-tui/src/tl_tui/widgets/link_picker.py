"""Link picker modal: search, choose a relation and a pin, link the sources to the targets.

(P0-I3-T12; brief 7.2, sketch 4.) Opened with `l` on a selection or on the open record. The user
searches records (key or title), ticks one or more with Ctrl+T, chooses the relation (pre-selected
from the record types) and an optional pin and note, and presses Enter. Ctrl+N creates a new record
and links it in place. The picker issues `ClientInterface.add_link` itself and dismisses with a
`LinkPickerResult`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel
from rich.cells import cell_len, set_cell_size
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Select, Static
from textual.widgets.option_list import Option
from textual.widgets.select import InvalidSelectValueError
from tl_core.services.link_queries import LinkTarget
from tl_core.services.links import AddLink

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.text import EMPTY

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
    if len(sources) == 1:
        return f"Link {sources[0].key} →"
    return f"Link {len(sources)} selected records →"


def result_line(target: LinkTarget, selected: bool, highlighted: bool, width: int) -> str:
    """One result row of exactly ``width`` cells: ``▶ [x] KEY  Title`` and the status on the right.

    ``▶`` marks the highlighted row (a space otherwise); ``[x]`` a ticked one (``[ ]`` otherwise).
    The left part is cut with ``…`` to leave room for the status and one space; a missing key or
    status shows as ``—``.
    """
    mark = f"{'▶' if highlighted else ' '} [{'x' if selected else ' '}]"
    left = f"{mark} {target.key or EMPTY}  {target.title}"
    right = target.status or EMPTY
    room = width - cell_len(right) - 1
    if cell_len(left) > room:
        left = set_cell_size(left, room - 1) + "…" if room > 0 else ""
    spaces = " " * max(0, width - cell_len(left) - cell_len(right))
    return set_cell_size(left + spaces + right, width)


def preview_text(target: LinkTarget | None) -> str:
    """``KEY · Title · Status · N linked`` for the highlighted record, or a hint when none."""
    if target is None:
        return "No record highlighted"
    key = target.key or EMPTY
    status = target.status or EMPTY
    return f"{key} · {target.title} · {status} · {target.link_total} linked"


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
    return [
        AddLink(
            actor=actor,
            source="tui",
            scope=scope,
            from_id=source.id,
            to_id=target.id,
            relation=relation,
            pin=pin,
            note=note,
            link_source="manual",
        )
        for source in sources
        for target in targets
        if source.id != target.id
    ]


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
        self.query_one("#picker-search", Input).focus()
        self._search()

    # --- searching and selecting ---------------------------------------------------------------

    def _search(self) -> None:
        query = self.query_one("#picker-search", Input).value
        try:
            rows = self.client.search_linkable(self.scope, query, limit=RESULT_LIMIT)
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc))
            rows = []
        source_ids = {source.id for source in self.sources}
        self.found = [target for target in rows if target.id not in source_ids]
        self._draw()

    def _draw(self, keep: int = 0) -> None:
        results = self.query_one("#picker-results", OptionList)
        width = max(results.size.width, 60)
        highlighted = results.highlighted if results.highlighted is not None else keep
        rows = [
            Option(
                Text(result_line(t, t.id in self.selected, i == highlighted, width)),
                id=t.id,
            )
            for i, t in enumerate(self.found)
        ]
        results.clear_options()
        results.add_options(rows)
        if self.found:
            results.highlighted = min(highlighted, len(self.found) - 1)
        self._on_highlight()

    def _highlighted(self) -> LinkTarget | None:
        index = self.query_one("#picker-results", OptionList).highlighted
        if index is None or not 0 <= index < len(self.found):
            return None
        return self.found[index]

    def _on_highlight(self) -> None:
        target = self._highlighted()
        self.query_one("#picker-preview", Static).update(preview_text(target))
        if target is not None and not self._manual_relation:
            self._set_relation(self._default_relation(target))

    def _set_relation(self, code: str) -> None:
        select: Select[str] = self.query_one("#picker-relation", Select)
        if select.value != code:
            self._setting_relation = True
            try:
                select.value = code
            except InvalidSelectValueError:
                pass  # a code missing from the options keeps the old value
            finally:
                self._setting_relation = False

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "picker-search":
            event.stop()
            self._search()

    def on_select_changed(self, event: Select.Changed) -> None:
        event.stop()
        if not self._setting_relation:
            self._manual_relation = True

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        event.stop()
        self._on_highlight()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.action_toggle_select()

    def action_move(self, delta: int) -> None:
        results = self.query_one("#picker-results", OptionList)
        if delta > 0:
            results.action_cursor_down()
        elif delta < 0:
            results.action_cursor_up()
        self._draw(results.highlighted or 0)

    def action_toggle_select(self) -> None:
        target = self._highlighted()
        if target is not None:
            if target.id in self.selected:
                del self.selected[target.id]
            else:
                self.selected[target.id] = target
        results = self.query_one("#picker-results", OptionList)
        self._draw(results.highlighted or 0)

    # --- linking -------------------------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        targets = list(self.selected.values())
        if not targets:
            highlighted = self._highlighted()
            targets = [] if highlighted is None else [highlighted]
        self._link(targets)

    def _say(self, text: str) -> None:
        self.query_one("#picker-status", Static).update(text)

    def _link(self, targets: Sequence[LinkTarget]) -> None:
        if not targets:
            self._say("Choose a record to link")
            return
        relation = str(self.query_one("#picker-relation", Select).value)
        pin = self.query_one("#picker-pin", Input).value.strip() or None
        note = self.query_one("#picker-note", Input).value.strip() or None
        commands = build_commands(
            self.sources,
            targets,
            relation=relation,
            pin=pin,
            note=note,
            scope=self.scope,
            actor=self.actor,
        )
        keys = {source.id: source.key for source in self.sources}
        keys.update({target.id: target.key or target.id for target in targets})
        created = 0
        messages: list[str] = []
        for cmd in commands:
            try:
                self.client.add_link(cmd)
            except CLIENT_ERRORS as exc:
                messages.append(f"{keys[cmd.from_id]} → {keys[cmd.to_id]}: {describe_error(exc)}")
            else:
                created += 1
        if created == 0:
            self._say("; ".join(messages) or "Nothing to link")
            return
        self.dismiss(LinkPickerResult(created=created, messages=messages))

    def action_create_and_link(self) -> None:
        from tl_tui.widgets.new_record_form import NewRecordForm

        def linked_new_record(key: str | None) -> None:
            if key is None:
                return
            record = self.client.get_record(self.scope, key)
            if record is None:
                self._say(f"Created {key} but could not read it back")
                return
            target = LinkTarget(
                id=str(record["id"]),
                key=record.get("key"),
                type=str(record["type"]),
                title=str(record["title"]),
                status=record.get("status"),
                scope=str(record["scope"]),
                link_total=0,
            )
            self._link([target])

        self.app.push_screen(
            NewRecordForm(self.client, self.scope, actor=self.actor), linked_new_record
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
