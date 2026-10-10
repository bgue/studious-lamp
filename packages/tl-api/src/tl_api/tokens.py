"""Static dev tokens (ADR-0005): a local JSON file that maps bearer token to actor.

This is an identity stub, not an authentication system. The file is ``{"<token>": "<actor>"}``
with actors like ``user:alice`` or ``agent:triage``. ``tl dev token add`` creates tokens. The
file is re-read when it changes, so a new token works without a restart.
"""

from __future__ import annotations

import fcntl
import hmac
import json
import logging
import os
import re
import secrets
import stat
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger("tl_api")

ACTOR_PATTERN = re.compile(r"(?:user|agent):[A-Za-z0-9][A-Za-z0-9_.@-]*")


def check_actor(actor: str) -> str:
    """The actor when it is ``user:<id>`` or ``agent:<id>``, else ``ValueError``."""
    if ACTOR_PATTERN.fullmatch(actor) is None:
        raise ValueError(f"actor must look like 'user:<id>' or 'agent:<id>', got {actor!r}")
    return actor


def add_token(path: str | Path, actor: str) -> str:
    """Create a token for ``actor`` in the file at ``path`` (mode 0600) and return it."""
    check_actor(actor)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _locked(target):  # concurrent callers (threads or processes) each keep their token
        entries = _read(target)
        token = secrets.token_urlsafe(24)
        entries[token] = actor
        scratch = target.with_name(f"{target.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        fd = os.open(scratch, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(entries, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(scratch, target)
        finally:
            scratch.unlink(missing_ok=True)
    return token


@contextmanager
def _locked(target: Path) -> Iterator[None]:
    """Hold an exclusive ``flock`` on ``<file>.lock`` (the data file is replaced by rename)."""
    lock = target.with_name(target.name + ".lock")
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # closing releases the lock


def check_private(path: Path) -> None:
    """Raise ``ValueError`` when the token file is readable or writable by group or others."""
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError(
            f"{path} has mode {mode:04o}: tokens are credentials, so it must not be accessible by "
            f"group or others; run `chmod 600 {path}`"
        )


def _read(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    check_private(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must hold a JSON object of token to actor")
    entries: dict[str, str] = {}
    for token, actor in data.items():  # pyright: ignore[reportUnknownVariableType]
        if isinstance(token, str) and isinstance(actor, str):
            entries[token] = actor
    return entries


class TokenStore:
    """Looks tokens up in the file; reloads it when its modification time changes."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._stamp: tuple[int, int] | None = None
        self._entries: dict[str, str] = {}

    def check(self) -> None:
        """Raise ``ValueError`` if the file exists and is accessible by group or others."""
        if self._path.exists():
            check_private(self._path)

    def actor_for(self, token: str) -> str | None:
        """The actor that owns ``token``, or ``None``. The comparison is constant-time per entry."""
        entries = self._current()
        probe = token.encode()
        found: str | None = None
        for known, actor in entries.items():
            if hmac.compare_digest(probe, known.encode()):
                found = actor
        return found

    def _current(self) -> dict[str, str]:
        try:
            stat = self._path.stat()
            stamp: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            stamp = None
        with self._lock:
            if stamp != self._stamp:
                try:
                    self._entries = _read(self._path) if stamp is not None else {}
                except (ValueError, OSError) as exc:
                    log.error("token file refused, nobody can authenticate: %s", exc)
                    self._entries = {}
                self._stamp = stamp
            return self._entries
