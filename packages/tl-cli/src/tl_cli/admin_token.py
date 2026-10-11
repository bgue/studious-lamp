"""`tl admin token ...`: list, issue and revoke agent tokens (P1-I0-T07).

Needs a signed-in admin. A new token is printed once, alone on stdout, so a script can capture it
(`TL_AGENT_TOKEN=$(tl admin token issue triage --label mcp)`); the facts about it go to stderr.

STUB (P1-I0-T07): the function bodies raise NotImplementedError; their signatures, annotations and
docstrings are final (they make the `--help` text). Each body has a STEPS comment. Implement them,
then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
from __future__ import annotations

from datetime import timedelta
from typing import Annotated

import typer
from tl_core.auth import accounts, queries
from tl_core.util import utcnow

from tl_cli.admin import backend_of, find_account
from tl_cli.session import fail, require_admin, service_errors

app = typer.Typer(help="Agent tokens: list, issue, revoke.", no_args_is_help=True)

DEFAULT_DAYS = 90

# Every command starts: admin = require_admin(ctx.obj); backend = backend_of(ctx). Service calls
# run inside `with service_errors():` (service failures become `error: <message>`, exit 1). Do not
# catch exceptions yourself. Never print a token except in `issue`, and never log one.


@app.command("ls")
def ls(
    ctx: typer.Context,
    user: Annotated[str | None, typer.Option("--user", help="Only this agent.")] = None,
    show_all: Annotated[bool, typer.Option("--all", help="Include revoked tokens.")] = False,
) -> None:
    """List agent tokens: id, agent, label, expiry, state. The tokens themselves are not stored."""
    # STEPS
    # 1. require_admin(ctx.obj); backend = backend_of(ctx).
    # 2. Inside `with service_errors():` owner = None if user is None else
    #    find_account(backend, user).account_id; then `with backend(readonly=True) as uow:`
    #    names = {a.account_id: a.username for a in queries.list_accounts(uow.conn())} and
    #    tokens = queries.list_agent_tokens(uow.conn(), account_id=owner, include_revoked=show_all).
    # 3. now = utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"). For each token: state is "revoked" if
    #    token.revoked, else "expired" if token.expires_at is not None and token.expires_at <= now,
    #    else "active". expires = token.expires_at or "never".
    # 4. typer.echo(f"{token.token_id}  {names.get(token.account_id, '?')}  {token.label}  "
    #    f"{expires}  {state}")  -- two spaces between fields.
    raise NotImplementedError


@app.command("issue")
def issue(
    ctx: typer.Context,
    username: Annotated[str, typer.Argument(help="The agent account's username.")],
    label: Annotated[str, typer.Option("--label", help="What the token is for.")],
    days: Annotated[
        int, typer.Option("--days", min=1, max=3650, help="Days until it expires.")
    ] = DEFAULT_DAYS,
    no_expiry: Annotated[
        bool, typer.Option("--no-expiry", help="A token that never expires.")
    ] = False,
) -> None:
    """Issue a token for an agent account. It is printed once and cannot be read back."""
    # STEPS
    # 1. admin = require_admin(ctx.obj); backend = backend_of(ctx).
    # 2. If no_expiry and days != DEFAULT_DAYS: fail("use --days or --no-expiry, not both").
    # 3. expires = None if no_expiry else utcnow() + timedelta(days=days).
    # 4. Inside `with service_errors():` target = find_account(backend, username); then
    #    `with backend() as uow:` view, token = accounts.issue_agent_token(uow,
    #    account_id=target.account_id, label=label, expires_at=expires, by=admin.actor).
    # 5. After the block: typer.echo(token)  (stdout, alone on its line), then
    #    typer.echo(f"issued token {view.token_id} for agent:{target.username}, expires "
    #    f"{view.expires_at or 'never'}; this is the only time it is shown", err=True).
    raise NotImplementedError


@app.command("revoke")
def revoke(
    ctx: typer.Context,
    token_id: Annotated[str, typer.Argument(help="The token id from `tl admin token ls`.")],
    reason: Annotated[str | None, typer.Option("--reason", help="Why.")] = None,
) -> None:
    """Revoke a token at once."""
    # STEPS
    # 1. admin = require_admin(ctx.obj); backend = backend_of(ctx).
    # 2. `with service_errors(), backend() as uow:` accounts.revoke_agent_token(uow,
    #    token_id=token_id, by=admin.actor, reason=reason).
    # 3. typer.echo(f"revoked {token_id}").
    raise NotImplementedError
