"""The CLI's signed-in session: where it is kept, who it names, what needs one (ADR-0009 sec. 4).

``tl login`` stores the opaque session token in a file readable by its owner only
(``TL_SESSION_FILE``, default ``~/.config/throughline/session.json``). The file holds one entry per
target, so one person can be signed in to a ledger file (``db:<path>``) and to a server
(``api:<url>``) at once. The token is never printed, logged or put in an exception text.

An embedded command takes its default ``--actor`` from the session of the ledger it opens
(``actor_hook``). Where there is no session the default is ``user:dev`` in ``TL_ENV`` dev, test
or ci and an error everywhere else. An explicit ``--actor`` is still honoured: whoever runs
``tl`` on a ledger file can edit the file (the embedded trust boundary, ADR-0009 sec. 14).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import NoReturn

import typer
from tl_adapters.sqlite.uow import open_uow
from tl_core.auth import sessions
from tl_core.auth.env import dev_tokens_allowed
from tl_core.auth.errors import AccountLockedError, InvalidCredentialsError, WeakPasswordError
from tl_core.auth.sessions import UowFactory
from tl_core.auth.types import Principal
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow

SESSION_FILE_ENV = "TL_SESSION_FILE"
DEV_ACTOR = "user:dev"
SIGN_IN_HINT = "run `tl login <username>`"
_VERSION = 1


class SessionFileError(Exception):
    """The session file cannot be used (unreadable, damaged, or open to other users)."""


@dataclass(frozen=True)
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


def api_target(url: str) -> str:
    """The target name of a server: ``api:`` and its base URL without a trailing slash."""
    return f"api:{url.strip().rstrip('/')}"


def session_file() -> Path:
    named = os.environ.get(SESSION_FILE_ENV, "").strip()
    if named:
        return Path(named).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME", "").strip()
    root = Path(base) if base else Path.home() / ".config"
    return root / "throughline" / "session.json"


def _read_all(path: Path) -> dict[str, dict[str, str]]:
    try:
        info = path.stat()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise SessionFileError(f"cannot read the session file {path}: {exc.strerror}") from exc
    if os.name == "posix" and info.st_mode & 0o077:
        raise SessionFileError(
            f"the session file {path} can be read by other users; run `chmod 600 {path}` "
            f"or delete it and sign in again"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        sessions_map = data["sessions"]
        if data["version"] != _VERSION or not isinstance(sessions_map, dict):
            raise ValueError("version")
        return {str(k): dict(v) for k, v in sessions_map.items()}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SessionFileError(
            f"the session file {path} is damaged; delete it and sign in again"
        ) from exc


def _write_all(path: Path, entries: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(temp, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"version": _VERSION, "sessions": entries}, handle, indent=2)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def save(stored: StoredSession) -> None:
    """Store (or replace) the session of ``stored.target`` in the session file, mode 0600."""
    path = session_file()
    entries = _read_all(path)
    entries[stored.target] = {
        "username": stored.username,
        "actor": stored.actor,
        "expires_at": stored.expires_at,
        "token": stored.token,
    }
    _write_all(path, entries)


def load(target: str) -> StoredSession | None:
    """The stored session of ``target``, or None when there is none or it has run out."""
    entry = _read_all(session_file()).get(target)
    if entry is None:
        return None
    try:
        stored = StoredSession(
            target=target,
            username=entry["username"],
            actor=entry["actor"],
            expires_at=entry["expires_at"],
            token=entry["token"],
        )
    except KeyError as exc:
        raise SessionFileError("the session file is damaged; delete it and sign in again") from exc
    return None if stored.expired() else stored


def forget(target: str) -> StoredSession | None:
    """Remove the session of ``target`` and return it (even an expired one), or None."""
    path = session_file()
    entries = _read_all(path)
    entry = entries.pop(target, None)
    if entry is None:
        return None
    if entries:
        _write_all(path, entries)
    else:
        path.unlink(missing_ok=True)
    return StoredSession(
        target=target,
        username=entry.get("username", ""),
        actor=entry.get("actor", ""),
        expires_at=entry.get("expires_at", ""),
        token=entry.get("token", ""),
    )


# --- using the ledger ------------------------------------------------------------------------


def open_backend(db: Path) -> UowFactory:
    """A unit-of-work factory for the ledger file ``db`` (the account services take one)."""

    def factory(readonly: bool = False) -> AbstractContextManager[UnitOfWork]:
        return open_uow(db, readonly=readonly)

    return factory


def fail(message: str) -> NoReturn:
    """Print ``error: <message>`` on stderr and exit 1 (the CLI convention)."""
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def service_errors() -> Iterator[None]:
    """Turn account-service failures into `error:` lines on stderr and exit 1.

    A weak password lists the broken rules; a lock names the time it ends. Nothing printed holds a
    password or a token.
    """
    try:
        yield
    except WeakPasswordError as exc:
        typer.echo(f"error: {exc}", err=True)
        for issue in exc.issues:
            typer.echo(f"  - {issue}", err=True)
        raise typer.Exit(code=1) from exc
    except AccountLockedError as exc:
        until = f" until {exc.locked_until}" if exc.locked_until else ""
        fail(f"{exc}; the account is locked{until}")
    except (ServiceError, ConcurrencyError) as exc:
        fail(str(exc))


def current_principal(db: Path) -> Principal | None:
    """Who the stored session of ``db`` names, checked against the ledger; None if none is valid.

    A session the ledger no longer knows (ended, disabled, expired) is not an error here: the caller
    decides what an absent session means.
    """
    try:
        stored = load(db_target(db))
    except SessionFileError as exc:
        typer.echo(f"warning: {exc}", err=True)
        return None
    if stored is None or not db.is_file():
        return None
    try:
        return sessions.principal_for_bearer(open_backend(db), stored.token)
    except InvalidCredentialsError:
        return None


def default_actor(db: Path) -> str:
    """The default ``--actor``: the session's, else ``user:dev`` in dev, test or ci, else error."""
    principal = current_principal(db)
    if principal is not None:
        return principal.actor
    if dev_tokens_allowed():
        return DEV_ACTOR
    fail(f"not signed in: {SIGN_IN_HINT}, or pass --actor")


def require_session(db: Path) -> Principal:
    """The signed-in principal of ``db``, or `error: not signed in` and exit 1."""
    principal = current_principal(db)
    if principal is None:
        fail(f"not signed in: {SIGN_IN_HINT}")
    return principal


def require_admin(db: Path) -> Principal:
    """Like :func:`require_session`, and the principal must hold the admin role."""
    principal = require_session(db)
    if not principal.is_admin:
        fail("forbidden: this command needs the admin role")
    return principal
