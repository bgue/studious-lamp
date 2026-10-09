"""Static dev tokens (ADR-0005): a local JSON file that maps bearer token to actor.

This is an identity stub, not an authentication system. The file is ``{"<token>": "<actor>"}``
with actors like ``user:alice`` or ``agent:triage``. ``tl dev token add`` creates tokens. The
file is re-read when it changes, so a new token works without a restart.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import threading
from pathlib import Path

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
    entries = _read(target)
    token = secrets.token_urlsafe(24)
    entries[token] = actor
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = target.with_name(target.name + ".tmp")
    fd = os.open(scratch, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(entries, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(scratch, target)
    return token


def _read(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
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
                except (ValueError, OSError):
                    self._entries = {}
                self._stamp = stamp
            return self._entries
