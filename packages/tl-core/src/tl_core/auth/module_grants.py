"""Grant and revoke a module role (ADR-0021; roles-mvp.md section 3; company grants: wave0 14).

Two commands, both with scope ``company`` and both an active human admin's alone. A grant appends
``Account.ModuleRoleGranted`` and a revoke ``Account.ModuleRoleRevoked`` on the account's stream
(stream type ``core.Account``, scope ``company``), copying the pattern of ``accounts.py``; the
projector writes ``cur_account_module_role``. Granting a role already held, or revoking one that
is not held, appends nothing new: the first answers ``changed: false``, the second is
``NoSuchGrantError``.

A revoke skips the table, module, company and agent checks of a grant: a grant made under an
older table (or for a module since removed) must stay revocable.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator
from sqlalchemy import Connection, text

from tl_core.auth.errors import (
    AccountNotFoundError,
    ForbiddenError,
    InvalidAccountError,
    NoCompanyRolesError,
    NoSuchGrantError,
    UnknownModuleError,
    UnknownRoleError,
)
from tl_core.auth.module_roles import (
    ALL_MODULES,
    COMPANY,
    effective_roles,
    holder_for_actor,
    load_role_table,
)
from tl_core.auth.names import check_text, is_id
from tl_core.auth.projector import (
    ACCOUNT_MODULE_ROLE_GRANTED,
    ACCOUNT_MODULE_ROLE_REVOKED,
    ACCOUNT_STREAM_TYPE,
    account_stream_id,
)
from tl_core.ledger import NewEvent
from tl_core.modules import load_modules
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

MAX_REASON = 500
_PROJECT_PATTERN = r"^(company|project:[A-Za-z0-9_.-]+)$"


class _ModuleRoleCommand(Command):
    scope: str = COMPANY
    account_id: str
    project: str = Field(pattern=_PROJECT_PATTERN)
    module: str  # a loaded module name, or "*" (every module of the project)
    role: str  # a role of the table
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("scope")
    @classmethod
    def _company_scope(cls, value: str) -> str:
        if value != COMPANY:
            raise ValueError("a module role command has scope 'company'")
        return value


class GrantModuleRole(_ModuleRoleCommand): ...


class RevokeModuleRole(_ModuleRoleCommand): ...


class ModuleRoleResult(CommandResult):
    """A ``CommandResult`` that also says whether anything was written."""

    changed: bool = True


def _require_admin(conn: Connection, actor: str) -> None:
    holder = holder_for_actor(conn, actor)
    if effective_roles(conn, holder, scope=COMPANY, module=ALL_MODULES).source != "admin":
        raise ForbiddenError("only an active admin may grant or revoke module roles")


def _account(conn: Connection, account_id: str) -> tuple[str, int]:
    """``(kind, stream version)`` of the account, or ``AccountNotFoundError``."""
    row = None
    if is_id(account_id):
        row = conn.execute(
            text("SELECT kind, version FROM cur_account WHERE account_id = :a"), {"a": account_id}
        ).first()
    if row is None:
        raise AccountNotFoundError(f"no account {account_id}")
    return str(row[0]), int(row[1])


def _held(conn: Connection, cmd: _ModuleRoleCommand) -> bool:
    return (
        conn.execute(
            text(
                "SELECT 1 FROM cur_account_module_role WHERE account_id = :a AND project = :p "
                "AND module = :m AND role = :r"
            ),
            {"a": cmd.account_id, "p": cmd.project, "m": cmd.module, "r": cmd.role},
        ).first()
        is not None
    )


def _check_grant(kind: str, cmd: _ModuleRoleCommand) -> None:
    table = load_role_table()
    if cmd.role not in table.roles:
        raise UnknownRoleError(f"unknown role {cmd.role}; roles are {', '.join(table.roles)}")
    modules = {spec.name: spec for spec in load_modules()}
    if cmd.project == COMPANY:
        spec = modules.get(cmd.module)  # "*" is never a module name
        if spec is None or not spec.company_roles:
            raise NoCompanyRolesError(f"{cmd.module} has no company-level roles")
    if cmd.module != ALL_MODULES and cmd.module not in modules:
        raise UnknownModuleError(f"no module {cmd.module}")
    if kind == "agent" and cmd.role not in table.agent_roles:
        raise InvalidAccountError(
            f"an agent account may hold only {', '.join(table.agent_roles)}; not {cmd.role}"
        )


def _event(cmd: _ModuleRoleCommand, reason: str) -> dict[str, Any]:
    return {
        "account_id": cmd.account_id,
        "project": cmd.project,
        "module": cmd.module,
        "role": cmd.role,
        "reason": reason,
    }


def _append(
    uow: UnitOfWork, cmd: _ModuleRoleCommand, version: int, event_type: str
) -> ModuleRoleResult:
    reason = check_text(cmd.reason, what="reason", limit=MAX_REASON)
    done = uow.append(
        stream_id=account_stream_id(cmd.account_id),
        stream_type=ACCOUNT_STREAM_TYPE,
        scope="company",
        expected_version=version,
        events=[NewEvent(event_type=event_type, payload=_event(cmd, reason))],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return ModuleRoleResult(
        stream_id=account_stream_id(cmd.account_id),
        key=None,
        version=done.new_version,
        events=done.events,
        changed=True,
    )


def grant_module_role(uow: UnitOfWork, cmd: GrantModuleRole) -> ModuleRoleResult:
    conn = uow.conn()
    _require_admin(conn, cmd.actor)
    kind, version = _account(conn, cmd.account_id)
    _check_grant(kind, cmd)
    if _held(conn, cmd):
        return ModuleRoleResult(
            stream_id=account_stream_id(cmd.account_id),
            key=None,
            version=version,
            events=[],
            changed=False,
        )
    return _append(uow, cmd, version, ACCOUNT_MODULE_ROLE_GRANTED)


def revoke_module_role(uow: UnitOfWork, cmd: RevokeModuleRole) -> ModuleRoleResult:
    conn = uow.conn()
    _require_admin(conn, cmd.actor)
    _, version = _account(conn, cmd.account_id)
    if not _held(conn, cmd):
        raise NoSuchGrantError(
            f"{cmd.role} on {cmd.module} for {cmd.project} is not held by that account"
        )
    return _append(uow, cmd, version, ACCOUNT_MODULE_ROLE_REVOKED)
