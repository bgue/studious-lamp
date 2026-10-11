"""Account services (ADR-0009): create, roles, disable and enable, passwords, agent tokens.

Every function takes an entered ``UnitOfWork`` and writes in it, so the ledger event and the
operational rows commit together or not at all. Events carry metadata only: a password, a hash or a
token never appears in a payload, a message or a log line. Authorization (who may call these) is
the caller's: routes run the ``Authorizer`` for ``admin.*`` first, and ``by`` is the trusted actor.

Roster changes (create, roles, disable) check what they need (a free username, the last active
admin) inside the unit of work. Both adapters take the ledger's single writer lock when a write
transaction begins, so two of them never interleave; ``test_two_admins_cannot_disable_each_other``
fails if that ever stops being true.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text

from tl_core.auth import password as pw
from tl_core.auth._time import Clock, iso_z
from tl_core.auth.errors import (
    AccountNotFoundError,
    AccountStateError,
    AgentTokenNotFoundError,
    InvalidAccountError,
    InvalidCredentialsError,
    LastAdminError,
    UsernameTakenError,
)
from tl_core.auth.names import (
    MAX_DISPLAY_NAME,
    MAX_LABEL,
    actor_for,
    check_text,
    check_username,
    username_key,
)
from tl_core.auth.projector import ACCOUNT_STREAM_TYPE, account_stream_id
from tl_core.auth.queries import get_account, load_roles
from tl_core.auth.tokens import new_agent_token, token_hash
from tl_core.auth.types import (
    ACCOUNT_CREATED,
    ACCOUNT_DISABLED,
    ACCOUNT_ENABLED,
    ACCOUNT_PASSWORD_CHANGED,
    ACCOUNT_ROLES_SET,
    AGENT_TOKEN_ISSUED,
    AGENT_TOKEN_REVOKED,
    AccountKind,
    AccountView,
    AgentTokenView,
    Role,
)
from tl_core.ledger import NewEvent
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

SOURCE = "auth"
MAX_ACTIVE_TOKENS_PER_AGENT = 20
ROLES: tuple[Role, ...] = ("admin", "user")


def _normalise_roles(kind: AccountKind, roles: Sequence[str]) -> list[Role]:
    unknown = sorted(set(roles) - set(ROLES))
    if unknown:
        raise InvalidAccountError(f"unknown role {', '.join(unknown)}; roles are admin and user")
    found: list[Role] = [r for r in ROLES if r in set(roles)]
    if not found:
        raise InvalidAccountError("an account needs at least one role")
    if kind != "person" and "admin" in found:
        raise InvalidAccountError(f"a {kind} account cannot hold the admin role")
    return found


def _row(conn: Connection, account_id: str) -> dict[str, Any]:
    found = (
        conn.execute(
            text(
                "SELECT account_id, username, kind, roles_json, is_admin, status, version "
                "FROM cur_account WHERE account_id = :a"
            ),
            {"a": account_id},
        )
        .mappings()
        .first()
    )
    if found is None:
        raise AccountNotFoundError(f"no account {account_id}")
    return dict(found)


def _append(
    uow: UnitOfWork,
    account_id: str,
    expected: int,
    event_type: str,
    payload: dict[str, Any],
    by: str,
) -> None:
    uow.append(
        stream_id=account_stream_id(account_id),
        stream_type=ACCOUNT_STREAM_TYPE,
        scope="company",
        expected_version=expected,
        events=[NewEvent(event_type=event_type, payload=payload)],
        actor=by,
        source=SOURCE,
        correlation_id=new_ulid(),
    )


def revoke_sessions(conn: Connection, account_id: str) -> None:
    """Sign the account out everywhere."""
    conn.execute(text("DELETE FROM auth_session WHERE account_id = :a"), {"a": account_id})


def clear_lockout(conn: Connection, username: str) -> None:
    conn.execute(
        text("DELETE FROM auth_attempt WHERE username_key = :k"), {"k": username_key(username)}
    )


def _store_credential(conn: Connection, account_id: str, password: str, now: datetime) -> None:
    stored = pw.hash_password(password)
    stamp = iso_z(now)
    changed = conn.execute(
        text(
            "UPDATE auth_credential SET password_hash = :h, updated_at = :t WHERE account_id = :a"
        ),
        {"h": stored, "t": stamp, "a": account_id},
    )
    if changed.rowcount == 0:
        conn.execute(
            text(
                "INSERT INTO auth_credential (account_id, password_hash, updated_at) "
                "VALUES (:a, :h, :t)"
            ),
            {"a": account_id, "h": stored, "t": stamp},
        )


def _last_admin_guard(conn: Connection, account: dict[str, Any], *, still_admin: bool) -> None:
    """Refuse a change that would leave no active admin (decision D4)."""
    is_active_admin = int(account["is_admin"]) == 1 and account["status"] == "active"
    if not is_active_admin or still_admin:
        return
    others = conn.execute(
        text(
            "SELECT COUNT(*) FROM cur_account WHERE is_admin = 1 AND status = 'active' "
            "AND account_id <> :a"
        ),
        {"a": account["account_id"]},
    ).scalar_one()
    if int(others) == 0:
        raise LastAdminError("the last active admin cannot be disabled or demoted")


def create_account_unchecked(
    uow: UnitOfWork,
    *,
    username: str,
    display_name: str,
    kind: AccountKind,
    roles: Sequence[str],
    password: str | None,
    by: str,
    enforce_policy: bool,
    clock: Clock = utcnow,
) -> AccountView:
    """``create_account`` with the password policy optional. Only the seeds use ``False``."""
    name = check_username(username)
    shown = check_text(display_name, what="display name", limit=MAX_DISPLAY_NAME)
    if kind not in ("person", "agent", "sim"):
        raise InvalidAccountError("kind must be person, agent or sim")
    role_list = _normalise_roles(kind, roles)
    if password is not None:
        if kind == "agent":
            raise InvalidAccountError("an agent account has no password; issue it a token")
        if enforce_policy:
            pw.check_policy(password, username=name)
    conn = uow.conn()
    taken = conn.execute(text("SELECT 1 FROM cur_account WHERE username = :u"), {"u": name}).first()
    if taken is not None:
        raise UsernameTakenError(f"the username {name!r} is taken")
    account_id = new_ulid()
    if password is not None:
        _store_credential(conn, account_id, password, clock())
    _append(
        uow,
        account_id,
        0,
        ACCOUNT_CREATED,
        {
            "account_id": account_id,
            "username": name,
            "display_name": shown,
            "kind": kind,
            "roles": role_list,
        },
        by,
    )
    return get_account(conn, account_id)


def create_account(
    uow: UnitOfWork,
    *,
    username: str,
    display_name: str,
    kind: AccountKind,
    roles: Sequence[str],
    password: str | None,
    by: str,
    clock: Clock = utcnow,
) -> AccountView:
    """Create an account. A password (never for an agent) must meet the policy."""
    return create_account_unchecked(
        uow,
        username=username,
        display_name=display_name,
        kind=kind,
        roles=roles,
        password=password,
        by=by,
        enforce_policy=True,
        clock=clock,
    )


def set_roles(
    uow: UnitOfWork, *, account_id: str, roles: Sequence[str], by: str, reason: str | None
) -> AccountView:
    conn = uow.conn()
    account = _row(conn, account_id)
    new_roles = _normalise_roles(account["kind"], roles)
    if new_roles == load_roles(account["roles_json"]):
        raise AccountStateError("the account already has these roles")
    _last_admin_guard(conn, account, still_admin="admin" in new_roles)
    _append(
        uow,
        account_id,
        int(account["version"]),
        ACCOUNT_ROLES_SET,
        {"account_id": account_id, "roles": new_roles, "reason": reason},
        by,
    )
    return get_account(conn, account_id)


def disable(uow: UnitOfWork, *, account_id: str, by: str, reason: str | None) -> AccountView:
    """Disable an account: it cannot sign in, and its sessions and agent tokens stop working."""
    conn = uow.conn()
    account = _row(conn, account_id)
    if account["status"] == "disabled":
        raise AccountStateError("the account is already disabled")
    _last_admin_guard(conn, account, still_admin=False)
    revoke_sessions(conn, account_id)
    _append(
        uow,
        account_id,
        int(account["version"]),
        ACCOUNT_DISABLED,
        {"account_id": account_id, "reason": reason},
        by,
    )
    return get_account(conn, account_id)


def enable(uow: UnitOfWork, *, account_id: str, by: str, reason: str | None) -> AccountView:
    conn = uow.conn()
    account = _row(conn, account_id)
    if account["status"] == "active":
        raise AccountStateError("the account is already active")
    _append(
        uow,
        account_id,
        int(account["version"]),
        ACCOUNT_ENABLED,
        {"account_id": account_id, "reason": reason},
        by,
    )
    return get_account(conn, account_id)


def change_password(
    uow: UnitOfWork,
    *,
    account_id: str,
    new_password: str,
    by: str,
    current_password: str | None = None,
    clock: Clock = utcnow,
    forced: bool | None = None,
) -> None:
    """Set a password. A person changing their own gives the current one; an admin reset does not.

    Every session of the account ends and its lockout clears. A wrong ``current_password`` is not
    counted towards lockout here (the exception rolls the unit of work back, counter included):
    callers acting for a signed-in person use :func:`tl_core.auth.sessions.change_own_password`.
    """
    conn = uow.conn()
    account = _row(conn, account_id)
    if account["kind"] == "agent":
        raise InvalidAccountError("an agent account has no password; issue it a token")
    own = by == actor_for(account["kind"], account["username"])
    if own:
        if current_password is None:
            raise InvalidCredentialsError("the current password is required")
        stored = conn.execute(
            text("SELECT password_hash FROM auth_credential WHERE account_id = :a"),
            {"a": account_id},
        ).scalar()
        if not pw.verify_password(None if stored is None else str(stored), current_password):
            raise InvalidCredentialsError("the current password is incorrect")
    pw.check_policy(new_password, username=account["username"])
    _store_credential(conn, account_id, new_password, clock())
    revoke_sessions(conn, account_id)
    clear_lockout(conn, account["username"])
    _append(
        uow,
        account_id,
        int(account["version"]),
        ACCOUNT_PASSWORD_CHANGED,
        {"account_id": account_id, "by": by, "forced": (not own) if forced is None else forced},
        by,
    )


def issue_agent_token(
    uow: UnitOfWork,
    *,
    account_id: str,
    label: str,
    expires_at: datetime | None,
    by: str,
    clock: Clock = utcnow,
) -> tuple[AgentTokenView, str]:
    """Issue a token for an active agent account. It is returned once; only its hash stays."""
    conn = uow.conn()
    account = _row(conn, account_id)
    if account["kind"] != "agent":
        raise InvalidAccountError("only an agent account holds agent tokens")
    if account["status"] != "active":
        raise AccountStateError("the agent account is disabled")
    name = check_text(label, what="label", limit=MAX_LABEL)
    now = clock()
    if expires_at is not None:
        if expires_at.tzinfo is None:
            raise InvalidAccountError("expires_at must be timezone-aware")
        if expires_at <= now:
            raise InvalidAccountError("expires_at must be in the future")
    live = conn.execute(
        text("SELECT COUNT(*) FROM cur_agent_token WHERE account_id = :a AND revoked = 0"),
        {"a": account_id},
    ).scalar_one()
    if int(live) >= MAX_ACTIVE_TOKENS_PER_AGENT:
        raise AccountStateError(
            f"the agent already has {MAX_ACTIVE_TOKENS_PER_AGENT} live tokens; revoke one first"
        )
    token_id, token = new_ulid(), new_agent_token()
    stamp = None if expires_at is None else iso_z(expires_at)
    conn.execute(
        text(
            "INSERT INTO auth_token_secret (token_hash, token_id, created_at) VALUES (:h, :i, :t)"
        ),
        {"h": token_hash(token), "i": token_id, "t": iso_z(now)},
    )
    _append(
        uow,
        account_id,
        int(account["version"]),
        AGENT_TOKEN_ISSUED,
        {"token_id": token_id, "account_id": account_id, "label": name, "expires_at": stamp},
        by,
    )
    view = AgentTokenView(
        token_id=token_id,
        account_id=account_id,
        label=name,
        expires_at=stamp,
        revoked=False,
        issued_by=by,
    )
    return view, token


def revoke_agent_token(
    uow: UnitOfWork, *, token_id: str, by: str, reason: str | None
) -> AgentTokenView:
    conn = uow.conn()
    found = (
        conn.execute(
            text(
                "SELECT token_id, account_id, label, expires_at, revoked, issued_by "
                "FROM cur_agent_token WHERE token_id = :t"
            ),
            {"t": token_id},
        )
        .mappings()
        .first()
    )
    if found is None:
        raise AgentTokenNotFoundError(f"no agent token {token_id}")
    if int(found["revoked"]) == 1:
        raise AccountStateError("the token is already revoked")
    account = _row(conn, str(found["account_id"]))
    conn.execute(text("DELETE FROM auth_token_secret WHERE token_id = :t"), {"t": token_id})
    _append(
        uow,
        str(found["account_id"]),
        int(account["version"]),
        AGENT_TOKEN_REVOKED,
        {"token_id": token_id, "account_id": str(found["account_id"]), "reason": reason},
        by,
    )
    return AgentTokenView(
        token_id=token_id,
        account_id=str(found["account_id"]),
        label=str(found["label"]),
        expires_at=None if found["expires_at"] is None else str(found["expires_at"]),
        revoked=True,
        issued_by=str(found["issued_by"]),
    )
