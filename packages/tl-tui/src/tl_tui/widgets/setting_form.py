"""One change to a setting: set, reset, lock, unlock or revert, with its reason and its risk.

A modal over the settings list (P0-I8-S19; brief 30.3). It shows what is being changed and where,
asks for the value (set only), a reason, and for a dangerous key the "I accept the risk" box, then
makes the one client call. The service decides whether the change is allowed: a refusal (a locked
key, a value out of range, a missing reason, an unaccepted risk) is shown under the fields and the
form stays open. Dismisses with ``True`` after a change was made, ``False`` when cancelled.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Static
from tl_core.settings.values import format_value, parse_text
from tl_core.settings.views import SettingView

from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.settings_text import hint_for, layer_label

Action = Literal["set", "reset", "lock", "unlock", "revert"]

_VERBS: dict[str, str] = {
    "set": "Set",
    "reset": "Reset",
    "lock": "Lock for projects",
    "unlock": "Unlock for projects",
    "revert": "Undo the last change of",
}


class SettingForm(ModalScreen[bool]):
    """Dismisses with ``True`` once the change was made."""

    KEY_HINTS: ClassVar[str] = "Tab next field  Ctrl+S apply  Esc cancel"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+s", "apply", "Apply", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    SettingForm { align: center middle; }
    SettingForm > Vertical {
        width: 76; height: auto; max-height: 95%;
        border: round $accent; background: $surface; padding: 1 2;
    }
    SettingForm #form-title { text-style: bold; }
    SettingForm #form-error { height: auto; color: $error; }
    SettingForm .form-label { margin-top: 1; }
    SettingForm Horizontal { height: auto; align-horizontal: right; margin-top: 1; }
    SettingForm Button { margin-left: 1; }
    """

    def __init__(
        self,
        client: ClientInterface,
        view: SettingView,
        action: Action,
        target: str,
        *,
        seq: int | None = None,
    ) -> None:
        super().__init__()
        self.client = client
        self.view = view
        self.action = action
        self.target = target
        self.seq = seq

    @property
    def key(self) -> str:
        return self.view.definition.key

    def compose(self) -> ComposeResult:
        defn = self.view.definition
        where = "company" if self.action in ("lock", "unlock") else self.target
        if not mode_of(self.app).technical:
            where = layer_label(where)
        with Vertical():
            yield Static(f"{_VERBS[self.action]} {self.key}", markup=False, id="form-title")
            yield Static(f"at {where}", markup=False, id="form-layer")
            yield Static(defn.description, markup=False, id="form-description")
            if self.action == "set":
                yield Static(f"New value ({hint_for(defn)})", markup=False, classes="form-label")
                yield Input(value=format_value(self.view.effective.value), id="form-value")
            yield Static(self._reason_label(), markup=False, classes="form-label")
            yield Input(id="form-reason")
            if defn.risk == "dangerous" and self.action in ("set", "reset", "revert"):
                yield Checkbox("I accept the risk", id="form-risk")
            yield Static("", markup=False, id="form-error")
            with Horizontal():
                yield Button("Apply", id="apply", variant="primary")
                yield Button("Cancel", id="cancel")

    def _reason_label(self) -> str:
        risk = self.view.definition.risk
        if self.action in ("lock", "unlock") or risk != "normal":
            return "Reason (required)"
        return "Reason (optional)"

    def on_mount(self) -> None:
        first = "#form-value" if self.action == "set" else "#form-reason"
        self.query_one(first, Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "apply":
            self.action_apply()
        else:
            self.dismiss(False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.action_apply()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def _error(self, text: str) -> None:
        self.query_one("#form-error", Static).update(text)

    def action_apply(self) -> None:
        defn = self.view.definition
        reason = self.query_one("#form-reason", Input).value.strip() or None
        risk_boxes = self.query("#form-risk")
        accept = bool(risk_boxes.first(Checkbox).value) if risk_boxes else False
        try:
            if self.action == "set":
                value = parse_text(defn, self.query_one("#form-value", Input).value)
                self.client.set_setting(
                    self.key, layer=self.target, value=value, reason=reason, accept_risk=accept
                )
            elif self.action == "reset":
                self.client.reset_setting(
                    self.key, layer=self.target, reason=reason, accept_risk=accept
                )
            elif self.action in ("lock", "unlock"):
                self.client.lock_setting(
                    self.key, locked=self.action == "lock", reason=reason or "", bounds=None
                )
            else:
                assert self.seq is not None
                self.client.revert_setting(
                    self.key, layer=self.target, seq=self.seq, reason=reason, accept_risk=accept
                )
        except CLIENT_ERRORS as exc:
            self._error(describe_error(exc))
            return
        self.dismiss(True)
