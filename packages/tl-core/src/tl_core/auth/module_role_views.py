"""Reads of module roles for the admin surfaces (ADR-0021; roles-mvp.md section 6).

Two plain queries and their views. ``list_module_roles`` reads the explicit grants
(``cur_account_module_role``); ``effective_role_views`` asks the one resolver
(:func:`tl_core.auth.module_roles.effective_roles`) once per loaded module. Nothing here decides
who may read: the surface (route, command, screen) does that, and these reads are not filtered by
module role (roles-mvp.md section 7). No decision logic is added.
"""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import Connection, text

from tl_core.auth.errors import AccountNotFoundError
from tl_core.auth.module_roles import Holder, Source, effective_roles, load_role_table
from tl_core.auth.queries import actor_of, find_account
from tl_core.modules import load_modules

#: ``company`` or ``project:<id>``: the value of every ``project`` field and query of a surface.
#: The same pattern as the grant commands (``module_grants``).
PROJECT_PATTERN = r"^(company|project:[A-Za-z0-9_.-]+)$"


class ModuleRoleGrantView(BaseModel):
    """One explicit grant, with the account's username."""

    account_id: str
    username: str
    project: str
    module: str
    role: str
    granted_by: str
    granted_at: str


class EffectiveRoleView(BaseModel):
    """What one account holds for one module on one project, and why (the resolver's source)."""

    module: str
    roles: list[str]
    source: Source


def list_module_roles(
    conn: Connection,
    *,
    project: str | None = None,
    module: str | None = None,
    account_id: str | None = None,
) -> list[ModuleRoleGrantView]:
    """Explicit grants, by project, module, username and role; each filter given narrows."""
    where: list[str] = []
    params: dict[str, str] = {}
    for column, value in (("project", project), ("module", module), ("account_id", account_id)):
        if value is not None:
            where.append(f"g.{column} = :{column}")
            params[column] = value
    sql = (
        "SELECT g.account_id, a.username, g.project, g.module, g.role, g.granted_by, g.granted_at "
        "FROM cur_account_module_role g JOIN cur_account a ON a.account_id = g.account_id"
        + (" WHERE " + " AND ".join(where) if where else "")
        + " ORDER BY g.project, g.module, a.username, g.role"
    )
    return [
        ModuleRoleGrantView(
            account_id=str(row["account_id"]),
            username=str(row["username"]),
            project=str(row["project"]),
            module=str(row["module"]),
            role=str(row["role"]),
            granted_by=str(row["granted_by"]),
            granted_at=str(row["granted_at"]),
        )
        for row in conn.execute(text(sql), params).mappings()
    ]


def effective_role_views(
    conn: Connection, account_id: str, project: str, *, holder: Holder | None = None
) -> list[EffectiveRoleView]:
    """One entry per loaded module: the roles ``account_id`` holds there on ``project``.

    The holder is built from the account row (as ``holder_for_actor`` does); a caller that
    already has one (the API's ``/auth/me/roles``, whose dev-token principal has no row) passes
    it. ``AccountNotFoundError`` when there is neither. Roles are in the table's order.
    """
    if holder is None:
        account = find_account(conn, account_id=account_id)
        if account is None:
            raise AccountNotFoundError(f"no account {account_id}")
        holder = Holder(
            actor=actor_of(account),
            kind=account.kind,
            account_id=account.account_id,
            account_roles=tuple(account.roles),
        )
    order = list(load_role_table().roles)
    views: list[EffectiveRoleView] = []
    for spec in load_modules():
        found = effective_roles(conn, holder, scope=project, module=spec.name)
        roles = [role for role in order if role in found.roles]
        views.append(EffectiveRoleView(module=spec.name, roles=roles, source=found.source))
    return views
