# P1-I0-T07 — `tl admin user ...` and `tl admin token ...`

Status: ready
Tier: haiku
Labels: cli
Depends on: P1-I0-S3 (CLI session module and `tl admin` helpers, on `p1/i0a`); not T06 (the provided tests sign in through helpers, not through `tl login`)
Branch: `p1/i0a-t07-cli-admin`

## Goal
An admin manages accounts and agent tokens from the shell. `tl admin user ls | show | add | roles | disable | enable | reset-password` and `tl admin token ls | issue | revoke` each make one call into `tl_core.auth` for the signed-in admin. `src/tl_cli/admin_user.py` and `src/tl_cli/admin_token.py` have every command with its options and docstring final; the bodies raise `NotImplementedError`. Both groups are already mounted under `tl admin` in `tl_cli/main.py`, next to the supervisor's `bootstrap`, `unlock` and `audit`. Two provided test files (22 + 14 test functions) must pass.

## Brief references (pasted)
> **ADR-0008 (owner).** The admin module manages accounts, roles and agent service tokens and is reachable from the CLI, API and TUI; service tokens for MCP agents are issued per agent by an admin (`agent:<name>`).
> **ADR-0009 (the design, already implemented in `tl_core.auth`).** Account events are ledger events with metadata only; every secret lives in `auth_*` operational tables. The last active admin cannot be disabled or demoted (`LastAdminError`). Passwords: 12 to 128 characters, a common-password list, no composition rules; `WeakPasswordError.issues` names the rules, never the password. A password reset ends the account's sessions and clears its lock. A token is shown once; only its hash is stored; default life 90 days. `admin.*` actions need a human admin. Hashing happens before the write transaction (one global writer lock).
> **Embedded CLI (decision D3).** The CLI opens the ledger file directly. These commands still require a signed-in admin (`tl login`), so the history says who did what; the recovery commands `bootstrap`, `unlock` and `audit` (already written) are the ones that need no sign-in.

### Specification
Every command starts with `admin = require_admin(ctx.obj)` and `backend = backend_of(ctx)`, and runs its service calls inside `with service_errors():`. `admin.actor` is `by=` in every write, so the ledger records `user:root`, never `user:dev`. People are named by **username**; `find_account(backend, username)` (a helper) turns the name into the account and exits 1 with `error: no account named 'x'`. The commands decide nothing: roles, the last-admin rule, double disables, token limits and the password policy are the services' answers, shown as `error: <message>`.

**Passwords.** `add` (for a person or sim account) and `reset-password` read the password with `read_password(from_stdin=password_stdin, confirm=not password_stdin)` and run `prepare_password(password, username=...)` (policy and slow hash) **before** `with backend() as uow:` opens the write transaction. A weak password then fails before anything is written, and `service_errors()` lists the broken rules under the error line. An agent account takes no password, so `add --kind agent` reads none (standard input may be empty). The password is never printed.

**Tokens.** `token issue` prints the token alone on stdout (one line, so `TL_AGENT_TOKEN=$(tl admin token issue triage --label mcp)` works) and the facts on stderr. `--days` and `--no-expiry` together are refused, whatever the number (`--days` defaults to none, which means 90). `ls` hides revoked tokens unless `--all`; the state is `revoked`, `expired` or `active`.

