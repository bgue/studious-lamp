# P1-I0-T09 — TUI accounts screen

Status: ready
Tier: haiku
Labels: tui
Depends on: P1-I0-T04 (merged: the admin routes and the API client's admin calls the remote client passes through); P1-I0-S4 (the admin calls on `ClientInterface`, the embedded implementation and `FakeClient`, on `p1/i0a`); P1-I0-T08 is not needed (the screen is opened by `TlApp`, which the supervisor wired to `F10`)
Branch: `p1/i0a-t09-tui-admin`

## Goal
An admin sees and manages accounts in the TUI. `AdminScreen` (`F10`, admins only) lists every account with its kind, roles, status and any lock; the panel under the table describes the highlighted account; `d` disables or enables it and `r` gives or takes away the admin role, each after an optional reason; `t` switches to the agent tokens (id, agent, label, expiry, state); `F5` reads the lists again. `src/tl_tui/admin_text.py` (pure text for cells and the panel) and `src/tl_tui/widgets/admin_screen.py` have their layout and signatures final; the bodies raise `NotImplementedError`. `TlApp`, the key map, the command palette and the client (`list_accounts`, `set_roles`, `disable_account`, `enable_account`, `list_agent_tokens`, ...) are the supervisor's and already in place. Adding accounts, resetting passwords and issuing or revoking tokens are a later ticket (the screen says to use `tl admin token revoke`). Two provided test files (7 + 15 test functions, 3 snapshots) must pass.

## Brief references (pasted)
> **Brief 10 (TUI).** Screens render and post messages; business logic stays in services behind `ClientInterface`. Meaning never rides on colour alone.
> **ADR-0008 (owner).** The admin module manages accounts, roles and agent service tokens and is reachable from the CLI, API and TUI. Two roles: `admin` and `user`; only a person can be an admin.
> **ADR-0009 (already implemented).** The last active admin cannot be disabled or demoted (`LastAdminError`); disabling an account ends its sessions and stops its agent tokens; a token is shown once and cannot be read back. The client calls raise the `tl_core.auth.errors` classes; a non-admin gets `ForbiddenError` ("this action needs the admin role").

### Specification
The screen checks no rule: `d` and `r` call the client and show the service's refusal in the status line (`! <message>`) while nothing changes; success reloads both lists and says what happened. A reload keeps the highlighted account. A client error on reload (a non-admin, an unreachable server) empties the lists and shows the message. `now` is injected so token expiry is testable; `_stamp()` gives it as ISO UTC text with microseconds (`2026-10-11T12:00:00.000000Z`), which compares correctly as text with the stored stamps. The reason prompt is the existing `PromptScreen` (`required=False`): Esc cancels (no call), an empty answer is no reason (`None`).

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
- `FakeClient` (`tests/fakes_admin.py`, written by the supervisor, with a parity test against the embedded client) is the test double; it has `seed_account`, `is_admin` and `admin_calls`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-tui/src/tl_tui/admin_text.py` (the stub you complete):
```python
"""Plain text for the accounts screen: table cells and the detail panel (P1-I0-T09).

Pure functions of an `AccountView` or `AgentTokenView`, so they are tested without a terminal.
Status is never colour alone: `✓` active, `✗` disabled or revoked, `!` expired, `■` locked.

STUB (P1-I0-T09): the function bodies raise NotImplementedError; the constants and signatures are
final. Each body has a STEPS comment. Implement them, then delete this paragraph, the STEPS
comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from tl_core.auth.types import AccountView, AgentTokenView

ACCOUNT_COLUMNS = ("Name", "Kind", "Roles", "Status", "Lock")
TOKEN_COLUMNS = ("Agent", "Label", "Expires", "State", "Id")


def moment(stamp: str) -> str:
    """``2026-10-11T12:15:00.123456Z`` as ``2026-10-11 12:15`` (UTC)."""
    # STEPS: datetime.fromisoformat(stamp.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    raise NotImplementedError


def status_text(view: AccountView) -> str:
    """``✓ active`` or ``✗ disabled``."""
    # STEPS: by view.status.
    raise NotImplementedError


def lock_text(view: AccountView) -> str:
    """``■ until 2026-10-11 12:15`` while a lockout is in force, else an empty string."""
    # STEPS: view.locked_until is None -> ""; else f"■ until {moment(view.locked_until)}".
    raise NotImplementedError


def account_cells(view: AccountView) -> tuple[str, str, str, str, str]:
    """The five cells of an account row, in the order of `ACCOUNT_COLUMNS`."""
    # STEPS: (username, kind, roles joined with ", ", status_text(view), lock_text(view)).
    raise NotImplementedError


def token_state(token: AgentTokenView, now: str) -> str:
    """``✗ revoked``, ``! expired`` (``expires_at`` is not after ``now``), else ``✓ active``."""
    # STEPS: check revoked first, then expiry. Both stamps are ISO UTC text that sorts as text.
    raise NotImplementedError


def token_cells(
    token: AgentTokenView, names: dict[str, str], now: str
) -> tuple[str, str, str, str, str]:
    """The five cells of a token row, in the order of `TOKEN_COLUMNS` (``?``: unknown agent)."""
    # STEPS: (names.get(token.account_id, "?"), token.label, "never" when expires_at is None
    # else moment(expires_at), token_state(token, now), token.token_id).
    raise NotImplementedError


def detail_lines(view: AccountView, tokens: Sequence[AgentTokenView], now: str) -> list[str]:
    """The panel under the table: one ``Label   value`` line per fact; agents also count tokens."""
    # STEPS
    # 1. Pairs, in this order: Name (username), Shown as (display_name), Kind, Roles (", "
    #    joined), Status (status_text), Lock ("none", or f"■ locked until {moment(...)} UTC"),
    #    Created (moment(view.created_at)).
    # 2. For an agent account add Tokens: of the tokens whose account_id is this account's,
    #    f"{live} live, {revoked} revoked" where live counts token_state == "✓ active" and
    #    revoked counts token.revoked.
    # 3. Each line is f"{label:<10}{value}".
    raise NotImplementedError
```

`packages/tl-tui/src/tl_tui/widgets/admin_screen.py` (the stub you complete):
```python
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
```

`tl_tui.client.ClientInterface` (the calls the screen uses; do not change):
```python
def list_accounts(self) -> list[AccountView]: ...
def set_roles(self, account_id: str, roles: Sequence[str], *, reason: str | None = None) -> AccountView: ...
def disable_account(self, account_id: str, *, reason: str | None = None) -> AccountView: ...
def enable_account(self, account_id: str, *, reason: str | None = None) -> AccountView: ...
def list_agent_tokens(self, account_id: str | None = None, *, include_revoked: bool = True) -> list[AgentTokenView]: ...
```
`tl_core.auth.types` (do not change): `AccountView(account_id, username, display_name, kind, roles, status, locked_until, created_at, seq)` and `AgentTokenView(token_id, account_id, label, expires_at, revoked, issued_by)`; `kind` is `person | agent | sim`, `status` is `active | disabled`, times are ISO-8601 UTC text.

`tl_tui.widgets.prompt.PromptScreen(title: str, label: str, *, initial: str = "", required: bool = True)` dismisses with the stripped text or `None` when cancelled; its input is `#prompt-input`.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/admin_text.py`
- `packages/tl-tui/src/tl_tui/widgets/admin_screen.py`
- `packages/tl-tui/src/tl_tui/widgets/settings_screen.py` (the closest existing screen: an example)
- `docs/tickets/P1-I0/provided/t09-test_admin_text.py.txt`
- `docs/tickets/P1-I0/provided/t09-test_admin_screen.py.txt`
- `docs/tickets/P1-I0/provided/snapshots/t09/`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/admin_text.py` (bodies only)
- `packages/tl-tui/src/tl_tui/widgets/admin_screen.py` (bodies only)
- `packages/tl-tui/tests/test_admin_text.py` (create, copy of the provided file)
- `packages/tl-tui/tests/test_admin_screen.py` (create, copy of the provided file)
- `packages/tl-tui/tests/__snapshots__/test_admin_screen/*.raw` (create, copies of the provided snapshots)
- `docs/reports/P1-I0/P1-I0-T09.md` (create: your report)

## Steps
1. Copy the two provided test files to `packages/tl-tui/tests/test_admin_text.py` and `test_admin_screen.py`, then `mkdir -p packages/tl-tui/tests/__snapshots__/test_admin_screen && cp docs/tickets/P1-I0/provided/snapshots/t09/*.raw packages/tl-tui/tests/__snapshots__/test_admin_screen/`.
2. Fill the bodies of `admin_text.py` first (its tests are pure), then `admin_screen.py`, by their `STEPS` comments.
3. Delete the `STUB` paragraphs, the `STEPS` comments and the `# ruff: noqa: F401` lines in both modules.
4. Run the acceptance commands.

## Acceptance
```
uv run ruff format packages/tl-tui && uv run ruff check packages/tl-tui
uv run pytest packages/tl-tui/tests/test_admin_text.py packages/tl-tui/tests/test_admin_screen.py -q
uv run pytest packages/tl-tui -q
uv run pyright packages/tl-tui
just check
```
Expected: the first pytest command reports 22 passed (from 7 + 15 functions; the three snapshot tests pass against the provided files without `--snapshot-update`); the whole `packages/tl-tui` suite passes; pyright reports no errors; `just check` is clean.

## Tests to add
- `packages/tl-tui/tests/test_admin_text.py` (7 test functions, provided): moments, status and lock symbols, account and token cells, token states, the detail panel for people and agents.
- `packages/tl-tui/tests/test_admin_screen.py` (15 test functions, provided): the table and hints; the panel follows the cursor; `d` disables and enables with a reason; Esc at the prompt; the service's refusals shown; `r` gives and takes the admin role; agents and sim accounts refused locally; `t` switches views; `F5`; a non-admin; Esc closes; three snapshots.

## Report requirements
Standard report (`docs/templates/haiku-report.md`): deviations first, then the commands above with their decisive output lines, then open questions. State that the screen checks no rule itself and that nothing in it handles a password or a token.

## Escalation triggers
- Stop and report *Blocked* if a snapshot differs after your logic matches the STEPS: do not edit the layout and do not update the snapshot; report the difference.
- Stop if a provided test needs a change outside the two modules or if a step seems to ask you to decide who may do what: the service decides.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
