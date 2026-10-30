"""The Add property form (P1-UX3 round 3): one short form, three ways to name a property.

Opened from the record screen's Properties tab and from the actions bar of a log (``+``). The first
step offers ``From the standard`` (the properties the record's type allows and the record has no
value for) and ``Custom field`` (a name and a value in a set's custom section) and, for an admin,
``Propose a change to the standard…`` (the schema workbench on the package that owns the set). A
picked standard property asks for its value in the field that fits its type (text, number with its
unit, date, code list choice).

The form sends nothing. It returns an ``AddOutcome``: the ``SetPsetValues`` command to send, or the
package whose change to propose. The host sends the command inside its own error handling, so a
refusal reaches its status line. ``load_add_property`` does the reads (they may raise
``CLIENT_ERRORS``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Select, Static
from textual.widgets.option_list import Option
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.psets import SetPsetValues
from tl_schema.forms import FormMetadata

from tl_tui.add_property import (
    CUSTOM_HELP,
    NO_CUSTOM_SECTION,
    CustomTarget,
    Offer,
    custom_key,
    custom_targets,
    offer_command,
    owners,
    set_values_command,
    standard_offers,
)
from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS
from tl_tui.widgets.form_fields import FieldEditor

COMPANY = "company"
STEP_CHOOSE, STEP_STANDARD, STEP_VALUE, STEP_CUSTOM, STEP_PROPOSE = (
    "choose",
    "standard",
    "value",
    "custom",
    "propose",
)
PROPOSE_LINE = "Propose a change to the standard…"


@dataclass(frozen=True)
class AddData:
    """What the form needs, read once when it opens."""

    record: dict[str, Any]
    meta: FormMetadata
    company: FormMetadata | None  # the company's form for the type; None when it cannot be read


@dataclass(frozen=True)
class AddOutcome:
    """What the form hands back: a command to send, or a package to open the workbench on."""

    command: SetPsetValues | None = None
    package: str | None = None


def load_add_property(client: ClientInterface, scope: str, record_id: str) -> AddData:
    """Read the record and the forms of its type: the project's and the company's. Raises
    ``CLIENT_ERRORS`` (a missing or hidden record is ``RecordNotFoundError``)."""
    record = client.get_record_by_id(record_id)
    if record is None:
        raise RecordNotFoundError(f"no record {record_id!r}")
    where = str(record.get("scope") or scope)
    meta = client.form_metadata(where, str(record["type"]), record_id)
    company: FormMetadata | None = None
    if where != COMPANY:
        try:
            company = client.form_metadata(COMPANY, str(record["type"]))
        except (NotImplementedError, *CLIENT_ERRORS):
            company = None  # only the sets the project shows are offered
    return AddData(record, meta, company)


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

    def __init__(self, data: AddData, *, actor: str, scope: str, is_admin: bool = False) -> None:
        super().__init__()
        self.data = data
        self.actor = actor
        self.scope = str(data.record.get("scope") or scope)
        self.is_admin = is_admin
        self.offers: list[Offer] = standard_offers(data.meta, data.company, data.record)
        self.targets: list[CustomTarget] = custom_targets(data.meta, data.record)
        self.owners: list[tuple[str, str]] = owners(data.meta, data.company)
        self.step = STEP_CHOOSE
        self.offer: Offer | None = None
        self.editor: FieldEditor | None = None

    # --- layout ---------------------------------------------------------------------------

    def choose_options(self) -> list[Option]:
        count = len(self.offers)
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
                    *[Option(o.line, id=str(i)) for i, o in enumerate(self.offers)], id="ap-offers"
                )
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

    # --- steps ----------------------------------------------------------------------------

    def _show(self, step: str) -> None:
        self.step = step
        for name in (STEP_CHOOSE, STEP_STANDARD, STEP_VALUE, STEP_CUSTOM, STEP_PROPOSE):
            self.query_one(f"#ap-{name}").display = name == step
        self.query_one("#ap-status", Static).update("")
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

    def _pick_offer(self, offer: Offer) -> None:
        self.offer = offer
        self.query_one("#ap-value-head", Static).update(offer.line.split("  (")[0])
        self.query_one("#ap-value-note", Static).update(
            ""
            if offer.adopted
            else "This set is not adopted by this project yet; the service may refuse the value."
        )
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
        elif self.step == STEP_VALUE:
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

    def _save_standard(self) -> None:
        offer, editor = self.offer, self.editor
        if offer is None or editor is None:
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
        if not self.targets:
            return
        chosen = self.query(Select)
        target = self.targets[int(chosen.first().value)] if chosen else self.targets[0]  # type: ignore[arg-type]
        name = self.query_one("#ap-cname", Input).value
        value = self.query_one("#ap-cvalue", Input).value.strip()
        key = custom_key(name)
        if not key or not value:
            self._status("Enter a name and a value.")
            return
        self.dismiss(
            AddOutcome(
                command=set_values_command(
                    self.data.record,
                    pset=target.pset,
                    layer="custom",
                    key=f"x.{key}",
                    value=value,
                    actor=self.actor,
                    scope=self.scope,
                )
            )
        )


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
) -> None:
    """Read what the form needs, show it, and hand its outcome to ``send`` (a command) or
    ``workbench`` (a package). The reads may raise ``CLIENT_ERRORS``; the caller shows them."""
    data = load_add_property(client, scope, record_id)

    def done(outcome: AddOutcome | None) -> None:
        if outcome is None:
            return
        if outcome.command is not None:
            send(outcome.command)
        elif outcome.package is not None:
            workbench(outcome.package)

    host.app.push_screen(AddPropertyScreen(data, actor=actor, scope=scope, is_admin=is_admin), done)
