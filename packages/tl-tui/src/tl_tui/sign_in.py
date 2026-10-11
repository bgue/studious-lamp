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
