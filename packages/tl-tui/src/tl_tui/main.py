"""Entry point: ``tl-tui`` / ``python -m tl_tui`` / ``tl tui`` (brief 4).

Embedded mode (the default) opens the SQLite ledger in this process. Remote mode talks to a running
API server: ``--remote URL`` with a dev token (``--token`` or the ``TL_TOKEN`` environment variable,
which keeps the token out of the process list). Both modes show live updates.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from tl_tui.app import TlApp
from tl_tui.embedded import EmbeddedClient
from tl_tui.remote import RemoteClient

DEFAULT_DB = "./dev/data/tl.db"
DEFAULT_PROJECT = "P123"
DEFAULT_ACTOR = "user:dev"


def build_app(db: str | Path, project: str = DEFAULT_PROJECT, *, live: bool = True) -> TlApp:
    """The app over the SQLite dev ledger at ``db``, showing project ``project`` (embedded)."""
    scope = f"project:{project}"
    client = EmbeddedClient.for_sqlite(db)
    return TlApp(client, scope=scope, feed=client.change_feed(scope) if live else None)


def build_remote_app(
    url: str,
    token: str,
    project: str = DEFAULT_PROJECT,
    *,
    actor: str = DEFAULT_ACTOR,
    live: bool = True,
) -> TlApp:
    """The app over the API server at ``url`` using the dev token ``token`` (remote).

    ``actor`` is only what the header shows: the server records the actor of the token.
    """
    scope = f"project:{project}"
    client = RemoteClient.connect(url, token)
    return TlApp(
        client.as_client(),
        scope=scope,
        mode="remote",
        actor=actor,
        feed=client.change_feed(scope) if live else None,
    )


def make_app(
    *,
    remote: str | None = None,
    token: str | None = None,
    db: str | Path | None = None,
    project: str | None = None,
    actor: str | None = None,
) -> TlApp:
    """The app for the options, falling back to the environment, then to the defaults.

    ``TL_REMOTE`` and ``TL_TOKEN`` select remote mode. Raises ``ValueError`` for a remote URL
    without a token or a URL that is not http(s).
    """
    url = remote or os.environ.get("TL_REMOTE") or None
    proj = project or os.environ.get("TL_PROJECT", DEFAULT_PROJECT)
    if url is None:
        return build_app(db or os.environ.get("TL_DB", DEFAULT_DB), proj)
    secret = token or os.environ.get("TL_TOKEN")
    if not secret:
        raise ValueError("remote mode needs a dev token: pass --token or set TL_TOKEN")
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"--remote must be an http(s) URL, got {url!r}")
    return build_remote_app(url, secret, proj, actor=actor or DEFAULT_ACTOR)


def run(
    *,
    remote: str | None = None,
    token: str | None = None,
    db: str | Path | None = None,
    project: str | None = None,
    actor: str | None = None,
) -> None:
    """Build the app for the options, run it, and release the client afterwards."""
    app = make_app(remote=remote, token=token, db=db, project=project, actor=actor)
    try:
        app.run()
    finally:
        close = getattr(app.client, "close", None)
        if callable(close):
            close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tl-tui", description="Throughline terminal UI.")
    parser.add_argument("--remote", metavar="URL", help="API server URL (default: embedded)")
    parser.add_argument(
        "--token",
        help="dev token for --remote; prefer TL_TOKEN (command-line arguments are visible in ps)",
    )
    parser.add_argument("--db", help=f"embedded: SQLite ledger (TL_DB, default {DEFAULT_DB})")
    parser.add_argument("--project", help=f"project id (TL_PROJECT, default {DEFAULT_PROJECT})")
    parser.add_argument("--actor", help="remote: the name the header shows")
    ns = parser.parse_args(argv)
    try:
        run(remote=ns.remote, token=ns.token, db=ns.db, project=ns.project, actor=ns.actor)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
