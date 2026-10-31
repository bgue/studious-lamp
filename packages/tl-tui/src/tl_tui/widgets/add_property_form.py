"""The Add property form (P1-UX3 rounds 3 and 4): one short form, three ways to name a property.

Opened from the record screen's Properties tab and from the actions bar of a log (``+``). It reads
``ClientInterface.addable_properties``, the read the API and the MCP tool offer too. The first step
offers ``From the standard`` (the properties the record's type allows and the record has no value
for, including those of an optional set the project has not adopted), ``Custom field`` (a name and
a value in a set's custom section) and, for an admin, ``Propose a change to the standard…`` (the
schema workbench on the package that owns the set). A picked standard property asks for its value in
the field that fits its type. Picking one of a set the project has not adopted offers ``Adopt <set>
for <project>`` to a person who may (``can_adopt``); for anybody else the line is greyed with the
words the read gives.

The form sends nothing. It returns an ``AddOutcome``: the ``SetPsetValues`` command to send, the set
to adopt (the form opens again on the same property afterwards), or the package whose change to
propose. The host sends them inside its own error handling, so a refusal reaches its status line.
``load_add_property`` does the read (it may raise ``CLIENT_ERRORS``).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Select, Static
from textual.widgets.option_list import Option
from tl_core.addable import AddableProperties
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.psets import SetPsetValues
from tl_mod_schemareg.handlers.adoption import AdoptSchemaSet

from tl_tui.add_property import (
    CUSTOM_HELP,
    NO_CUSTOM_SECTION,
    CustomTarget,
    Offer,
    adopt_command,
    adopt_label,
    custom_key,
    custom_problem,
    custom_targets,
    offer_command,
    owners,
    set_values_command,
    standard_offers,
)
from tl_tui.client import ClientInterface
from tl_tui.widgets.form_fields import FieldEditor

STEP_CHOOSE, STEP_STANDARD, STEP_VALUE, STEP_CUSTOM, STEP_PROPOSE, STEP_ADOPT = (
    "choose",
    "standard",
    "value",
    "custom",
    "propose",
    "adopt",
)
PROPOSE_LINE = "Propose a change to the standard…"


@dataclass(frozen=True)
class AddData:
    """What the form needs, read once when it opens."""

    record: dict[str, Any]
    addable: AddableProperties


@dataclass(frozen=True)
class AddOutcome:
    """What the form hands back: a command to send, a set to adopt (and the property to offer
    again afterwards), or a package to open the workbench on."""

    command: SetPsetValues | None = None
    package: str | None = None
    adopt: AdoptSchemaSet | None = None
    then: tuple[str, str] | None = None  # (set, property) to open on once the set is adopted


def load_add_property(client: ClientInterface, record_id: str) -> AddData:
    """Read the record and what can be added to it. Raises ``CLIENT_ERRORS`` (a missing or hidden
    record is ``RecordNotFoundError``)."""
    record = client.get_record_by_id(record_id)
    if record is None:
        raise RecordNotFoundError(f"no record {record_id!r}")
    return AddData(record, client.addable_properties(record_id))


class AddPropertyScreen(ModalScreen[AddOutcome | None]):
    """Add a property to one record. Esc steps back; on the first step it closes."""

    KEY_HINTS: ClassVar[str] = "Up/Down choose  Enter pick  Ctrl+S save  Esc back"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "back", "Back", show=False),
        Binding("ctrl+s", "save", "Save", show=False),
    ]

    DEFAULT_CSS = """
    AddPropertyScreen { align: center middle; }
    AddPropertyScreen > Vertical { width: 80%; height: 80%; border: round $accent;
        background: $surface; padding: 0 1; }
    AddPropertyScreen .ap-step { height: 1fr; }
    AddPropertyScreen OptionList { height: 1fr; min-height: 3; }
    AddPropertyScreen #ap-title { text-style: bold; }
    AddPropertyScreen #ap-status { height: auto; color: $error; }
    AddPropertyScreen .ap-help { color: $text-muted; height: auto; margin: 1 0; }
    AddPropertyScreen .ap-label { margin-top: 1; }
    """

    def __init__(
        self,
        data: AddData,
        *,
        actor: str,
        scope: str,
        is_admin: bool = False,
        preselect: tuple[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.data = data
        self.actor = actor
        self.scope = str(data.record.get("scope") or scope)
        self.is_admin = is_admin
        self.preselect = preselect
        self.offers: list[Offer] = standard_offers(data.addable, data.record)
        self.targets: list[CustomTarget] = custom_targets(data.addable)
        self.owners: list[tuple[str, str]] = owners(data.addable)
        self.step = STEP_CHOOSE
        self.offer: Offer | None = None
        self.editor: FieldEditor | None = None

    # --- layout ---------------------------------------------------------------------------

    def choose_options(self) -> list[Option]:
        count = len([o for o in self.offers if o.blocked is None])
        standard = (
            f"From the standard  ({count} available)" if count else "From the standard  (none left)"
        )
        options = [Option(standard, id=STEP_STANDARD), Option("Custom field", id=STEP_CUSTOM)]
        if self.is_admin:
            options.append(Option(PROPOSE_LINE, id=STEP_PROPOSE))
        return options

    def compose(self) -> ComposeResult:
        key = self.data.record.get("key") or ""
        with Vertical():
            yield Static(f"Add a property to {key}", id="ap-title", markup=False)
            with Vertical(id="ap-choose", classes="ap-step"):
                yield Static("Pick where the property comes from.", classes="ap-help", markup=False)
                yield OptionList(*self.choose_options(), id="ap-choose-list")
            with Vertical(id="ap-standard", classes="ap-step"):
                yield Static(
                    "Properties the standard allows for this record and it has no value for.",
                    classes="ap-help",
                    markup=False,
                )
                yield OptionList(
                    *[
                        Option(
                            Text(o.line, style="dim") if o.blocked else o.line,
                            id=str(i),
                            disabled=o.blocked is not None,
                        )
                        for i, o in enumerate(self.offers)
                    ],
                    id="ap-offers",
                )
            with Vertical(id="ap-adopt", classes="ap-step"):
                yield Static("", id="ap-adopt-head", classes="ap-help", markup=False)
                yield OptionList(id="ap-adopt-list")
            with VerticalScroll(id="ap-value", classes="ap-step"):
                yield Static("", id="ap-value-head", markup=False)
                yield Vertical(id="ap-value-body")
                yield Static("", id="ap-value-note", classes="ap-help", markup=False)
            with VerticalScroll(id="ap-custom", classes="ap-step"):
                yield from self._custom_widgets()
            with Vertical(id="ap-propose", classes="ap-step"):
                yield Static(
                    "Which standard should change? The schema workbench opens on it, and the "
                    "change goes through draft and review.",
                    classes="ap-help",
                    markup=False,
                )
                yield OptionList(
                    *[
                        Option(f"{label}  ·  {package}", id=package)
                        for package, label in self.owners
                    ],
                    id="ap-owners",
                )
            yield Static("", id="ap-status", markup=False)

    def _custom_widgets(self) -> ComposeResult:
        if not self.targets:
            yield Static(NO_CUSTOM_SECTION, classes="ap-help", markup=False)
            return
        yield Static(CUSTOM_HELP, classes="ap-help", markup=False)
        if len(self.targets) > 1:
            yield Static("In which set", classes="ap-label", markup=False)
            yield Select[int](
                [(t.line, i) for i, t in enumerate(self.targets)], allow_blank=False, id="ap-cset"
            )
        else:
            yield Static(f"In {self.targets[0].line}", classes="ap-label", markup=False)
        yield Static("Name", classes="ap-label", markup=False)
        yield Input(placeholder="for example: fat witness by", id="ap-cname")
        yield Static("Value", classes="ap-label", markup=False)
        yield Input(id="ap-cvalue")

    def on_mount(self) -> None:
        self._show(STEP_CHOOSE)
        if self.preselect is not None:
            for offer in self.offers:
                if (offer.pset, offer.prop.property) == self.preselect and offer.adopted:
                    self._pick_offer(offer)
                    break

    # --- steps ----------------------------------------------------------------------------

    def _show(self, step: str) -> None:
        self.step = step
        for name in (STEP_CHOOSE, STEP_STANDARD, STEP_VALUE, STEP_CUSTOM, STEP_PROPOSE, STEP_ADOPT):
            self.query_one(f"#ap-{name}").display = name == step
        refusal = self.data.addable.write_refusal
        shown = f"This record takes no new property now: {refusal}." if refusal else ""
        self.query_one("#ap-status", Static).update(shown if step == STEP_CHOOSE else "")
        self.call_after_refresh(self._focus_step)

    def _focus_step(self) -> None:
        if self.step == STEP_VALUE and self.editor is not None:
            control = getattr(self.editor, "_control", None)  # built when the editor is composed
            if control is None:
                self.set_timer(0.05, self._focus_step)
            else:
                control.focus()
        elif self.step == STEP_CUSTOM:
            for found in self.query("#ap-cname"):
                found.focus()
                return
        else:
            for found in self.query(f"#ap-{self.step} OptionList"):
                found.focus()
                return

    def _status(self, text: str) -> None:
        self.query_one("#ap-status", Static).update(text)

    def _pick_adopt(self, offer: Offer) -> None:
        """The set is not the project's yet: offer to adopt it (the person may; the line is greyed
        for anybody else, so this is not reached)."""
        sheet = offer.adopt
        if sheet is None:
            return
        self.offer = offer
        self.query_one("#ap-adopt-head", Static).update(
            f"{sheet.set_label} is an optional set of the company standard and {sheet.project} "
            f"has not adopted it yet. Adopting makes it part of {sheet.project}'s schema, from "
            f"{sheet.package} {sheet.version}; then the value can be entered."
        )
        options = self.query_one("#ap-adopt-list", OptionList)
        options.clear_options()
        options.add_option(Option(adopt_label(sheet), id=STEP_ADOPT))
        self._show(STEP_ADOPT)

    def _pick_offer(self, offer: Offer) -> None:
        if offer.blocked is not None:
            self._status(offer.blocked)
            return
        if offer.adopt is not None:
            self._pick_adopt(offer)
            return
        self.offer = offer
        self.query_one("#ap-value-head", Static).update(offer.line)
        self.query_one("#ap-value-note", Static).update("")
        body = self.query_one("#ap-value-body", Vertical)
        self.editor = FieldEditor(offer.field, None, id="ap-editor")
        body.remove_children()
        body.mount(self.editor)
        self._show(STEP_VALUE)

    # --- events ---------------------------------------------------------------------------

    def _choose(self, picked: str) -> None:
        """A line of the first step: a list to pick from, or (one package) the workbench."""
        if picked == STEP_PROPOSE and len(self.owners) == 1:
            self.dismiss(AddOutcome(package=self.owners[0][0]))
        elif picked == STEP_PROPOSE and not self.owners:
            self._status("No property set of this record names a package to change.")
        else:
            self._show(picked)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        picked = event.option.id or ""
        if self.step == STEP_CHOOSE:
            self._choose(picked)
        elif self.step == STEP_STANDARD:
            self._pick_offer(self.offers[int(picked)])
        elif self.step == STEP_PROPOSE:
            self.dismiss(AddOutcome(package=picked))
        elif self.step == STEP_ADOPT and self.offer is not None and self.offer.adopt is not None:
            self.dismiss(
                AddOutcome(
                    adopt=adopt_command(self.offer.adopt, actor=self.actor),
                    then=(self.offer.pset, self.offer.prop.property),
                )
            )

    def on_key(self, event: events.Key) -> None:
        """1, 2 and 3 pick a line of the first step."""
        if self.step != STEP_CHOOSE or event.key not in ("1", "2", "3"):
            return
        options = self.choose_options()
        if int(event.key) <= len(options):
            event.stop()
            self._choose(options[int(event.key) - 1].id or "")

    def action_back(self) -> None:
        if self.step == STEP_CHOOSE:
            self.dismiss(None)
        elif self.step == STEP_VALUE or self.step == STEP_ADOPT:
            self._show(STEP_STANDARD)
        else:
            self._show(STEP_CHOOSE)

    def action_save(self) -> None:
        if self.step == STEP_VALUE:
            self._save_standard()
        elif self.step == STEP_CUSTOM:
            self._save_custom()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.action_save()

    def _refused(self) -> bool:
        refusal = self.data.addable.write_refusal
        if refusal:
            self._status(f"This record takes no new property now: {refusal}.")
        return bool(refusal)

    def _save_standard(self) -> None:
        offer, editor = self.offer, self.editor
        if offer is None or editor is None or self._refused():
            return
        if not editor.validate():
            self._status("Fix the value first.")
            return
        value = editor.value
        if value is None:
            self._status("Enter a value.")
            return
        self.dismiss(
            AddOutcome(
                command=offer_command(
                    self.data.record, offer, value, actor=self.actor, scope=self.scope
                )
            )
        )

    def _save_custom(self) -> None:
        if not self.targets or self._refused():
            return
        chosen = self.query(Select)
        target = self.targets[int(chosen.first().value)] if chosen else self.targets[0]  # type: ignore[arg-type]
        name = self.query_one("#ap-cname", Input).value
        value = self.query_one("#ap-cvalue", Input).value.strip()
        problem = custom_problem(name, target)
        if problem is not None:
            self._status(problem)
            return
        if not value:
            self._status("Enter a value.")
            return
        self.dismiss(
            AddOutcome(
                command=set_values_command(
                    self.data.record,
                    pset=target.pset,
                    layer="custom",
                    key=f"x.{custom_key(name)}",
                    value=_typed(value),
                    actor=self.actor,
                    scope=self.scope,
                )
            )
        )


def _typed(text: str) -> Any:
    """A number typed in the value box is kept as a number when it reads back exactly the same
    (``14``, ``2.5``); anything else (``007``, a date, ``nan``) stays text. The service refuses
    what it cannot keep."""
    try:
        whole = int(text)
    except ValueError:
        pass
    else:
        return whole if str(whole) == text else text
    try:
        number = float(text)
    except ValueError:
        return text
    return number if math.isfinite(number) and repr(number) == text else text


def open_add_property(
    host: Any,
    client: ClientInterface,
    *,
    scope: str,
    record_id: str,
    actor: str,
    is_admin: bool,
    send: Callable[[SetPsetValues], None],
    workbench: Callable[[str], None],
    adopt: Callable[[AdoptSchemaSet], bool],
    preselect: tuple[str, str] | None = None,
) -> None:
    """Read what the form needs, show it, and hand its outcome to ``send`` (a command), ``adopt``
    (a set to adopt; it answers whether it worked, and then the form opens again on the same
    property) or ``workbench`` (a package). The read may raise ``CLIENT_ERRORS``; the caller shows
    them."""
    data = load_add_property(client, record_id)

    def done(outcome: AddOutcome | None) -> None:
        if outcome is None:
            return
        if outcome.command is not None:
            send(outcome.command)
        elif outcome.package is not None:
            workbench(outcome.package)
        elif outcome.adopt is not None and adopt(outcome.adopt):
            open_add_property(
                host,
                client,
                scope=scope,
                record_id=record_id,
                actor=actor,
                is_admin=is_admin,
                send=send,
                workbench=workbench,
                adopt=adopt,
                preselect=outcome.then,
            )

    host.app.push_screen(
        AddPropertyScreen(data, actor=actor, scope=scope, is_admin=is_admin, preselect=preselect),
        done,
    )
