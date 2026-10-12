"""The simulator's agent: an account and a token made on the dev ledger (P1-I0-T11, ADR-0009).

The simulated assistant proposes over MCP, and the MCP server only starts with an agent token
(``TL_AGENT_TOKEN``). Under ``tl sim`` on a local ledger file in a dev setup this module makes the
agent account ``sim-assistant`` and a short-lived token for it, as the local operator (``svc:sim``),
the way ``tl init --dev`` makes the demo account. An agent may hold 20 live tokens, so each run
first revokes the expired ones and then the oldest while ``KEEP`` or more remain: up to ``KEEP``
runs at once keep their tokens, and the ledger never fills up. Outside a dev setup it makes nothing
and ``issue_token`` refuses: ``TL_SIM_AGENT_TOKEN`` (a token an admin issued) is the only way in
there.

**A Postgres ledger is not a file the operator owns** (ADR-0009 section 7 and the P1-I0 workstream
B addendum), so ``TL_ENV=dev`` alone does not let anyone mint a token there. ``provider`` answers
``None`` and ``issue_token`` refuses (`error: not signed in`) unless a signed-in **admin** session
exists for that ledger (``tl login``); then the account and the token are made as, and attributed
to, that admin. Without one the simulator stops with its usual "no agent token" line, and
``TL_SIM_AGENT_TOKEN`` is the way in.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from tl_adapters.backend import ledger_exists
from tl_adapters.db import DbTarget, is_postgres
from tl_core.auth import accounts, queries
from tl_core.auth.env import current_env, demo_allowed
from tl_core.auth.errors import ForbiddenError, InvalidAccountError
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow

from tl_cli.session import current_principal, open_backend, require_admin

SIM_AGENT = "sim-assistant"
SIM_ACTOR = "svc:sim"
TOKEN_DAYS = 2
KEEP = 10  # live tokens kept: concurrent runs do not revoke each other below this


def issue_token(db: DbTarget) -> str:
    """Make sure ``sim-assistant`` exists, thin out its old tokens and return a new one.

    Only in a dev, demo or test environment (``ForbiddenError`` elsewhere), whoever calls it. On a
    Postgres ledger also only with a signed-in admin session (`error: not signed in`, or `forbidden`
    for a user), and the work is attributed to that admin instead of ``svc:sim``.
    """
    if not demo_allowed(current_env()):
        raise ForbiddenError(
            "the simulator makes its agent only where TL_ENV is dev, demo or test; "
            "set TL_SIM_AGENT_TOKEN to a token an admin issued"
        )
    by = require_admin(db).actor if is_postgres(db) else SIM_ACTOR
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
                by=by,
            )
        elif agent.kind != "agent":
            raise InvalidAccountError(
                f"the account {SIM_AGENT!r} exists but is a {agent.kind} account, not an agent: "
                f"rename or remove it so the simulator can make its agent"
            )
        now = utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        live = queries.list_agent_tokens(
            uow.conn(), account_id=agent.account_id, include_revoked=False
        )  # oldest first
        fresh = [t for t in live if t.expires_at is None or t.expires_at > now]
        for old in live:
            if old not in fresh:
                _revoke(uow, old.token_id, "expired", by)
        while len(fresh) >= KEEP:
            _revoke(uow, fresh.pop(0).token_id, "replaced by newer runs", by)
        _, token = accounts.issue_agent_token(
            uow,
            account_id=agent.account_id,
            label="simulator",
            expires_at=utcnow() + timedelta(days=TOKEN_DAYS),
            by=by,
        )
    return token


def _revoke(uow: UnitOfWork, token_id: str, reason: str, by: str) -> None:
    accounts.revoke_agent_token(uow, token_id=token_id, by=by, reason=reason)


def provider(db: DbTarget) -> Callable[[], str] | None:
    """A function that makes the token on first use, or ``None`` outside a dev setup.

    On a Postgres ledger it is also ``None`` unless an admin is signed in to that ledger.
    """
    if not demo_allowed(current_env()) or not ledger_exists(db):
        return None
    if is_postgres(db):
        who = current_principal(db)
        if who is None or not who.is_admin:
            return None
    made: list[str] = []

    def token() -> str:
        if not made:
            made.append(issue_token(db))
        return made[0]

    return token
