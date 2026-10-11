"""Entry point: ``tl-tui`` / ``python -m tl_tui`` / ``tl tui`` (brief 4).

Embedded mode (the default) opens the ledger in this process: a SQLite file or a
``postgresql://`` URL (`--db` or `TL_DB`; prefer the variable, a URL carries the password). Remote
mode talks to a running API server: ``--remote URL``. Both modes show live updates.

Both ask for a username and a password first (``tl_tui.sign_in``), unless the caller already knows
who is using it (``tl tui`` passes the session ``tl login`` made) or, remote only, a token is given
(``--token`` or the ``TL_TOKEN`` environment variable, which keeps the token out of the process
list: an agent or dev token, honoured by the server only where it allows them).
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

from tl_adapters.backend import BackendUnavailableError, ledger_exists
from tl_adapters.db import as_target, display_target

from tl_tui.app import TlApp
from tl_tui.embedded import DEFAULT_ACTOR, EmbeddedAuthenticator, EmbeddedClient
from tl_tui.remote import RemoteAuthenticator, RemoteClient, sign_out
from tl_tui.sign_in import SignedIn, SignInApp

DEFAULT_DB = "./dev/data/tl.db"
DEFAULT_PROJECT = "P123"
DEFAULT_TYPE = "core.Record"


def build_app(
    db: str | Path,
    project: str = DEFAULT_PROJECT,
    *,
    live: bool = True,
    actor: str = DEFAULT_ACTOR,
    record_type: str = DEFAULT_TYPE,
    is_admin: bool = False,
) -> TlApp:
    """The app over the ledger ``db`` (SQLite file or Postgres URL), showing ``project`` (embedded).

    ``actor`` is shown in the header and recorded on the settings the screens change.
    ``record_type`` is the record type the grid lists: ``core.Record`` or an extension type.
    ``is_admin`` opens the accounts screen (F10) to the person using the app.
    """
    scope = f"project:{project}"
    client = EmbeddedClient.for_target(db, actor=actor)
    return TlApp(
        client,
        scope=scope,
        record_type=record_type,
        actor=actor,
        is_admin=is_admin,
        feed=client.change_feed(scope) if live else None,
    )


def build_remote_app(
    url: str,
    token: str,
    project: str = DEFAULT_PROJECT,
    *,
    actor: str = DEFAULT_ACTOR,
    live: bool = True,
    record_type: str = DEFAULT_TYPE,
    is_admin: bool = False,
) -> TlApp:
    """The app over the API server at ``url`` using the bearer ``token`` (remote).

    ``token`` is a session token from a sign-in, or a dev or agent token. ``actor`` is only what
    the header shows: the server records the actor of the token.
    """
    scope = f"project:{project}"
    client = RemoteClient.connect(url, token)
    return TlApp(
        client.as_client(),
        scope=scope,
        record_type=record_type,
        mode="remote",
        actor=actor,
        is_admin=is_admin,
        feed=client.change_feed(scope) if live else None,
    )


def make_app(
    *,
    remote: str | None = None,
    token: str | None = None,
    db: str | Path | None = None,
    project: str | None = None,
    actor: str | None = None,
    record_type: str | None = None,
    signed_in: SignedIn | None = None,
) -> TlApp:
    """The app for the options, falling back to the environment, then to the defaults.

    ``TL_REMOTE`` and ``TL_TOKEN`` select remote mode; ``TL_TYPE`` the record type of the grid.
    ``signed_in`` (from :func:`run` or ``tl tui``) names the person: it sets the actor and, in
    remote mode, supplies the token. Raises ``ValueError`` for a remote URL without a token or a
    URL that is not http(s).
    """
    url = remote or os.environ.get("TL_REMOTE") or None
    proj = project or os.environ.get("TL_PROJECT", DEFAULT_PROJECT)
    rtype = record_type or os.environ.get("TL_TYPE") or DEFAULT_TYPE
    who = signed_in.actor if signed_in is not None else actor or DEFAULT_ACTOR
    admin = signed_in is not None and signed_in.is_admin
    if url is None:
        return build_app(
            db or os.environ.get("TL_DB", DEFAULT_DB),
            proj,
            actor=who,
            record_type=rtype,
            is_admin=admin,
        )
    secret = (signed_in.token if signed_in is not None else None) or token
    secret = secret or os.environ.get("TL_TOKEN")
    if not secret:
        raise ValueError("remote mode needs a token: sign in, pass --token or set TL_TOKEN")
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"--remote must be an http(s) URL, got {url!r}")
    return build_remote_app(url, secret, proj, actor=who, record_type=rtype, is_admin=admin)


def plain_http_warning(url: str) -> str | None:
    """A line for the sign-in screen when the password would cross the network unencrypted."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "http" or host == "localhost":
        return None
    try:
        if ipaddress.ip_address(host).is_loopback:
            return None
    except ValueError:
        pass
    return f"warning: {host or url} is plain http: your password would be sent unencrypted"


