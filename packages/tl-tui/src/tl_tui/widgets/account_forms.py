"""Forms of the accounts screen: add an account, reset a password, issue a token (P1-I0-T09b).

Each is a modal over :class:`tl_tui.widgets.admin_screen.AdminScreen` that makes one client call.
The service decides what is allowed (a weak password, a taken name, a disabled agent): its
refusal is shown under the fields and the form stays open. A password is read from a masked
input, passed to that one call and cleared from the input after every attempt, success or not; it
is never stored, shown or put in a message. An issued token is shown once, by :class:`TokenShown`.
"""

from __future__ import annotations

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, RadioButton, RadioSet, Static
from tl_core.auth.types import AccountKind, AccountView

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error

KINDS: tuple[AccountKind, ...] = ("person", "sim", "agent")
DEFAULT_DAYS = "90"

_FORM_CSS = """
NAME { align: center middle; }
NAME > Vertical {
    width: 70; max-width: 100%; height: auto; max-height: 95%;
    border: round $accent; background: $surface; padding: 1 2;
}
NAME .form-title { text-style: bold; }
NAME .form-label { margin-top: 1; }
NAME .form-error { height: auto; color: $error; margin-top: 1; }
NAME Horizontal { height: auto; align-horizontal: right; margin-top: 1; }
NAME Button { margin-left: 1; }
"""


class _Form(ModalScreen[Any]):
    """What the three forms share: apply on Enter or Ctrl+S, cancel on Esc, one error line."""

    KEY_HINTS: ClassVar[str] = "Tab next field  Ctrl+S apply  Esc cancel"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+s", "apply", "Apply", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def action_apply(self) -> None:
        raise NotImplementedError

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "apply":
            self.action_apply()
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.action_apply()

    def _error(self, text: str) -> None:
        self.query_one(".form-error", Static).update(text)

    def _clear_passwords(self) -> None:
        for box in self.query(".form-password"):
            if isinstance(box, Input):
                box.value = ""