Learnings that apply:
- pyright is `standard` for `packages/tl-cli`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided files live under `docs/tickets/P1-I0/provided/`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` clean and pyright clean.
- Commit your report at `docs/reports/P1-I0/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message.
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages. Run everything from the repository root, never with a package directory as the working directory.
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line.
- This is credential-handling glue. Never log, print, echo, store or put in an exception message a password, a hash or a session or agent token, and never add a debug line that does. Reviewers check this first.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number after "cases".
- CLI error convention: a failure prints `error: <message>` on stderr and exits 1, with no traceback. `tl_cli.session.fail` and `service_errors` do that; do not write your own `try`/`except` around service calls unless a step says so.
- `ctx.obj` is the ledger path (`Path`) the root `--db` option names. `backend_of(ctx)` opens it and exits 1 with `error: no ledger at ...` when the file is missing.
- A password is never an option or an argument (it would show in `ps` and shell history). `read_password` takes it from a hidden prompt or from one line of standard input (`--password-stdin`).
- The tests run `tl` in process with `typer.testing.CliRunner`; `TL_SESSION_FILE` points at a private file in every test (root `conftest.py`).
- The provided tests keep several people signed in at once with separate `TL_SESSION_FILE`s (`auth_support.separate_session`); a command reads the session file named in its environment.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/admin_user.py` (the stub you complete):
```python
"""`tl admin user ...`: list, show, add, roles, disable, enable, reset-password (P1-I0-T07).

Needs a signed-in admin (`tl login`). Each command is one call into `tl_core.auth`. A password is
read by `read_password` (hidden prompt or stdin), checked and hashed **before** the write
transaction opens, and never printed.

STUB (P1-I0-T07): the function bodies raise NotImplementedError; their signatures, annotations and
docstrings are final (they make the `--help` text). Each body has a STEPS comment. Implement them,
then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

import json
from typing import Annotated, cast

import typer
from tl_core.auth import accounts, queries
from tl_core.auth.password import prepare_password
from tl_core.auth.types import AccountKind

from tl_cli.admin import account_fields, account_line, backend_of, find_account
from tl_cli.prompts import read_password
from tl_cli.session import require_admin, service_errors

app = typer.Typer(
    help="Accounts: list, add, roles, disable, enable, reset passwords.", no_args_is_help=True
)

_Name = Annotated[str, typer.Argument(help="The account's username.")]
_Reason = Annotated[str | None, typer.Option("--reason", help="Why (kept in the history).")]
_Stdin = Annotated[bool, typer.Option("--password-stdin", help="Read the password from stdin.")]

# Every command starts the same way, in this order:
#   admin = require_admin(ctx.obj)    # exits 1: `error: not signed in ...` / `error: forbidden ...`
#   backend = backend_of(ctx)         # exits 1: `error: no ledger at ...`
# and runs the service calls inside `with service_errors():`, which turns every service failure
# into `error: <message>` (exit 1) and lists the broken rules of a weak password. `admin.actor` is
# `by=` in every write. Do not catch exceptions yourself.


@app.command("ls")
def ls(
    ctx: typer.Context,
    as_json: Annotated[bool, typer.Option("--json", help="Print a JSON list.")] = False,
) -> None:
    """List every account: name, kind, roles, status, and any lock."""
    # STEPS
    # 1. require_admin(ctx.obj); backend = backend_of(ctx).
    # 2. `with service_errors(), backend(readonly=True) as uow:`
    #    views = queries.list_accounts(uow.conn()).
    # 3. With --json: typer.echo(json.dumps([view.model_dump() for view in views], indent=2)) and
    #    return.
    # 4. Else one typer.echo(account_line(view)) per view.
    raise NotImplementedError


@app.command("show")
def show(ctx: typer.Context, username: _Name) -> None:
    """Show one account, one field per line."""
    # STEPS
    # 1. require_admin(ctx.obj). With service_errors():
    #    view = find_account(backend_of(ctx), username).
    # 2. One typer.echo(line) per line of account_fields(view).
    raise NotImplementedError


@app.command("add")
def add(
    ctx: typer.Context,
    username: _Name,
    display_name: Annotated[
        str | None, typer.Option("--display-name", help="Shown name; default: the username.")
    ] = None,
    kind: Annotated[
        str,
        typer.Option("--kind", help="person, sim or agent (an agent has a token, no password)."),
    ] = "person",
    role: Annotated[
        list[str] | None,
        typer.Option("--role", help="admin or user; repeat for both. Default user."),
    ] = None,
    password_stdin: _Stdin = False,
) -> None:
    """Create an account. People and sim accounts get a password; agents get tokens instead."""
    # STEPS
    # 1. admin = require_admin(ctx.obj); backend = backend_of(ctx).
    # 2. Inside `with service_errors():` and BEFORE any write transaction:
    #    prepared = None; if kind != "agent": password = read_password(from_stdin=password_stdin,
    #    confirm=not password_stdin); prepared = prepare_password(password, username=username).
    #    (The policy check and the slow hash must not run inside a write transaction.)
    # 3. Still inside service_errors(): `with backend() as uow:` view = accounts.create_account(uow,
    #    username=username, display_name=display_name or username, kind=cast(AccountKind, kind),
    #    roles=role or ["user"], password=prepared, by=admin.actor).
    # 4. typer.echo(f"created {account_line(view)}"). For an agent also
    #    typer.echo(f"next: tl admin token issue {view.username} --label <what it is for>").
    #    Never print the password.
    raise NotImplementedError


@app.command("roles")
def roles(
    ctx: typer.Context,
    username: _Name,
    role: Annotated[list[str], typer.Option("--role", help="admin or user; repeat for both.")],
    reason: _Reason = None,
) -> None:
    """Replace an account's roles. The last active admin cannot be demoted."""
    # STEPS
    # 1. admin = require_admin(ctx.obj); backend = backend_of(ctx).
    # 2. With service_errors(): target = find_account(backend, username); then
    #    `with backend() as uow:` view = accounts.set_roles(uow, account_id=target.account_id,
    #    roles=role, by=admin.actor, reason=reason).
    # 3. typer.echo(account_line(view)).
    raise NotImplementedError


