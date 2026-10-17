"""Helpers shared by the `tl xer` and `tl cost` CLI tests (unique name on purpose: L-P1-I0A-1).

``Cast`` signs three people in to one ledger, each with a session file of their own: `boss`
(admin), `dora` (user and document controller) and `ursula` (user). The module that uses it sets
``AUTO_SIGN_IN = False`` and runs on both adapters. ``xer_env`` gives an initialised ledger whose
object store is under ``tmp_path``; ``xer_file`` writes one of the synthetic files of
``tl_xer.synth`` (no real project data).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest
from doccli_support import docs_env
from tl_adapters.db import DbTarget, as_target
from tl_cli import session
from tl_cli.main import app
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_xer.synth import make_xer, week_pair
from typer.testing import CliRunner
from typer.testing import Result as RunResult

PASSWORD = "correct horse battery"
GATE = "needs the document_controller or admin role"
runner = CliRunner()
P = ("--project", "P123")


def xer_env(
    new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, str]:
    values = docs_env(new_db, monkeypatch)
    values["TL_OBJECT_ROOT"] = str(tmp_path / "objects")
    return values


def xer_file(tmp_path: Path, which: int = 0, name: str | None = None) -> Path:
    """The first (0) or second (1) demo file: data dates 2026-10-05 and 2026-10-12."""
    path = tmp_path / (name or f"update-{which + 1}.xer")
    path.write_bytes(make_xer(week_pair()[which]))
    return path


class Cast:
    """`env` per person: the same ledger, a session file of their own."""

    def __init__(self, env: dict[str, str], tmp_path: Path) -> None:
        self.base = env
        self.target = as_target(env["TL_DB"])
        with mock.patch.dict(os.environ, env):
            backend = session.open_backend(self.target)
            with backend() as uow:
                for name, roles in (
                    ("boss", ["admin"]),
                    ("dora", ["user", "document_controller"]),
                    ("ursula", ["user"]),
                ):
                    accounts.create_account(
                        uow, username=name, display_name=name.title(), kind="person",
                        roles=roles, password=prepare_password(PASSWORD, username=name),
                        by="svc:test",
                    )  # fmt: skip
        self.boss = self._sign_in("boss", tmp_path)
        self.dora = self._sign_in("dora", tmp_path)
        self.ursula = self._sign_in("ursula", tmp_path)

    def _sign_in(self, name: str, tmp_path: Path) -> dict[str, str]:
        mine = self.base | {"TL_SESSION_FILE": str(tmp_path / f"session-{name}.json")}
        with mock.patch.dict(os.environ, mine):
            backend = session.open_backend(self.target)
            principal, token = sessions.sign_in(backend, username=name, password=PASSWORD)
            session.save(
                session.StoredSession(
                    target=session.db_target(self.target),
                    username=name,
                    actor=principal.actor,
                    expires_at=session.expires_at_from(sessions.SESSION_TTL),
                    token=token,
                )
            )
        return mine


def tl(who: dict[str, str], *args: str, ok: bool | None = None) -> RunResult:
    result = runner.invoke(app, list(args), env=who)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    if ok is not None:
        assert (result.exit_code == 0) is ok, result.output
    return result
