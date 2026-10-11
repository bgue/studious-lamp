"""Forms of the accounts screen: add an account, reset a password, issue a token (P1-I0-T09b).

Each is a modal over :class:`tl_tui.widgets.admin_screen.AdminScreen` that makes one client call.
The service decides what is allowed (a weak password, a taken name, a disabled agent): its
refusal is shown under the fields and the form stays open. A password is read from a masked
input, passed to that one call and cleared from the input after every attempt, success or not; it
is never stored, shown or put in a message. An issued token is shown once, by :class:`TokenShown`.

STUB (P1-I0-T09b): the bodies marked STEPS raise NotImplementedError; the layout (`compose`,
`DEFAULT_CSS`, `BINDINGS`), `TokenShown` and every signature are final (the provided snapshots pin
the layout). Implement the bodies, then delete this paragraph and the STEPS comments.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

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
        # STEPS: the kind the "#form-kind" RadioSet shows pressed: KINDS[index] for
        # `pressed_index` in range, else "person".
        raise NotImplementedError

    def action_apply(self) -> None:
        # STEPS
        # 1. username = "#form-username" value stripped; display = "#form-display" stripped;
        #    kind = self._kind(); password and repeat = the "#form-password" and "#form-repeat"
        #    values as typed (do not strip them).
        # 2. No username: self._error("Enter a username") and return.
        # 3. kind is not "agent" and password != repeat: self._error("The two passwords differ"),
        #    self._clear_passwords(), return. (An agent has no password: its fields are ignored.)
        # 4. roles = ["admin", "user"] when the "#form-admin" Checkbox is on, else ["user"].
        # 5. try: view = self.client.create_account(username, display or username, kind=kind,
        #    roles=roles, password=None if kind == "agent" else password)
        #    except CLIENT_ERRORS as exc: self._error(describe_error(exc)); self._clear_passwords();
        #    return (the form stays open; check no rule yourself: the service decides).
        # 6. self._clear_passwords(); self.dismiss(view).
        raise NotImplementedError


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
        # STEPS
        # 1. password and repeat = the "#form-password" and "#form-repeat" values as typed.
        # 2. Empty password: self._error("Enter the new password") and return.
        #    password != repeat: self._error("The two passwords differ"), self._clear_passwords(),
        #    return.
        # 3. try: view = self.client.reset_password(self.account.account_id, password)
        #    except CLIENT_ERRORS as exc: self._error(describe_error(exc)); self._clear_passwords();
        #    return.
        # 4. self._clear_passwords(); self.dismiss(view).
        raise NotImplementedError


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
        # STEPS
        # 1. label = the "#form-label" value stripped; no label: self._error("Enter a label"),
        #    return.
        # 2. days = None. Unless the "#form-never" Checkbox is on, days = int(the "#form-days" value
        #    stripped); a ValueError is self._error("Days must be a whole number") and return.
        # 3. try: _, token = self.client.issue_agent_token(self.account.account_id, label,
        #    expires_in_days=days)  except CLIENT_ERRORS as exc: self._error(describe_error(exc));
        #    return (the form stays open).
        # 4. self.dismiss((label, token)). The token goes nowhere else: not a message, not an
        #    attribute, not a log line.
        raise NotImplementedError


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