@app.command("disable")
def disable(ctx: typer.Context, username: _Name, reason: _Reason = None) -> None:
    """Disable an account: it cannot sign in and its sessions and tokens stop working."""
    # STEPS
    # Like `roles`, with accounts.disable(uow, account_id=..., by=admin.actor, reason=reason).
    # Print typer.echo(account_line(view)).
    raise NotImplementedError


@app.command("enable")
def enable(ctx: typer.Context, username: _Name, reason: _Reason = None) -> None:
    """Enable a disabled account again."""
    # STEPS
    # Like `disable`, with accounts.enable(...).
    raise NotImplementedError


@app.command("reset-password")
def reset_password(ctx: typer.Context, username: _Name, password_stdin: _Stdin = False) -> None:
    """Set a new password without the old one. Ends the account's sessions and clears any lock."""
    # STEPS
    # 1. admin = require_admin(ctx.obj); backend = backend_of(ctx).
    # 2. Inside `with service_errors():` target = find_account(backend, username);
    #    password = read_password(from_stdin=password_stdin, confirm=not password_stdin);
    #    prepared = prepare_password(password, username=target.username)  (before any write).
    # 3. Then `with backend() as uow:` accounts.change_password(uow, account_id=target.account_id,
    #    new_password=prepared, by=admin.actor).
    # 4. typer.echo(f"password reset for {target.username}; their sessions ended and any lock is "
    #    "cleared").
    raise NotImplementedError