class AccountForm(_Form):
    """Add an account. Dismisses with the new :class:`AccountView`, or ``None`` when cancelled."""

    DEFAULT_CSS = _FORM_CSS.replace("NAME", "AccountForm")

    def __init__(self, client: ClientInterface) -> None:
        super().__init__()
        self.client = client

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Add an account", classes="form-title", markup=False)
            yield Static("Username", classes="form-label", markup=False)
            yield Input(id="form-username")
            yield Static("Display name (optional)", classes="form-label", markup=False)
            yield Input(id="form-display")
            yield Static("Kind", classes="form-label", markup=False)
            with RadioSet(id="form-kind"):
                yield RadioButton("person", value=True)
                yield RadioButton("sim")
                yield RadioButton("agent (gets tokens, no password)")
            yield Checkbox("Admin role (people only)", id="form-admin")
            yield Static("Password", classes="form-label", markup=False)
            yield Input(password=True, id="form-password", classes="form-password")
            yield Static("Repeat the password", classes="form-label", markup=False)
            yield Input(password=True, id="form-repeat", classes="form-password")
            yield Static("", classes="form-error", markup=False)
            with Horizontal():
                yield Button("Add", id="apply", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#form-username", Input).focus()

    def _kind(self) -> AccountKind:
        index = self.query_one("#form-kind", RadioSet).pressed_index
        if 0 <= index < len(KINDS):
            return KINDS[index]
        return "person"

    def action_apply(self) -> None:
        username = self.query_one("#form-username", Input).value.strip()
        display = self.query_one("#form-display", Input).value.strip()
        kind = self._kind()
        password = self.query_one("#form-password", Input).value
        repeat = self.query_one("#form-repeat", Input).value
        if not username:
            self._error("Enter a username")
            self._clear_passwords()
            return
        if kind != "agent" and password != repeat:
            self._error("The two passwords differ")
            self._clear_passwords()
            return
        admin = self.query_one("#form-admin", Checkbox).value
        roles = ["admin", "user"] if admin else ["user"]
        try:
            view = self.client.create_account(
                username,
                display or username,
                kind=kind,
                roles=roles,
                password=None if kind == "agent" else password,
            )
        except CLIENT_ERRORS as exc:
            self._error(describe_error(exc))
            self._clear_passwords()
            return
        self._clear_passwords()
        self.dismiss(view)


class PasswordForm(_Form):
    """Set a new password for ``account`` without the old one. Dismisses with the account."""

    DEFAULT_CSS = _FORM_CSS.replace("NAME", "PasswordForm")

    def __init__(self, client: ClientInterface, account: AccountView) -> None:
        super().__init__()
        self.client = client
        self.account = account

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(
                f"New password for {self.account.username}", classes="form-title", markup=False
            )
            yield Static("It ends their sessions and clears a lock.", markup=False)
            yield Static("New password", classes="form-label", markup=False)
            yield Input(password=True, id="form-password", classes="form-password")
            yield Static("Repeat the password", classes="form-label", markup=False)
            yield Input(password=True, id="form-repeat", classes="form-password")
            yield Static("", classes="form-error", markup=False)
            with Horizontal():
                yield Button("Reset", id="apply", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#form-password", Input).focus()

    def action_apply(self) -> None:
        password = self.query_one("#form-password", Input).value
        repeat = self.query_one("#form-repeat", Input).value
        if not password:
            self._error("Enter the new password")
            self._clear_passwords()
            return
        if password != repeat:
            self._error("The two passwords differ")
            self._clear_passwords()
            return
        try:
            view = self.client.reset_password(self.account.account_id, password)
        except CLIENT_ERRORS as exc:
            self._error(describe_error(exc))
            self._clear_passwords()
            return
        self._clear_passwords()
        self.dismiss(view)


class TokenForm(_Form):
    """Issue an agent token for ``account``. Dismisses with ``(label, token)`` or ``None``."""

    DEFAULT_CSS = _FORM_CSS.replace("NAME", "TokenForm")

    def __init__(self, client: ClientInterface, account: AccountView) -> None:
        super().__init__()
        self.client = client
        self.account = account

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(
                f"Issue a token for {self.account.username}", classes="form-title", markup=False
            )
            yield Static("Label (what it is for)", classes="form-label", markup=False)
            yield Input(id="form-label")
            yield Static("Days until it expires", classes="form-label", markup=False)
            yield Input(value=DEFAULT_DAYS, id="form-days")
            yield Checkbox("Never expires", id="form-never")
            yield Static("", classes="form-error", markup=False)
            with Horizontal():
                yield Button("Issue", id="apply", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#form-label", Input).focus()

    def action_apply(self) -> None:
        label = self.query_one("#form-label", Input).value.strip()
        if not label:
            self._error("Enter a label")
            return
        days: int | None = None
        if not self.query_one("#form-never", Checkbox).value:
            try:
                days = int(self.query_one("#form-days", Input).value.strip())
            except ValueError:
                self._error("Days must be a whole number")
                return
        try:
            _, token = self.client.issue_agent_token(
                self.account.account_id, label, expires_in_days=days
            )
        except CLIENT_ERRORS as exc:
            self._error(describe_error(exc))
            return
        self.dismiss((label, token))


class TokenShown(ModalScreen[None]):
    """Shows a new token once. It cannot be read back: close this and it is gone."""

    KEY_HINTS: ClassVar[str] = "Enter or Esc: I have copied it"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "close", "Close", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = _FORM_CSS.replace("NAME", "TokenShown")

    def __init__(self, label: str, token: str) -> None:
        super().__init__()
        self.label = label
        self.token = token

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Token {self.label}", classes="form-title", markup=False)
            yield Static("Copy it now. It is shown once and cannot be read back.", markup=False)
            yield Static(self.token, id="token-value", markup=False)
            yield Static(self.KEY_HINTS, classes="form-label", markup=False)

    def action_close(self) -> None:
        self.dismiss(None)
