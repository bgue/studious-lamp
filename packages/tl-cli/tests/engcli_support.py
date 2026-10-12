"""Helpers shared by the engineering CLI tests (`tl standards`, `tl tag ...`; P1-I1).

The name is unique on purpose (L-P1-I0A-1). ``admin_env`` gives an initialised ledger with an admin
signed in: on SQLite the helper bootstraps ``root`` and signs in; on Postgres the conftest signs
the test account in on the first command. ``ordinary_env`` adds a second, non-admin person with a
session of their own (SQLite only; the Postgres conftest signs every test command in as an admin).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from auth_support import GOOD, bootstrap, separate_session, sign_in
from auth_support import run as tl
from tl_adapters.db import DbTarget, is_postgres, open_uow
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.loader import load_standards

ROOT = Path(__file__).resolve().parents[3]
ACME = ROOT / "schema" / "fixtures" / "standards" / "co.acme.standards@1.0.0.yaml"


def admin_env(new_db: Callable[[], DbTarget]) -> dict[str, str]:
    """An initialised ledger of the adapter under test with an admin signed in."""
    target = new_db()
    values = {"TL_DB": str(target), "TL_ENV": "dev"}
    assert tl(values, "init").exit_code == 0
    if not is_postgres(target):
        assert bootstrap(values).exit_code == 0
        sign_in(values)
    return values


def ordinary_env(env: dict[str, str], tmp_path: Path, name: str = "amy") -> dict[str, str]:
    """``env`` with its own session file, signed in as the non-admin person ``name``."""
    assert tl(env, "admin", "user", "add", name, "--password-stdin", stdin=GOOD).exit_code == 0
    mine = separate_session(env, tmp_path, name)
    sign_in(mine, name)
    return mine


def count(env: dict[str, str], table: str = "events") -> int:
    """Rows of ``table`` in a SQLite ledger (a quick way to see that nothing was written)."""
    with sqlite3.connect(env["TL_DB"]) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def load_acme(env: dict[str, str]) -> None:
    """Load the acme standards into ``env``'s ledger through the module (not the CLI)."""
    from tl_adapters.db import as_target

    with open_uow(as_target(env["TL_DB"])) as uow:
        load_standards(uow, load_standards_file(ACME), actor="user:seed", source="test")