def needs_sign_in(*, remote: str | None = None, token: str | None = None) -> bool:
    """Whether the options leave open who is using the TUI: embedded, or remote without a token."""
    if not (remote or os.environ.get("TL_REMOTE")):
        return True
    return not (token or os.environ.get("TL_TOKEN"))


def sign_in_first(*, remote: str | None = None, db: str | Path | None = None) -> SignedIn | None:
    """Show the sign-in screen; the person signed in, or ``None`` when they quit it.

    Raises ``ValueError`` for a remote URL that is not http(s) or an embedded ledger that does not
    exist (signing in would create an empty one), and ``BackendUnavailableError`` for a Postgres
    server that cannot be reached.
    """
    url = remote or os.environ.get("TL_REMOTE") or None
    if url is not None:
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"--remote must be an http(s) URL, got {url!r}")
        return SignInApp(
            RemoteAuthenticator(url), target=f"server {url}", hint=plain_http_warning(url)
        ).run()
    target = as_target(db or os.environ.get("TL_DB", DEFAULT_DB))
    where = display_target(target)
    if not ledger_exists(target):
        raise ValueError(f"no ledger at {where}; run `tl init` first")
    authenticator = EmbeddedAuthenticator.for_target(target)
    return SignInApp(authenticator, target=f"ledger {where}", hint=authenticator.demo_hint()).run()


def run(
    *,
    remote: str | None = None,
    token: str | None = None,
    db: str | Path | None = None,
    project: str | None = None,
    actor: str | None = None,
    record_type: str | None = None,
    signed_in: SignedIn | None = None,
) -> None:
    """Sign in (unless ``signed_in`` or a token says who it is), build the app, run it, release it.

    Quitting the sign-in screen ends the run without opening the ledger.
    """
    url = remote or os.environ.get("TL_REMOTE") or None
    session_token: str | None = None  # a server session this call made and must end
    if signed_in is None and needs_sign_in(remote=remote, token=token):
        signed_in = sign_in_first(remote=remote, db=db)
        if signed_in is None:
            return  # the person left the sign-in screen
        session_token = signed_in.token if url is not None else None
    try:
        app = make_app(
            remote=remote,
            token=token,
            db=db,
            project=project,
            actor=actor,
            record_type=record_type,
            signed_in=signed_in,
        )
        try:
            app.run()
        finally:
            close = getattr(app.client, "close", None)
            if callable(close):
                close()
    finally:
        if url is not None and session_token is not None:
            sign_out(url, session_token)  # on every way out: the session is not left to expire


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tl-tui", description="Throughline terminal UI.")
    parser.add_argument("--remote", metavar="URL", help="API server URL (default: embedded)")
    parser.add_argument(
        "--token",
        help="dev token for --remote; prefer TL_TOKEN (command-line arguments are visible in ps)",
    )
    parser.add_argument(
        "--db", help=f"embedded: SQLite file or postgresql:// URL (TL_DB, default {DEFAULT_DB})"
    )
    parser.add_argument("--project", help=f"project id (TL_PROJECT, default {DEFAULT_PROJECT})")
    parser.add_argument("--actor", help="remote: the name the header shows")
    parser.add_argument(
        "--type", dest="record_type", help="record type of the grid (TL_TYPE, default core.Record)"
    )
    ns = parser.parse_args(argv)
    try:
        run(
            remote=ns.remote,
            token=ns.token,
            db=ns.db,
            project=ns.project,
            actor=ns.actor,
            record_type=ns.record_type,
        )
    except (ValueError, BackendUnavailableError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
