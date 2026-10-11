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
