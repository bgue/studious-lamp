"""The simulator's agent: an account and a token made on the dev ledger (P1-I0-T11, ADR-0009).

The simulated assistant proposes over MCP, and the MCP server only starts with an agent token
(``TL_AGENT_TOKEN``). Under ``tl sim`` the ledger is a local file in a dev setup, so this module
makes the agent account ``sim-assistant`` and a short-lived token for it, as the local operator
(``svc:sim``), the way ``tl init --dev`` makes the demo account. Each run revokes the tokens of the
earlier ones (an agent may hold 20), so the ledger keeps one live token. Outside a dev setup it
makes nothing: ``TL_SIM_AGENT_TOKEN`` (a token an admin issued) is the only way in there.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from tl_core.auth import accounts, queries
from tl_core.auth.env import current_env, demo_allowed
from tl_core.util import utcnow

from tl_cli.session import open_backend

SIM_AGENT = "sim-assistant"
SIM_ACTOR = "svc:sim"
TOKEN_DAYS = 2


def issue_token(db: Path) -> str:
    """Make sure ``sim-assistant`` exists, revoke its live tokens and return a new one."""
    backend = open_backend(db)
    with backend() as uow:
        agent = queries.find_account(uow.conn(), username=SIM_AGENT)
        if agent is None:
            agent = accounts.create_account(
                uow,
                username=SIM_AGENT,
                display_name="Simulated assistant",
                kind="agent",
                roles=["user"],
                password=None,
                by=SIM_ACTOR,
            )
        for old in queries.list_agent_tokens(
            uow.conn(), account_id=agent.account_id, include_revoked=False
        ):
            accounts.revoke_agent_token(
                uow, token_id=old.token_id, by=SIM_ACTOR, reason="replaced by a new run"
            )
        _, token = accounts.issue_agent_token(
            uow,
            account_id=agent.account_id,
            label="simulator",
            expires_at=utcnow() + timedelta(days=TOKEN_DAYS),
            by=SIM_ACTOR,
        )
    return token


def provider(db: Path) -> Callable[[], str] | None:
    """A function that makes the token on first use, or ``None`` outside a dev setup."""
    if not demo_allowed(current_env()) or not db.is_file():
        return None
    made: list[str] = []

    def token() -> str:
        if not made:
            made.append(issue_token(db))
        return made[0]

    return token
