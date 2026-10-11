"""Seeding and bootstrap (ADR-0009 sections 8, 9 and 12): the demo account and local recovery."""

from __future__ import annotations

import logging

from sqlalchemy import text

from tl_core.auth import audit
from tl_core.auth import password as pw
from tl_core.auth._time import Clock
from tl_core.auth.accounts import change_password, create_account
from tl_core.auth.env import demo_allowed
from tl_core.auth.errors import AccountStateError, InvalidAccountError
from tl_core.auth.names import check_username, username_key
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
    The documented password skips the password policy; nothing else does. The hash is made before
    the write transaction opens.
    """
    if not demo_allowed(env):
        return None
    with uow_factory(readonly=True) as uow:
        existing = find_account(uow.conn(), username=DEMO_USERNAME)
    if existing is not None:
        return existing
    prepared = pw.prepare_password(DEMO_PASSWORD, enforce_policy=False)
    with uow_factory() as uow:
        existing = find_account(uow.conn(), username=DEMO_USERNAME)  # another seed won the race
        if existing is not None:
            return existing
        return create_account(
            uow,
            username=DEMO_USERNAME,
            display_name="Demo User",
            kind="person",
            roles=["admin"],
            password=prepared,
            by=SEED_ACTOR,
            clock=clock,
            allow_demo=True,
        )


def bootstrap_admin(
    uow_factory: UowFactory,
    *,
    username: str,
    password: str,
    display_name: str | None = None,
    clock: Clock = utcnow,
) -> AccountView:
    """Local recovery: create the first admin, or reset an existing admin's password and lock.

    Local access only (the CLI on a database it can open; there is no API route). With the name of
    an existing active admin it sets the password, ends the admin's sessions and clears the lock,
    whether or not other admins have passwords: this is how a locked-out sole admin gets back in.
    With a new name it creates an admin, but only while no active admin has a password (a new
    database, or a restore that left accounts without passwords); otherwise add users with
    ``tl admin user add``. Anything else is refused.
    """
    name = check_username(username)
    prepared = pw.prepare_password(password, username=name)  # policy and hash, before the write
    with uow_factory() as uow:
        conn = uow.conn()
        existing = find_account(conn, username=name)
        if existing is None:
            usable = conn.execute(
                text(
                    "SELECT COUNT(*) FROM cur_account a JOIN auth_credential c "
                    "ON c.account_id = a.account_id WHERE a.is_admin = 1 AND a.status = 'active'"
                )
            ).scalar_one()
            if int(usable) > 0:
                raise AccountStateError(
                    "an admin with a password exists already; sign in and use `tl admin user add`"
                )
            view = create_account(
                uow,
                username=name,
                display_name=display_name or name,
                kind="person",
                roles=["admin"],
                password=prepared,
                by=BOOTSTRAP_ACTOR,
                clock=clock,
            )
            audit.record(
                conn, "bootstrap", now=clock(), username_key=username_key(name),
                account_id=view.account_id, actor=BOOTSTRAP_ACTOR, detail="created",
            )  # fmt: skip
            return view
        if existing.kind != "person" or "admin" not in existing.roles:
            raise InvalidAccountError(f"{name!r} is not a person account with the admin role")
        if existing.status != "active":
            raise AccountStateError(f"{name!r} is disabled; enable it first")
        change_password(
            uow,
            account_id=existing.account_id,
            new_password=prepared,
            by=BOOTSTRAP_ACTOR,
            clock=clock,
            forced=True,
        )
        audit.record(
            conn, "bootstrap", now=clock(), username_key=username_key(name),
            account_id=existing.account_id, actor=BOOTSTRAP_ACTOR, detail="reset",
        )  # fmt: skip
        return existing.model_copy(update={"locked_until": None})
