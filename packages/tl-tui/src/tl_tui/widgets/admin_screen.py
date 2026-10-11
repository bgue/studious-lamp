"""The accounts screen: who can sign in, with which roles, and the agents' tokens (P1-I0-T09).

A full-size modal opened with ``F10`` by an admin (brief 10; ADR-0008). The table lists every
account; ``t`` switches to the agent tokens. The panel under the table describes the highlighted
account. ``d`` disables or enables the account, ``r`` gives or takes away the admin role; each asks
for an optional reason first. The service decides what is allowed (the last active admin cannot
be disabled or demoted): a refusal is shown in the status line and nothing changes. Every change is
one client call and the lists are read again afterwards; nothing is stored here.

STUB (P1-I0-T09): the bodies below raise NotImplementedError; the layout (`compose`,
`DEFAULT_CSS`, `BINDINGS`) and every signature are final (the provided snapshots pin the layout).
Each body has a STEPS comment. Implement them, then delete this paragraph, the STEPS comments and
the `ruff: noqa` line.
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
from tl_tui.widgets.prompt import PromptScreen


class AdminScreen(ModalScreen[None]):
    """Accounts and agent tokens. ``now`` is the clock used for token expiry (tests fix it)."""

    KEY_HINTS: ClassVar[str] = "d disable/enable  r admin role  t tokens  F5 reload  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("d", "toggle_disabled", "Disable/enable", show=False),
        Binding("r", "toggle_admin", "Admin role", show=False),
        Binding("t", "toggle_view", "Tokens", show=False),
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
    AdminScreen #admin-hints { height: 1; color: $text-muted; }
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

    def on_mount(self) -> None:
        # STEPS
        # 1. Add ACCOUNT_COLUMNS to "#admin-accounts" and TOKEN_COLUMNS to "#admin-tokens"
        #    (DataTable.add_columns(*columns)). Hide the tokens table: its `display = False`.
        # 2. self.reload(); then focus "#admin-accounts".
        raise NotImplementedError

    # --- data ----------------------------------------------------------------------------

    def _stamp(self) -> str:
        # STEPS: self.now() as ISO UTC text with microseconds: strftime("%Y-%m-%dT%H:%M:%S.000000Z")
        raise NotImplementedError

    def reload(self) -> None:
        """Read both lists again and keep the highlighted account where it is."""
        # STEPS
        # 1. keep = self.current_account().
        # 2. try: self.accounts = self.client.list_accounts(); self.tokens =
        #    self.client.list_agent_tokens()
        #    except CLIENT_ERRORS as exc: set both lists to [], self._fill(None), self._say(
        #    describe_error(exc), error=True), return.
        # 3. self._fill(keep.account_id if keep is not None else None).
        raise NotImplementedError

    def _fill(self, keep: str | None) -> None:
        # STEPS
        # 1. Accounts table: clear(); add_row(*(Text(cell) for cell in account_cells(view)),
        #    key=view.account_id) per account (Text, not str: a cell is read as markup).
        #    If there are accounts: move_cursor(row=index of `keep` in the account ids, else 0).
        # 2. names = {account_id: username}. Tokens table: clear(); add_row(*(Text(cell) for cell
        #    in token_cells(token, names, self._stamp())), key=token.token_id) per token.
        # 3. self._title(); self._describe().
        raise NotImplementedError

    def _title(self) -> None:
        # STEPS: "#admin-title" gets f"{what} ({count})   t switches" with what/count = "Agent
        # tokens"/len(self.tokens) while showing_tokens, else "Accounts"/len(self.accounts).
        raise NotImplementedError

    def current_account(self) -> AccountView | None:
        # STEPS: the account under the "#admin-accounts" cursor (table.cursor_row), or None when
        # there are no accounts or the row is out of range.
        raise NotImplementedError

    def _describe(self) -> None:
        # STEPS: update "#admin-detail": while showing_tokens, "Tokens cannot be read back. Revoke
        # one with `tl admin token revoke`."; with no current account "No accounts."; else
        # "\n".join(detail_lines(view, self.tokens, self._stamp())).
        raise NotImplementedError

    def _say(self, text: str, *, error: bool = False) -> None:
        # STEPS: update "#admin-status" with the text, prefixed "! " when error.
        raise NotImplementedError

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        # STEPS: event.stop(); self._describe().
        raise NotImplementedError

    # --- actions -------------------------------------------------------------------------

    def _ask_reason(self, title: str, then: Callable[[str | None], None]) -> None:
        # STEPS: push PromptScreen(title, "Reason (optional)", required=False) on self.app with a
        # callback `done(answer)`: when answer is None (cancelled) do nothing; else call
        # then(answer or None) (an empty answer is "no reason").
        raise NotImplementedError

    def action_toggle_disabled(self) -> None:
        # STEPS
        # 1. view = self.current_account(); return if None or showing_tokens.
        # 2. enabling = view.status == "disabled"; verb = "Enable" or "Disable".
        # 3. self._ask_reason(f"{verb} {view.username}", apply) where apply(reason) calls
        #    client.enable_account(view.account_id, reason=reason) or client.disable_account(...);
        #    on CLIENT_ERRORS: self._say(describe_error(exc), error=True) and return (nothing
        #    changes; do not re-check any rule here); on success self.reload() and
        #    self._say(f"{verb}d {view.username}").
        raise NotImplementedError

    def action_toggle_admin(self) -> None:
        # STEPS
        # 1. view = self.current_account(); return if None or showing_tokens.
        # 2. If view.kind != "person": self._say(f"Only people can be admins; {view.username} is a
        #    {view.kind} account.") and return (no client call).
        # 3. taking = "admin" in view.roles; roles = ["user"] if taking else ["admin", "user"];
        #    verb = "Take the admin role from" if taking else "Make admin".
        # 4. self._ask_reason(f"{verb} {view.username}", apply) where apply(reason) calls
        #    client.set_roles(view.account_id, roles, reason=reason); on CLIENT_ERRORS show it as
        #    in action_toggle_disabled; on success reload() and
        #    self._say(f"{view.username} is now {', '.join(roles)}").
        raise NotImplementedError

    def action_toggle_view(self) -> None:
        # STEPS: flip self.showing_tokens; show exactly one of "#admin-accounts" / "#admin-tokens"
        # (their `display`), focus the shown one, then self._title() and self._describe().
        raise NotImplementedError

    def action_reload(self) -> None:
        # STEPS: self.reload(); self._say("Reloaded.").
        raise NotImplementedError

    def action_close(self) -> None:
        # STEPS: self.dismiss(None).
        raise NotImplementedError
