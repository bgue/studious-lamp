"""Seeding and bootstrap (ADR-0009 sections 8 and 9): the demo account and the first admin."""

from __future__ import annotations

import logging

from sqlalchemy import text

from tl_core.auth import password as pw
from tl_core.auth._time import Clock
from tl_core.auth.accounts import change_password, create_account_unchecked
from tl_core.auth.env import demo_allowed
from tl_core.auth.errors import AccountStateError, InvalidAccountError
from tl_core.auth.names import check_username
from tl_core.auth.queries import find_account
from tl_core.auth.sessions import UowFactory
from tl_core.auth.types import DEMO_PASSWORD, DEMO_USERNAME, AccountView
from tl_core.util import utcnow

log = logging.getLogger("tl_core.auth")

SEED_ACTOR = "svc:seed"
BOOTSTRAP_ACTOR = "svc:bootstrap"
DEMO_WARNING = (
    "the demo account (demo/demo) exists and is enabled: this is a dev or demo setup. "
    "Disable it with `tl admin user disable demo` before any real use"
)


def seed_demo(uow_factory: UowFactory, *, env: str, clock: Clock = utcnow) -> AccountView | None:
    """Create ``demo``/``demo`` (role ``admin``) when ``env`` is dev, demo or test; else do nothing.

    Idempotent: an existing ``demo`` account is returned untouched (its password and status stay).
    The documented password skips the password policy; nothing else does.
    """
    if not demo_allowed(env):
        return None
    with uow_factory() as uow:
        existing = find_account(uow.conn(), username=DEMO_USERNAME)
        if existing is not None:
            return existing
        return create_account_unchecked(
            uow,
            username=DEMO_USERNAME,
            display_name="Demo User",
            kind="person",
            roles=["admin"],
            password=DEMO_PASSWORD,
            by=SEED_ACTOR,
            enforce_policy=False,
            clock=clock,
        )


def bootstrap_admin(
    uow_factory: UowFactory,
    *,
    username: str,
    password: str,
    display_name: str | None = None,
    clock: Clock = utcnow,
) -> AccountView:
    """Create the first admin, or give an existing admin a password; local access only.

    Allowed only while no active admin has a password (a new database, or a restore that left
    accounts without passwords). With an existing admin of that name it sets the password and
    clears the lock; with a new name it creates the account. Anything else is refused.
    """
    name = check_username(username)
    with uow_factory() as uow:
        conn = uow.conn()
        usable = conn.execute(
            text(
                "SELECT COUNT(*) FROM cur_account a JOIN auth_credential c "
                "ON c.account_id = a.account_id WHERE a.is_admin = 1 AND a.status = 'active'"
            )
        ).scalar_one()
        if int(usable) > 0:
            raise AccountStateError(
                "an admin with a password exists already; sign in and use `tl admin user ...`"
            )
        existing = find_account(conn, username=name)
        if existing is None:
            return create_account_unchecked(
                uow,
                username=name,
                display_name=display_name or name,
                kind="person",
                roles=["admin"],
                password=password,
                by=BOOTSTRAP_ACTOR,
                enforce_policy=True,
                clock=clock,
            )
        if existing.kind != "person" or "admin" not in existing.roles:
            raise InvalidAccountError(f"{name!r} is not a person account with the admin role")
        if existing.status != "active":
            raise AccountStateError(f"{name!r} is disabled; enable it first")
        pw.check_policy(password, username=name)
        change_password(
            uow,
            account_id=existing.account_id,
            new_password=password,
            by=BOOTSTRAP_ACTOR,
            clock=clock,
            forced=True,
        )
        return existing.model_copy(update={"locked_until": None})
