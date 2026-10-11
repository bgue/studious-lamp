# P1-I0-T06 — `tl login`, `tl logout`, `tl whoami`

Status: ready
Tier: haiku
Labels: cli
Depends on: P1-I0-S3 (CLI session module, on `p1/i0a`); no other ticket
Branch: `p1/i0a-t06-cli-login`

## Goal
A person signs in to a ledger file from the shell: `tl login USERNAME` asks for the password without echo (or reads one line from stdin with `--password-stdin`), stores the session token in the private session file, and prints who they are. `tl whoami` names the signed-in account and its roles; `tl logout` ends the session in the ledger and forgets it. From then on the default `--actor` of every `tl` command is that person (the supervisor's `actor_hook` already does this from the session file). `src/tl_cli/login.py` has the three functions with their signatures, options and docstrings final; the bodies raise `NotImplementedError`. The three commands are already registered in `tl_cli/main.py`. One provided test file (18 test functions) must pass.

## Brief references (pasted)
> **Brief 11.1 Auth.** OAuth2/OIDC bearer tokens; API keys for service accounts; scopes per module.
> **ADR-0008 (owner).** Username and password now, behind an identity seam; two roles `admin` and `user`; the admin module is reachable from the CLI, API and TUI.
> **ADR-0009 (the design, already implemented in `tl_core.auth` and `tl_cli.session`).** A session token is `tls_` + 256 random bits, stored only as SHA-256, valid 12 hours, deleted on sign-out, disable and password change. Five failed sign-ins within 15 minutes lock a name for 15 minutes; the counters are keyed by the normalised username whether or not the account exists, so an unknown name fails exactly like a wrong password (`error: invalid username or password`). A disabled account is reported only to the right password. `tl login` keeps the token in `TL_SESSION_FILE` (default `~/.config/throughline/session.json`, mode 0600), one entry per ledger file. The token is never printed. Embedded commands trust whoever can open the ledger file (decision D3); an explicit `--actor` is still honoured. The demo account `demo`/`demo` signs in only where `TL_ENV` is dev, demo or test.

### Specification
`login` is `sessions.sign_in` on the ledger plus a stored entry. All of the account rules (lockout, disabled accounts, the demo gate, the enumeration-safe messages) live in `sign_in`; the command adds none and catches nothing itself: `service_errors()` turns every failure into `error: <message>` (exit 1) and nothing is stored. A second login for the same ledger replaces the first and **ends the earlier session** in the ledger, so sessions do not pile up. If the session file cannot be used (open to other users, damaged, not writable) the session just created is ended again and the error is shown: a login must never leave a live session whose token was not stored. Output is exactly one line: `signed in as user:root (admin)`, roles joined with `, `.

`logout` forgets the entry and, when the ledger file exists, ends that session in the ledger. Nobody signed in is not an error: it prints `not signed in` and exits 0. `whoami` prints the actor and `roles: admin, user`; `require_session` already checks the stored token against the ledger (an ended, expired or disabled-account session counts as not signed in).

Learnings that apply (paste of the relevant `docs/memory/LEARNINGS.md` entries and the build's conventions):
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

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/login.py` (the stub you complete):
```python
"""`tl login`, `tl logout` and `tl whoami`: the CLI session of an embedded ledger (ADR-0009 sec. 4).

Thin glue over `tl_core.auth.sessions` and `tl_cli.session`. The password is read by
`tl_cli.prompts.read_password` (a hidden prompt or one line of standard input), never from an
option. The session token goes into the session file and is never printed. P1-I0-T06.

STUB (P1-I0-T06): the function bodies raise NotImplementedError; their signatures, annotations and
docstrings are final (they make the `--help` text). Each body has a STEPS comment. Implement them,
then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from tl_core.auth import sessions

from tl_cli.admin import backend_of
from tl_cli.prompts import read_password
from tl_cli.session import (
    SessionFileError,
    StoredSession,
    db_target,
    expires_at_from,
    fail,
    forget,
    load,
    open_backend,
    require_session,
    save,
    service_errors,
)


def login(
    ctx: typer.Context,
    username: Annotated[str, typer.Argument(help="Your username.")],
    password_stdin: Annotated[
        bool, typer.Option("--password-stdin", help="Read the password from standard input.")
    ] = False,
) -> None:
    """Sign in to the ledger (--db). The password is asked for without echo, or read from stdin."""
    # STEPS
    # 1. db: Path = ctx.obj; backend = backend_of(ctx)  (exits 1 with `error: no ledger ...`).
    # 2. password = read_password(from_stdin=password_stdin, prompt=f"Password for {username}").
    # 3. Inside `with service_errors():` call
    #    `principal, token = sessions.sign_in(backend, username=username, password=password)`.
    #    A wrong password, an unknown name, a lock and a disabled account all end here as
    #    `error: ...` (exit 1) and nothing is stored.
    # 4. target = db_target(db). In a `try` that catches (SessionFileError, OSError) as exc:
    #    earlier = load(target); then save(StoredSession(target=target, username=username,
    #    actor=principal.actor, expires_at=expires_at_from(sessions.SESSION_TTL), token=token)).
    #    In the `except`: end the session just made, `sessions.sign_out(backend, token=token)`,
    #    then `fail(str(exc))`.
    # 5. If `earlier` is not None, end it: `sessions.sign_out(backend, token=earlier.token)`.
    # 6. typer.echo(f"signed in as {principal.actor} ({', '.join(principal.roles)})").
    #    Print nothing else: never the token, never the password.
    raise NotImplementedError


def logout(ctx: typer.Context) -> None:
    """Sign out: end the session in the ledger and forget it. Harmless when not signed in."""
    # STEPS
    # 1. db: Path = ctx.obj. earlier = forget(db_target(db)); a SessionFileError is
    #    `fail(str(exc))`.
    # 2. If earlier is None: typer.echo("not signed in") and return (exit 0).
    # 3. If db.is_file(): sessions.sign_out(open_backend(db), token=earlier.token).
    # 4. typer.echo(f"signed out {earlier.username}").
    raise NotImplementedError


def whoami(ctx: typer.Context) -> None:
    """Print who you are signed in as, and your roles."""
    # STEPS
    # 1. principal = require_session(ctx.obj)  (exits 1 with `error: not signed in: ...`).
    # 2. typer.echo(principal.actor), then typer.echo(f"roles: {', '.join(principal.roles)}").
    raise NotImplementedError
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

`packages/tl-cli/tests/auth_support.py` (supervisor-written helpers the provided test imports; read, do not change): `new_ledger`, `run` (as `tl`), `bootstrap`, `login`, `rows`, `live_sessions`, `last_actor`.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/login.py`
- `packages/tl-cli/src/tl_cli/session.py`
- `packages/tl-cli/src/tl_cli/prompts.py`
- `packages/tl-cli/src/tl_cli/admin.py` (only `backend_of`)
- `packages/tl-cli/src/tl_cli/serve.py` (an example of a Typer command in this package)
- `docs/tickets/P1-I0/provided/t06-test_cli_login.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/login.py` (bodies only)
- `packages/tl-cli/tests/test_cli_login.py` (create, copy of the provided file)
- `docs/reports/P1-I0/P1-I0-T06.md` (create: your report)

## Steps
1. `cp docs/tickets/P1-I0/provided/t06-test_cli_login.py.txt packages/tl-cli/tests/test_cli_login.py`
2. Fill the three bodies by their `STEPS` comments.
3. Delete the `STUB` paragraph, the `STEPS` comments and the `# ruff: noqa: F401` line.
4. Run the acceptance commands.

## Acceptance
```
uv run ruff format packages/tl-cli && uv run ruff check packages/tl-cli
uv run pytest packages/tl-cli/tests/test_cli_login.py -q
uv run pytest packages/tl-cli -q
just check
```
Expected: the first pytest command reports all cases passed (20 cases: 18 functions); the whole `packages/tl-cli` suite passes; `just check` is clean.

## Tests to add
- `packages/tl-cli/tests/test_cli_login.py` (18 test functions, provided): login output and file mode; the token never printed; hidden prompt; whoami; wrong password and unknown name fail alike and store nothing; names that cannot exist; lockout and `tl admin unlock`; disabled accounts; a second login ends the first session; logout; logout and whoami when not signed in; an ended session; one ledger per session; the default actor follows login and logout in a non-dev environment; the demo gate; an unusable session file; missing ledger and empty password; no `--password` option.

## Report requirements
Standard report (`docs/templates/haiku-report.md`): deviations first, then the commands above with their decisive output lines, then open questions. State that no `try`/`except` other than the one in `login` step 4 was added and that nothing printed, logged or raised includes a password or a token.

## Escalation triggers
- Stop and report *Blocked* if a provided test fails and the fix needs a change outside `login.py` (the session module, `sessions.sign_in`, `main.py`).
- Stop if a step seems to ask you to decide who may do what, or to change what a message says: the services and the session module already decide.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