```

`packages/tl-cli/src/tl_cli/admin_token.py` (the stub you complete):
```python
"""`tl admin token ...`: list, issue and revoke agent tokens (P1-I0-T07).

Needs a signed-in admin. A new token is printed once, alone on stdout, so a script can capture it
(`TL_AGENT_TOKEN=$(tl admin token issue triage --label mcp)`); the facts about it go to stderr.

STUB (P1-I0-T07): the function bodies raise NotImplementedError; their signatures, annotations and
docstrings are final (they make the `--help` text). Each body has a STEPS comment. Implement them,
then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

from datetime import timedelta
from typing import Annotated

import typer
from tl_core.auth import accounts, queries
from tl_core.util import utcnow

from tl_cli.admin import backend_of, find_account
from tl_cli.session import fail, require_admin, service_errors

app = typer.Typer(help="Agent tokens: list, issue, revoke.", no_args_is_help=True)

DEFAULT_DAYS = 90

# Every command starts: admin = require_admin(ctx.obj); backend = backend_of(ctx). Service calls
# run inside `with service_errors():` (service failures become `error: <message>`, exit 1). Do not
# catch exceptions yourself. Never print a token except in `issue`, and never log one.


@app.command("ls")
def ls(
    ctx: typer.Context,
    user: Annotated[str | None, typer.Option("--user", help="Only this agent.")] = None,
    show_all: Annotated[bool, typer.Option("--all", help="Include revoked tokens.")] = False,
) -> None:
    """List agent tokens: id, agent, label, expiry, state. The tokens themselves are not stored."""
    # STEPS
    # 1. require_admin(ctx.obj); backend = backend_of(ctx).
    # 2. Inside `with service_errors():` owner = None if user is None else
    #    find_account(backend, user).account_id; then `with backend(readonly=True) as uow:`
    #    names = {a.account_id: a.username for a in queries.list_accounts(uow.conn())} and
    #    tokens = queries.list_agent_tokens(uow.conn(), account_id=owner, include_revoked=show_all).
    # 3. now = utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"). For each token: state is "revoked" if
    #    token.revoked, else "expired" if token.expires_at is not None and token.expires_at <= now,
    #    else "active". expires = token.expires_at or "never".
    # 4. typer.echo(f"{token.token_id}  {names.get(token.account_id, '?')}  {token.label}  "
    #    f"{expires}  {state}")  -- two spaces between fields.
    raise NotImplementedError


@app.command("issue")
def issue(
    ctx: typer.Context,
    username: Annotated[str, typer.Argument(help="The agent account's username.")],
    label: Annotated[str, typer.Option("--label", help="What the token is for.")],
    days: Annotated[
        int | None,
        typer.Option("--days", min=1, max=3650, help=f"Days until it expires (default {DEFAULT_DAYS})."),
    ] = None,
    no_expiry: Annotated[
        bool, typer.Option("--no-expiry", help="A token that never expires.")
    ] = False,
) -> None:
    """Issue a token for an agent account. It is printed once and cannot be read back."""
    # STEPS
    # 1. admin = require_admin(ctx.obj); backend = backend_of(ctx).
    # 2. If no_expiry and days is not None: fail("use --days or --no-expiry, not both").
    # 3. expires = None if no_expiry else utcnow() + timedelta(days=days or DEFAULT_DAYS).
    # 4. Inside `with service_errors():` target = find_account(backend, username); then
    #    `with backend() as uow:` view, token = accounts.issue_agent_token(uow,
    #    account_id=target.account_id, label=label, expires_at=expires, by=admin.actor).
    # 5. After the block: typer.echo(token)  (stdout, alone on its line), then
    #    typer.echo(f"issued token {view.token_id} for agent:{target.username}, expires "
    #    f"{view.expires_at or 'never'}; this is the only time it is shown", err=True).
    raise NotImplementedError


@app.command("revoke")
def revoke(
    ctx: typer.Context,
    token_id: Annotated[str, typer.Argument(help="The token id from `tl admin token ls`.")],
    reason: Annotated[str | None, typer.Option("--reason", help="Why.")] = None,
) -> None:
    """Revoke a token at once."""
    # STEPS
    # 1. admin = require_admin(ctx.obj); backend = backend_of(ctx).
    # 2. `with service_errors(), backend() as uow:` accounts.revoke_agent_token(uow,
    #    token_id=token_id, by=admin.actor, reason=reason).
    # 3. typer.echo(f"revoked {token_id}").
    raise NotImplementedError
```

`packages/tl-cli/src/tl_cli/admin.py`:
```python
def backend_of(ctx: typer.Context) -> UowFactory:
    """The unit-of-work factory of the ledger ``--db`` names; exits 1 if there is no such ledger."""
    db: Path = ctx.obj
    if not db.is_file():
        fail(f"no ledger at {db}: run `tl init` first")
    return open_backend(db)


def find_account(backend: UowFactory, username: str) -> AccountView:
    """The account called ``username``, or `error: no account named ...` and exit 1."""
    with backend(readonly=True) as uow:
        found = queries.find_account(uow.conn(), username=username)
    if found is None:
        fail(f"no account named {username!r}")
    return found


def account_line(view: AccountView) -> str:
    """``root  person  admin  active`` (two spaces), plus ``  locked until <time>`` while locked."""
    line = f"{view.username}  {view.kind}  {','.join(view.roles)}  {view.status}"
    return line + (f"  locked until {view.locked_until}" if view.locked_until else "")


def account_fields(view: AccountView) -> list[str]:
    """One ``name value`` line per field of an account (``tl admin user show``)."""
    return [
        f"username {view.username}",
        f"id {view.account_id}",
        f"display_name {view.display_name}",
        f"kind {view.kind}",
        f"roles {','.join(view.roles)}",
        f"status {view.status}",
        f"locked_until {view.locked_until or '-'}",
        f"created_at {view.created_at}",
    ]
```

`packages/tl-cli/src/tl_cli/session.py`:
```python
class StoredSession:
    """One saved sign-in. ``token`` is secret: it is left out of ``repr``."""

    target: str
    username: str
    actor: str
    expires_at: str
    token: str = field(repr=False)

    def expired(self, now: datetime | None = None) -> bool:
        moment = (now or utcnow()).strftime("%Y-%m-%dT%H:%M:%S")
        return self.expires_at[:19] <= moment


def db_target(db: Path) -> str:
    """The target name of a ledger file: ``db:`` and its absolute path."""
    return f"db:{db.expanduser().resolve()}"


def expires_at_from(lifetime: timedelta) -> str:
    """The ISO-8601 UTC time ``lifetime`` from now, as stored in ``StoredSession.expires_at``."""
    return (utcnow() + lifetime).strftime("%Y-%m-%dT%H:%M:%SZ")
```

`packages/tl-cli/src/tl_cli/session.py` (the helpers the commands use; bodies elided):
```python
def db_target(db: Path) -> str: ...           # the key of a ledger in the session file
def expires_at_from(lifetime: timedelta) -> str: ...
def save(stored: StoredSession) -> None: ...  # replaces the entry of stored.target, file mode 0600
def load(target: str) -> StoredSession | None: ...  # None when absent or expired; SessionFileError if the file is unusable
def forget(target: str) -> StoredSession | None: ...  # removes and returns the entry (even an expired one)
def open_backend(db: Path) -> UowFactory: ...
def fail(message: str) -> NoReturn: ...        # prints `error: <message>` on stderr, exits 1
def service_errors() -> Iterator[None]: ...    # context manager: ServiceError -> `error: <message>`, exit 1
def current_principal(db: Path) -> Principal | None: ...
def require_session(db: Path) -> Principal: ...  # `error: not signed in: run `tl login <username>``, exit 1
def require_admin(db: Path) -> Principal: ...    # also `error: forbidden: this command needs the admin role`
class SessionFileError(Exception): ...
```
`packages/tl-cli/src/tl_cli/prompts.py`:
```python
def read_password(*, from_stdin: bool, confirm: bool = False, prompt: str = "Password") -> str:
    """One password: a line of standard input, or a hidden prompt (twice if ``confirm``)."""
    if from_stdin:
        line = sys.stdin.readline()
        value = line.rstrip("\r\n")
        if not value:
            fail("no password on standard input")
        return value
    value = typer.prompt(prompt, hide_input=True)
    if confirm and typer.prompt(f"Repeat {prompt.lower()}", hide_input=True) != value:
        fail("the two passwords differ")
    return str(value)
```
`tl_core.auth.sessions` (supervisor-built, security-reviewed; do not change):
```python
SESSION_TTL = timedelta(hours=12)
def sign_in(backend: UowFactory, *, username: str, password: str, clock=utcnow) -> tuple[Principal, str]: ...
def sign_out(backend: UowFactory, *, token: str, clock=utcnow) -> None: ...  # idempotent
```

`tl_core.auth` (supervisor-built, security-reviewed; do not change): `accounts.create_account(uow, *, username, display_name, kind, roles, password: PreparedPassword | None, by) -> AccountView`, `set_roles(uow, *, account_id, roles, by, reason)`, `disable` / `enable(uow, *, account_id, by, reason)`, `change_password(uow, *, account_id, new_password: PreparedPassword, by)`, `issue_agent_token(uow, *, account_id, label, expires_at, by) -> tuple[AgentTokenView, str]`, `revoke_agent_token(uow, *, token_id, by, reason)`; `queries.list_accounts(conn)`, `list_agent_tokens(conn, *, account_id=None, include_revoked=True)`; `password.prepare_password(password, *, username=None) -> PreparedPassword`.

`packages/tl-cli/tests/auth_support.py` (supervisor-written helpers the provided tests import; read, do not change).

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/admin_user.py`
- `packages/tl-cli/src/tl_cli/admin_token.py`
- `packages/tl-cli/src/tl_cli/admin.py` (the helpers and the three recovery commands)
- `packages/tl-cli/src/tl_cli/session.py`
- `docs/tickets/P1-I0/provided/t07-test_cli_admin_user.py.txt`
- `docs/tickets/P1-I0/provided/t07-test_cli_admin_token.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/admin_user.py` (bodies only)
- `packages/tl-cli/src/tl_cli/admin_token.py` (bodies only)
- `packages/tl-cli/tests/test_cli_admin_user.py` (create, copy of the provided file)
- `packages/tl-cli/tests/test_cli_admin_token.py` (create, copy of the provided file)
- `docs/reports/P1-I0/P1-I0-T07.md` (create: your report)

## Steps
1. `cp docs/tickets/P1-I0/provided/t07-test_cli_admin_user.py.txt packages/tl-cli/tests/test_cli_admin_user.py` and the same for `t07-test_cli_admin_token.py.txt` -> `test_cli_admin_token.py`.
2. Fill the ten command bodies by their `STEPS` comments.
3. Delete the `STUB` paragraph, the `STEPS` comments and the `# ruff: noqa: F401` line in both modules.
4. Run the acceptance commands.

## Acceptance
```
uv run ruff format packages/tl-cli && uv run ruff check packages/tl-cli
uv run pytest packages/tl-cli/tests/test_cli_admin_user.py packages/tl-cli/tests/test_cli_admin_token.py -q
uv run pytest packages/tl-cli -q
just check
```
Expected: the first pytest command reports 48 passed (30 + 18 cases, from 22 + 14 functions); the whole `packages/tl-cli` suite passes; `just check` is clean.

## Tests to add
- `packages/tl-cli/tests/test_cli_admin_user.py` (22 test functions, provided): list, JSON list, show with a lock; add (person, hidden prompt twice, roles and kinds, agent, refusals, weak passwords listed, taken names); roles with the actor and reason in the event; the last-admin rule; disable and enable ending sessions; reset-password ending sessions and clearing a lock; every command refused without an admin session; no `--password` option.
- `packages/tl-cli/tests/test_cli_admin_token.py` (14 test functions, provided): the token alone on stdout; it authenticates as the agent and is stored nowhere; default 90 days, `--days`, `--no-expiry` and their limits; only for enabled agent accounts; listing, `--all`, `--user`; revoke stops the token at once; revoking twice or an unknown id; every command refused without an admin session.

## Report requirements
Standard report (`docs/templates/haiku-report.md`): deviations first, then the commands above with their decisive output lines, then open questions. State that no `try`/`except` was added, that every service call runs after `require_admin`, that passwords are prepared before any write transaction, and that nothing printed or logged includes a password or a token other than the one deliberate `token issue` line.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and the fix needs a change outside the two modules (`admin.py`, `session.py`, a service).
- Stop if a step seems to ask you to decide who may do what, or what a message says: the services and `require_admin` already decide.

## Change log
- 2026-10-11 (supervisor, after the first run): `--days` now defaults to `None` (meaning 90) and is refused together with `--no-expiry` even when it is 90 (the implementer's open question: the default could not be told from an explicit 90). Changed on this branch: `admin_token.py`, the provided test and its copy (one new test, `test_an_explicit_default_number_of_days_does_not_slip_past_no_expiry`).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
