"""Helpers for the authentication tests: a movable clock and a small world over a real ledger.

The conftest next to this file puts the directory on ``sys.path`` so tests can write
``from authworld import World`` (pytest runs in importlib mode; pyright finds it via extraPaths).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_core.auth.types import AccountKind, AccountView

GOOD = "correct horse battery"
OTHER = "another long passphrase"


class MovingClock:
    """The real clock plus an offset, so it never falls behind what the ledger stamps."""

    def __init__(self) -> None:
        self.offset = timedelta(0)

    def __call__(self) -> datetime:
        return datetime.now(UTC) + self.offset

    def advance(self, **kwargs: float) -> None:
        self.offset += timedelta(**kwargs)


@dataclass
class World:
    db: str | Path
    factory: Any
    clock: MovingClock
    log: list[str] = field(default_factory=list[str])

    def create(
        self,
        username: str,
        *,
        roles: tuple[str, ...] = ("user",),
        kind: AccountKind = "person",
        password: str | None = GOOD,
        by: str = "user:root",
    ) -> AccountView:
        if kind == "agent":
            password = None
        # policy and hash happen before the write transaction, as in production
        prepared = None if password is None else prepare_password(password, username=username)
        with self.factory() as uow:
            return accounts.create_account(
                uow,
                username=username,
                display_name=username.title(),
                kind=kind,
                roles=list(roles),
                password=prepared,
                by=by,
                clock=self.clock,
            )

    def admin(self, username: str = "root", password: str = GOOD) -> AccountView:
        return self.create(username, roles=("admin",), password=password)

    def sign_in(self, username: str, password: str = GOOD) -> tuple[Any, str]:
        return sessions.sign_in(
            self.factory, username=username, password=password, clock=self.clock
        )

    def rows(self, sql: str, **params: Any) -> list[tuple[Any, ...]]:
        with self.factory(readonly=True) as uow:
            return [tuple(r) for r in uow.conn().execute(text(sql), params).all()]

    def events(self) -> list[tuple[str, str, str, str]]:
        """(event_type, stream_id, actor, payload text) of every ledger event."""
        return [
            (str(a), str(b), str(c), str(d))
            for a, b, c, d in self.rows(
                "SELECT event_type, stream_id, actor, payload FROM events ORDER BY seq"
            )
        ]
