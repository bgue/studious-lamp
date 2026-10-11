# P1-I0-T09b — TUI forms: add an account, reset a password, issue and revoke a token

Status: ready
Tier: haiku
Labels: tui
Depends on: P1-I0-T09 (merged: `AdminScreen`, `admin_text`); P1-I0-S4 (the client calls and `FakeClient`); P1-I0-S18 (the keys, hint line and layout, on `p1/i0a`)
Branch: `p1/i0a-t09b-tui-account-forms`

## Goal
An admin finishes the accounts screen's work without leaving the TUI. `a` opens a form to add an account (username, display name, kind, admin role, password twice), `p` sets a person's password, `i` issues a token for the highlighted agent and shows it once, and `x` revokes the highlighted token on the tokens view. `src/tl_tui/widgets/account_forms.py` has the three forms (`AccountForm`, `PasswordForm`, `TokenForm`) and `TokenShown` with their layout, bindings and signatures final; `_kind` and the three `action_apply` bodies raise `NotImplementedError`. `admin_screen.py` has the key bindings, the second hint line and the layout; `current_token` and the four `action_*` bodies raise `NotImplementedError`. The keys, the key map and the snapshots of the list screens are the supervisor's and already in place. One provided test file (20 test functions, 3 snapshots) must pass.

## Brief references (pasted)
> **Brief 10 (TUI).** Screens render and post messages; business logic stays in services behind `ClientInterface`. Meaning never rides on colour alone.
> **ADR-0008 (owner).** The admin module manages accounts, roles and agent service tokens and is reachable from the CLI, API and TUI. A person has a password; an agent has tokens and no password.
> **ADR-0009 (already implemented).** Passwords: 12 to 128 characters and a common-password list; `WeakPasswordError.issues` names the rules and `describe_error` shows them, never the password. A password reset ends the account's sessions and clears its lock. A token is shown once and only its hash is stored. The last admin rules, a taken name, a disabled agent and a revoked token are the service's refusals.

### Specification
No form checks a rule the service owns: a weak password, a taken name, a disabled agent, an unknown role are `CLIENT_ERRORS`, shown with `describe_error(exc)` under the fields while the form stays open. The forms check only what the service cannot: that the two password fields match, that a required field is not empty, and that the days are a whole number. A password is read from a masked input exactly as typed (do not strip it), passed to the one call, and the password inputs are emptied after **every** attempt that reached a check or a call, success or failure (`_clear_passwords`). A password or a token never goes into a message, an attribute or a log line. The token leaves `TokenForm` only as the dismissed value `(label, token)`; the screen hands it to `TokenShown` and keeps nothing.

On the screen, `a` needs no highlighted account. `p`, `i` and `x` act on the highlighted account or token and say why they do nothing (a status line, no form) for the wrong kind or the wrong view. After a change the lists are read again and the highlighted account stays where it is.

