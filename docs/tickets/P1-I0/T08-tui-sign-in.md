# P1-I0-T08 — TUI sign-in screen

Status: ready
Tier: haiku
Labels: tui
Depends on: P1-I0-T03 (merged: `POST /auth/sign-in` and the client's `sign_in`, which `RemoteAuthenticator` calls); P1-I0-S3 and S4 (on `p1/i0a`)
Branch: `p1/i0a-t08-tui-sign-in`

## Goal
The TUI asks who is using it. `SignInScreen` shows a username and a password field (the password masked), calls an injected `Authenticator`, shows the refusal under the fields when it fails, and dismisses with the `SignedIn` when it succeeds; `SignInApp` hosts the screen alone and returns the result from `run()`. `src/tl_tui/sign_in.py` already has `SignedIn`, the `Authenticator` protocol, the layout (`compose`, `DEFAULT_CSS`, `BINDINGS`) and every signature; the logic bodies (`on_mount`, `on_input_submitted`, `_submit`, `action_quit`, `SignInApp.on_mount`) raise `NotImplementedError`. The authenticators (`EmbeddedAuthenticator` in `embedded.py`, `RemoteAuthenticator` in `remote.py`) and the wiring in `main.py` are the supervisor's and already in place. One provided test file (12 test functions, 2 snapshots) must pass.

## Brief references (pasted)
> **Brief 10 (TUI).** Screens render and post messages; business logic stays in services behind `ClientInterface`.
> **ADR-0008 (owner).** Username and password now, behind an identity seam; the embedded modes sign in against the local account store.
> **ADR-0009 (already implemented).** A wrong password and an unknown name give the same message (`invalid username or password`); five failed sign-ins lock a name for 15 minutes (`AccountLockedError`, whose message says when); a disabled account is reported only to the right password. The password is passed to the one `authenticate` call and nowhere else: it is not stored, shown, logged or put in a message.

### Specification
`_submit` runs on the UI thread (the embedded check takes about 100 ms; a remote one is bounded by the 3 s client timeout). The username is stripped, the password is used exactly as typed. An empty field is asked for without calling the authenticator. A refusal is any of `CLIENT_ERRORS` (`ServiceError` and `ApiError` families, which include `AccountLockedError` and `ApiUnavailableError`); its text is `describe_error(exc)`. After a refusal the password field is emptied and focused and the username stays; after success the password field is emptied before `dismiss`. Catch nothing else: a bug must not look like a wrong password.

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
- Do not name an attribute after a DOM property (`visible`, `query`). `Input(password=True)` masks with `•`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-tui/src/tl_tui/sign_in.py` (the stub you complete):
```python
"""The sign-in screen of the TUI (ADR-0009 section 4; P1-I0-T08).

The TUI asks for a username and a password before it shows anything. This module is the screen
and the small app that hosts it; it knows nothing about ledgers or servers. It is given an
``Authenticator``, a function that turns a username and a password into a :class:`SignedIn` or
raises (``tl_tui.embedded.EmbeddedAuthenticator`` checks them on the ledger file,
``tl_tui.remote.RemoteAuthenticator`` signs in to a server). The password never leaves the input
widget except as the argument of that one call; it is not stored, shown or put in a message.

STUB (P1-I0-T08): the bodies marked STEPS raise NotImplementedError; the dataclass, the protocol,
the layout (`compose`, `DEFAULT_CSS`) and every signature are final (the provided snapshots pin
the layout). Implement the bodies, then delete this paragraph and the STEPS comments.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Protocol

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Input, Static

from tl_tui.errors import CLIENT_ERRORS, describe_error


@dataclass(frozen=True)
class SignedIn:
    """Who signed in. ``token`` is the session token of a server sign-in (``None`` embedded)."""

    actor: str
    username: str
    roles: tuple[str, ...]
    token: str | None = field(default=None, repr=False)

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles


class Authenticator(Protocol):
    """Checks a username and password. Raises a ``ServiceError`` or ``ApiError`` on failure."""

    def __call__(self, username: str, password: str) -> SignedIn: ...


class SignInScreen(Screen[SignedIn | None]):
    """Username and password. Dismisses with the :class:`SignedIn`, or ``None`` on Esc."""

    KEY_HINTS: ClassVar[str] = "Enter sign in  Tab next field  Esc quit"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "quit", "Quit", show=False),
        Binding("ctrl+q", "quit", "Quit", show=False),
    ]

    DEFAULT_CSS = """
    SignInScreen { align: center middle; }
    SignInScreen > Vertical {
        width: 60; max-width: 100%; height: auto;
        border: round $accent; background: $surface; padding: 1 2;
    }
    SignInScreen #sign-in-title { text-style: bold; }
    SignInScreen #sign-in-target { color: $text-muted; }
    SignInScreen .sign-in-label { margin-top: 1; }
    SignInScreen #sign-in-error { color: $error; height: auto; margin-top: 1; }
    SignInScreen #sign-in-hint { color: $text-muted; height: auto; margin-top: 1; }
    SignInScreen #sign-in-keys { color: $text-muted; margin-top: 1; }
    """

    def __init__(
        self, authenticate: Authenticator, *, target: str, hint: str | None = None
    ) -> None:
        super().__init__()
        self.authenticate = authenticate
        self.target = target
        self.hint = hint

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Sign in to Throughline", id="sign-in-title", markup=False)
            yield Static(self.target, id="sign-in-target", markup=False)
            yield Static("Username", classes="sign-in-label", markup=False)
            yield Input(id="sign-in-username")
            yield Static("Password", classes="sign-in-label", markup=False)
            yield Input(password=True, id="sign-in-password")
            yield Static("", id="sign-in-error", markup=False)
            if self.hint:
                yield Static(self.hint, id="sign-in-hint", markup=False)
            yield Static(self.KEY_HINTS, id="sign-in-keys", markup=False)

    def on_mount(self) -> None:
        # STEPS: focus the username input: self.query_one("#sign-in-username", Input).focus().
        raise NotImplementedError

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # STEPS
        # 1. event.stop().
        # 2. If event.input.id == "sign-in-username": focus "#sign-in-password" and return.
        # 3. Otherwise (the password input): self._submit().
        raise NotImplementedError

    def _show_error(self, message: str) -> None:
        self.query_one("#sign-in-error", Static).update(message)

    def _submit(self) -> None:
        # STEPS
        # 1. username = the username input's value, stripped. password_input = the
        #    "#sign-in-password" input; password = its value as typed (do NOT strip it).
        # 2. No username: self._show_error("Enter your username"), focus the username input, return.
        #    No password: self._show_error("Enter your password"), focus the password input, return.
        #    Neither calls the authenticator.
        # 3. try: signed_in = self.authenticate(username, password)
        #    except CLIENT_ERRORS as exc: self._show_error(describe_error(exc)); clear the password
        #    input (value = ""); focus it; return. (Keep the username. Catch nothing else.)
        # 4. On success clear the password input (value = "") and self.dismiss(signed_in).
        #    Never put the password in a message, a log line or an attribute.
        raise NotImplementedError

    def action_quit(self) -> None:
        # STEPS: self.dismiss(None).
        raise NotImplementedError


class SignInApp(App[SignedIn | None]):
    """Runs :class:`SignInScreen` alone. ``run()`` returns the :class:`SignedIn` or ``None``."""

    TITLE = "Throughline"
    ENABLE_COMMAND_PALETTE = False

    def __init__(
        self, authenticate: Authenticator, *, target: str, hint: str | None = None
    ) -> None:
        super().__init__()
        self._screen = SignInScreen(authenticate, target=target, hint=hint)

    def on_mount(self) -> None:
        # STEPS: self.push_screen(self._screen, self.exit)  (the screen's result ends the app).
        raise NotImplementedError
```

`tl_tui.errors` (do not change): `CLIENT_ERRORS: tuple[type[Exception], ...]` and `describe_error(exc: BaseException) -> str`.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/sign_in.py`
- `packages/tl-tui/src/tl_tui/widgets/prompt.py` (a small modal in this package: an example)
- `docs/tickets/P1-I0/provided/t08-test_sign_in.py.txt`
- `docs/tickets/P1-I0/provided/snapshots/t08/`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/sign_in.py` (bodies only)
- `packages/tl-tui/tests/test_sign_in.py` (create, copy of the provided file)
- `packages/tl-tui/tests/__snapshots__/test_sign_in/*.raw` (create, copies of the provided snapshots)
- `docs/reports/P1-I0/P1-I0-T08.md` (create: your report)

## Steps
1. `cp docs/tickets/P1-I0/provided/t08-test_sign_in.py.txt packages/tl-tui/tests/test_sign_in.py`, then `mkdir -p packages/tl-tui/tests/__snapshots__/test_sign_in && cp docs/tickets/P1-I0/provided/snapshots/t08/*.raw packages/tl-tui/tests/__snapshots__/test_sign_in/`.
2. Fill the bodies by their `STEPS` comments.
3. Delete the `STUB` paragraph, the `STEPS` comments and the `# ruff: noqa: F401` line.
4. Run the acceptance commands.

## Acceptance
```
uv run ruff format packages/tl-tui && uv run ruff check packages/tl-tui
uv run pytest packages/tl-tui/tests/test_sign_in.py -q
uv run pytest packages/tl-tui -q
uv run pyright packages/tl-tui
just check
```
Expected: the first pytest command reports 14 passed (from 12 functions; the two snapshot tests pass against the provided files without `--snapshot-update`); the whole `packages/tl-tui` suite passes; pyright reports no errors; `just check` is clean.

## Tests to add
- `packages/tl-tui/tests/test_sign_in.py` (12 test functions, provided): the layout and the optional hint; focus and the Enter chain; trimmed username and untrimmed password; refusals shown, password cleared, retry succeeds; locked and unreachable messages; empty fields; the password masked on screen; Esc and Ctrl+Q; the token hidden in `SignedIn`'s repr; the screen pushed by a larger app; two snapshots (80x24, and 120x40 with an error).

## Report requirements
Standard report (`docs/templates/haiku-report.md`): deviations first, then the commands above with their decisive output lines, then open questions. State that nothing shows, stores or logs the password, and that you caught only `CLIENT_ERRORS`.

## Escalation triggers
- Stop and report *Blocked* if a snapshot differs after your logic matches the STEPS: do not edit the layout and do not update the snapshot; report the difference.
- Stop if a provided test needs a change outside `sign_in.py`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
