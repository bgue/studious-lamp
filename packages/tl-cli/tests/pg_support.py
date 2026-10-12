"""Helpers for CLI tests that run on Postgres as well as SQLite (P1-I0 workstream B).

On a Postgres ledger the conftest signs a test account in (a server target needs a session), and an
account is an event of the ledger, so a test that counts events or names a ``seq`` must allow for
them: ``account_events`` says how many there are. An agent cannot be the signed-in user, so a test
that needs a named actor of the kind ``agent:`` uses ``person_or_agent``.
"""

from __future__ import annotations

from sqlalchemy import text
from tl_adapters.db import is_postgres, open_uow


def account_events(env: dict[str, str]) -> int:
    """How many ``Account.*`` events the ledger of ``env`` holds (none on a fresh SQLite file)."""
    with open_uow(env["TL_DB"], readonly=True) as uow:
        found = uow.conn().execute(
            text("SELECT COUNT(*) FROM events WHERE event_type LIKE 'Account.%'")
        )
        return int(found.scalar_one())


def person_or_agent(env: dict[str, str], agent: str) -> str:
    """``agent`` on a ledger file; on a server, where only a person is signed in, ``user:<name>``.

    The test keeps its point (a named actor is recorded) on both; a server refuses an agent here by
    design (ADR-0009 section 7), which ``test_cli_auth_targets.py`` covers.
    """
    if not is_postgres(env["TL_DB"]):
        return agent
    return "user:" + agent.partition(":")[2]