Learnings that apply:
- pyright is `standard` for `packages/tl-tui`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided files live under `docs/tickets/P1-I0/provided/`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` clean and pyright clean.
- Commit your report at `docs/reports/P1-I0/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message.
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages. Run everything from the repository root, never with a package directory as the working directory.
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line.
- This is credential-handling glue. Never log, print, echo, store or put in an exception message a password, a hash or a session or agent token, and never add a debug line that does. Reviewers check this first.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number after "cases".
- Read `packages/tl-tui/AGENTS.md` first. Screens call `ClientInterface` only; they never import `tl_core.services` or touch the ledger.
- A client call may raise `CLIENT_ERRORS`: catch them where you call and show `describe_error(exc)`; keep the state.
- Meaning never rides on colour alone: the symbols `✓ ! ✗ ■` are in the cell text already.
- `Static` needs `markup=False` for user text; wrap `DataTable` cell text in `rich.text.Text` (a cell is read as markup).
- Tests: no async pytest plugin. They use `tests/helpers.run_pilot` and `screen_text`. Snapshot tests pin the terminal size and render no clock or random value.
- The provided snapshot files (`provided/snapshots/...raw`) pin the layout. Copy them into `packages/tl-tui/tests/__snapshots__/<test module name>/` byte for byte. Never run `--snapshot-update`: the layout (`compose`, `DEFAULT_CSS`, `BINDINGS`) is final in the stub, so a snapshot that differs means your logic differs.
- Before you hand in, run `uv run pyright packages/tl-tui` with the copied test in place: a type error in a provided test is reported to the supervisor, not edited.
- `Input(password=True)`, `Checkbox`, `RadioSet` and `RadioButton` are Textual widgets: read the value with `.value` and the chosen kind with `RadioSet.pressed_index`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-tui/src/tl_tui/widgets/account_forms.py` (the stub you complete):
```python
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
```

`packages/tl-tui/src/tl_tui/widgets/admin_screen.py` (the stub you complete):
```python
"""The accounts screen: who can sign in, with which roles, and the agents' tokens (P1-I0-T09).

A full-size modal opened with ``F10`` by an admin (brief 10; ADR-0008). The table lists every
account; ``t`` switches to the agent tokens. The panel under the table describes the highlighted
account. ``d`` disables or enables the account, ``r`` gives or takes away the admin role; each asks
for an optional reason first; ``a`` adds an account, ``p`` sets a person's password, ``i`` issues a
token for the highlighted agent (shown once) and ``x`` revokes the highlighted token on the tokens
view (P1-I0-T09b). The service decides what is allowed (the last active admin cannot
be disabled or demoted): a refusal is shown in the status line and nothing changes. Every change is
one client call and the lists are read again afterwards; nothing is stored here.

STUB (P1-I0-T09b): the bodies of `current_token` and `action_add`, `action_password`,
`action_issue` and `action_revoke` raise NotImplementedError and have a STEPS comment; everything
else is final. Implement them, then delete this paragraph, the STEPS comments and the
`ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static
from tl_core.auth.types import AccountView, AgentTokenView
from tl_core.util import utcnow

from tl_tui.admin_text import (
    ACCOUNT_COLUMNS,
    TOKEN_COLUMNS,
    account_cells,
    detail_lines,
    token_cells,
)
from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.widgets.account_forms import AccountForm, PasswordForm, TokenForm, TokenShown
from tl_tui.widgets.prompt import PromptScreen


class AdminScreen(ModalScreen[None]):
    """Accounts and agent tokens. ``now`` is the clock used for token expiry (tests fix it)."""

    KEY_HINTS: ClassVar[str] = "d disable/enable  r admin role  t tokens  F5 reload  Esc close"
    KEY_HINTS_MORE: ClassVar[str] = "a add  p password  i issue token  x revoke token"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("d", "toggle_disabled", "Disable/enable", show=False),
        Binding("r", "toggle_admin", "Admin role", show=False),
        Binding("t", "toggle_view", "Tokens", show=False),
        Binding("a", "add", "Add", show=False),
        Binding("p", "password", "Password", show=False),
        Binding("i", "issue", "Issue token", show=False),
        Binding("x", "revoke", "Revoke token", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    AdminScreen { background: $surface; }
    AdminScreen > Vertical { padding: 0 1; }
    AdminScreen #admin-title { text-style: bold; height: 1; }
    AdminScreen #admin-accounts, AdminScreen #admin-tokens { height: 1fr; min-height: 6; }
    AdminScreen #admin-detail { height: 9; border-top: solid $accent; padding: 0 1; }
    AdminScreen #admin-status { height: 1; }
    AdminScreen #admin-hints, AdminScreen #admin-hints-more { height: 1; color: $text-muted; }
    """

    def __init__(
        self, client: ClientInterface, actor: str, *, now: Callable[[], datetime] = utcnow
    ) -> None:
        super().__init__()
        self.client = client
        self.actor = actor
        self.now = now
        self.accounts: list[AccountView] = []
        self.tokens: list[AgentTokenView] = []
        self.showing_tokens = False

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", markup=False, id="admin-title")
            yield DataTable[str](id="admin-accounts", cursor_type="row", zebra_stripes=True)
            yield DataTable[str](id="admin-tokens", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="admin-detail")
            yield Static("", markup=False, id="admin-status")
            yield Static(self.KEY_HINTS, markup=False, id="admin-hints")
            yield Static(self.KEY_HINTS_MORE, markup=False, id="admin-hints-more")

    def on_mount(self) -> None:
        self.query_one("#admin-accounts", DataTable).add_columns(*ACCOUNT_COLUMNS)
        tokens = self.query_one("#admin-tokens", DataTable)
        tokens.add_columns(*TOKEN_COLUMNS)
        tokens.display = False
        self.reload()
        self.query_one("#admin-accounts", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def _stamp(self) -> str:
        return self.now().strftime("%Y-%m-%dT%H:%M:%S.000000Z")

    def reload(self) -> None:
        """Read both lists again and keep the highlighted account where it is."""
        keep = self.current_account()
        try:
            self.accounts = self.client.list_accounts()
            self.tokens = self.client.list_agent_tokens()
        except CLIENT_ERRORS as exc:
            self.accounts = []
            self.tokens = []
            self._fill(None)
            self._say(describe_error(exc), error=True)
            return
        self._fill(keep.account_id if keep is not None else None)

    def _fill(self, keep: str | None) -> None:
        accounts = self.query_one("#admin-accounts", DataTable)
        accounts.clear()
        for view in self.accounts:
            cells = account_cells(view)
            accounts.add_row(*(Text(cell) for cell in cells), key=view.account_id)
        if self.accounts:
            ids = [view.account_id for view in self.accounts]
            accounts.move_cursor(row=ids.index(keep) if keep in ids else 0)
        names = {view.account_id: view.username for view in self.accounts}
        tokens = self.query_one("#admin-tokens", DataTable)
        tokens.clear()
        now = self._stamp()
        for token in self.tokens:
            cells = token_cells(token, names, now)
            tokens.add_row(*(Text(cell) for cell in cells), key=token.token_id)
        self._title()
        self._describe()

    def _title(self) -> None:
        if self.showing_tokens:
            what, count = "Agent tokens", len(self.tokens)
        else:
            what, count = "Accounts", len(self.accounts)
        self.query_one("#admin-title", Static).update(f"{what} ({count})   t switches")

    def current_account(self) -> AccountView | None:
        table = self.query_one("#admin-accounts", DataTable)
        if not self.accounts or not 0 <= table.cursor_row < len(self.accounts):
            return None
        return self.accounts[table.cursor_row]

    def current_token(self) -> AgentTokenView | None:
        # STEPS: the token under the "#admin-tokens" cursor (cursor_row), or None when there are
        # no tokens or the row is out of range (like current_account).
        raise NotImplementedError

    def _describe(self) -> None:
        detail = self.query_one("#admin-detail", Static)
        if self.showing_tokens:
            detail.update("Tokens cannot be read back. Revoke one with `tl admin token revoke`.")
            return
        view = self.current_account()
        if view is None:
            detail.update("No accounts.")
            return
        detail.update("\n".join(detail_lines(view, self.tokens, self._stamp())))

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#admin-status", Static).update(("! " if error else "") + text)

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    # --- actions -------------------------------------------------------------------------

    def _ask_reason(self, title: str, then: Callable[[str | None], None]) -> None:
        def done(answer: str | None) -> None:
            if answer is None:  # cancelled: nothing is changed
                return
            then(answer or None)  # an empty answer is "no reason"

        self.app.push_screen(PromptScreen(title, "Reason (optional)", required=False), done)

    def action_toggle_disabled(self) -> None:
        view = self.current_account()
        if view is None or self.showing_tokens:
            return
        enabling = view.status == "disabled"
        verb = "Enable" if enabling else "Disable"

        def apply(reason: str | None) -> None:
            try:
                if enabling:
                    self.client.enable_account(view.account_id, reason=reason)
                else:
                    self.client.disable_account(view.account_id, reason=reason)
            except CLIENT_ERRORS as exc:
                self._say(describe_error(exc), error=True)
                return
            self.reload()
            self._say(f"{verb}d {view.username}")

        self._ask_reason(f"{verb} {view.username}", apply)

    def action_toggle_admin(self) -> None:
        view = self.current_account()
        if view is None or self.showing_tokens:
            return
        if view.kind != "person":
            self._say(f"Only people can be admins; {view.username} is a {view.kind} account.")
            return
        taking = "admin" in view.roles
        roles = ["user"] if taking else ["admin", "user"]
        verb = "Take the admin role from" if taking else "Make admin"

        def apply(reason: str | None) -> None:
            try:
                self.client.set_roles(view.account_id, roles, reason=reason)
            except CLIENT_ERRORS as exc:
                self._say(describe_error(exc), error=True)
                return
            self.reload()
            self._say(f"{view.username} is now {', '.join(roles)}")

        self._ask_reason(f"{verb} {view.username}", apply)

    def action_toggle_view(self) -> None:
        self.showing_tokens = not self.showing_tokens
        accounts = self.query_one("#admin-accounts", DataTable)
        tokens = self.query_one("#admin-tokens", DataTable)
        accounts.display = not self.showing_tokens
        tokens.display = self.showing_tokens
        (tokens if self.showing_tokens else accounts).focus()
        self._title()
        self._describe()

    def action_reload(self) -> None:
        self.reload()
        self._say("Reloaded.")

    def action_close(self) -> None:
        self.dismiss(None)

    def action_add(self) -> None:
        # STEPS: push AccountForm(self.client) on self.app with a callback `done(view)`: when the
        # form was cancelled (None) do nothing; else self.reload() and
        # self._say(f"Added {view.username}").
        raise NotImplementedError

    def action_password(self) -> None:
        # STEPS
        # 1. view = self.current_account(); return if None or showing_tokens.
        # 2. view.kind == "agent": self._say(f"{view.username} is an agent: it has tokens, not a
        #    password.") and return (no form).
        # 3. Push PasswordForm(self.client, view) with a callback `done(result)`: None (cancelled):
        #    nothing; else self.reload() and
        #    self._say(f"Password reset for {view.username}; their sessions ended").
        raise NotImplementedError

    def action_issue(self) -> None:
        # STEPS
        # 1. While showing_tokens: self._say("Press t for the accounts, pick the agent, then i.")
        #    and return.
        # 2. view = self.current_account(); return if None. A kind other than "agent":
        #    self._say(f"Only agents have tokens; {view.username} is a {view.kind} account.") and
        #    return.
        # 3. Push TokenForm(self.client, view) with a callback `done(result)`: None (cancelled):
        #    nothing; else (label, token) = result: self.reload();
        #    self._say(f"Issued token {label} for {view.username}"); then
        #    self.app.push_screen(TokenShown(label, token)). Keep the token in no attribute and in
        #    no message.
        raise NotImplementedError

    def action_revoke(self) -> None:
        # STEPS
        # 1. Not showing_tokens: self._say("Press t for the tokens, pick one, then x.") and return.
        # 2. token = self.current_token(); return if None.
        # 3. self._ask_reason(f"Revoke token {token.label}", apply) where apply(reason) calls
        #    client.revoke_agent_token(token.token_id, reason=reason); on CLIENT_ERRORS
        #    self._say(describe_error(exc), error=True) and return (nothing changes; check no rule
        #    here); on success self.reload() and self._say(f"Revoked token {token.label}").
        raise NotImplementedError
```

`tl_tui.client.ClientInterface` (the calls the forms use; do not change):
```python
def create_account(self, username: str, display_name: str, *, kind: AccountKind = "person", roles: Sequence[str] = ("user",), password: str | None = None) -> AccountView: ...
def reset_password(self, account_id: str, new_password: str) -> AccountView: ...
def issue_agent_token(self, account_id: str, label: str, *, expires_in_days: int | None = 90) -> tuple[AgentTokenView, str]: ...
def revoke_agent_token(self, token_id: str, *, reason: str | None = None) -> AgentTokenView: ...
```
`tl_tui.errors`: `CLIENT_ERRORS` and `describe_error(exc) -> str` (a weak password's message lists the broken rules).

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/account_forms.py`
- `packages/tl-tui/src/tl_tui/widgets/admin_screen.py`
- `packages/tl-tui/src/tl_tui/widgets/setting_form.py` (a form in this package: an example)
- `docs/tickets/P1-I0/provided/t09b-test_account_forms.py.txt`
- `docs/tickets/P1-I0/provided/snapshots/t09b/`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/account_forms.py` (bodies only)
- `packages/tl-tui/src/tl_tui/widgets/admin_screen.py` (bodies only)
- `packages/tl-tui/tests/test_account_forms.py` (create, copy of the provided file)
- `packages/tl-tui/tests/__snapshots__/test_account_forms/*.raw` (create, copies of the provided snapshots)
- `docs/reports/P1-I0/P1-I0-T09b.md` (create: your report)

## Steps
1. `cp docs/tickets/P1-I0/provided/t09b-test_account_forms.py.txt packages/tl-tui/tests/test_account_forms.py`, then `mkdir -p packages/tl-tui/tests/__snapshots__/test_account_forms && cp docs/tickets/P1-I0/provided/snapshots/t09b/*.raw packages/tl-tui/tests/__snapshots__/test_account_forms/`.
2. Fill the bodies of `account_forms.py`, then `admin_screen.py`, by their `STEPS` comments.
3. Delete the `STUB` paragraphs, the `STEPS` comments and the `# ruff: noqa: F401` lines in both modules.
4. Run the acceptance commands.

## Acceptance
```
uv run ruff format packages/tl-tui && uv run ruff check packages/tl-tui
uv run pytest packages/tl-tui/tests/test_account_forms.py -q
uv run pytest packages/tl-tui -q
uv run pyright
just check
```
Expected: the first pytest command reports 20 passed (from 20 functions; the three snapshot tests pass against the provided files without `--snapshot-update`); the whole `packages/tl-tui` suite passes; pyright and `just check` are clean.

## Tests to add
- `packages/tl-tui/tests/test_account_forms.py` (20 test functions, provided): the add form and the extra hint line; adding a person, an admin, a sim account and an agent; passwords that differ and an empty username; weak password, taken name and a non-admin refused by the service; Esc; the password form (reset, lock cleared, checks, the rules shown, agents explained); issuing a token and showing it once, with days and "never expires", bad input, a disabled agent, a person or the wrong view explained; revoking a token with a reason, Esc, an already revoked one and the wrong view; three snapshots.

## Report requirements
Standard report (`docs/templates/haiku-report.md`): deviations first, then the commands above with their decisive output lines, then open questions. State that no password or token is stored, shown or logged outside the masked input and the one-time `TokenShown`, and that no rule is checked beyond the three listed.

## Escalation triggers
- Stop and report *Blocked* if a snapshot differs after your logic matches the STEPS: do not edit the layout and do not update the snapshot; report the difference.
- Stop if a provided test needs a change outside the two modules, or if the test file fails `pyright` or `ruff`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
