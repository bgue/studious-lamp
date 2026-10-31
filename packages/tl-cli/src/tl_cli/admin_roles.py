"""`tl admin roles ...`: grant, revoke, list and read module roles (RM-S3; ADR-0021).

Needs a signed-in admin (`tl login`). Each command is one call into `tl_core.auth`: a grant or a
revoke runs the RM-S1 handler as the admin, a list or an effective read the RM-S3 views.
``--project`` is a project id (``P1`` means ``project:P1``) or ``company``. No decision is made
here: the handlers refuse an unknown role or module, a company grant for a module without company
roles, an agent holding a role outside the agent roles, and a revoke of a role not held.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from pydantic import ValidationError
from tl_core.auth.module_grants import (
    GrantModuleRole,
    ModuleRoleResult,
    RevokeModuleRole,
    grant_module_role,
    revoke_module_role,
)
from tl_core.auth.module_role_views import effective_role_views, list_module_roles

from tl_cli.admin import backend_of, find_account
from tl_cli.session import fail, require_admin, service_errors

app = typer.Typer(help="Module roles: grant, revoke, list, effective.", no_args_is_help=True)

_Name = Annotated[str, typer.Argument(help="The account's username.")]
_Project = Annotated[
    str, typer.Option("--project", help="A project id (P1 means project:P1), or company.")
]
_Module = Annotated[str, typer.Option("--module", help="A module name, or * for every module.")]
_Role = Annotated[str, typer.Option("--role", help="viewer, user or superuser.")]
_Reason = Annotated[str, typer.Option("--reason", help="Why (kept in the history).")]

COMPANY = "company"
PROJECT_PREFIX = "project:"

# Every command starts: admin = require_admin(ctx.obj); backend = backend_of(ctx). Service calls
# run inside `with service_errors():`. Do not catch service exceptions yourself.


def scope_of(project: str) -> str:
    """``P1`` as ``project:P1``; ``company`` and ``project:P1`` as they are."""
    if project == COMPANY or project.startswith(PROJECT_PREFIX):
        return project
    return f"{PROJECT_PREFIX}{project}"


def _change(
    ctx: typer.Context,
    username: str,
    project: str,
    module: str,
    role: str,
    reason: str,
    *,
    grant: bool,
) -> tuple[ModuleRoleResult, str]:
    """Run the grant or revoke handler as the signed-in admin; the result and the scope used."""
    admin = require_admin(ctx.obj)
    backend = backend_of(ctx)
    scope = scope_of(project)
    with service_errors():
        target = find_account(backend, username)
        fields = {
            "actor": admin.actor,
            "source": "cli",
            "account_id": target.account_id,
            "project": scope,
            "module": module,
            "role": role,
            "reason": reason,
        }
        try:
            command = GrantModuleRole(**fields) if grant else RevokeModuleRole(**fields)
        except ValidationError as exc:
            fail(f"invalid module role request: {exc.errors()[0]['msg']}")
        with backend() as uow:
            if isinstance(command, GrantModuleRole):
                return grant_module_role(uow, command), scope
            return revoke_module_role(uow, command), scope
    raise AssertionError("unreachable")  # service_errors exits on every failure


@app.command("grant")
def grant(
    ctx: typer.Context,
    username: _Name,
    project: _Project,
    module: _Module,
    role: _Role,
    reason: _Reason,
) -> None:
    """Grant ROLE on MODULE for the project to USERNAME (nothing changes if already held)."""
    result, scope = _change(ctx, username, project, module, role, reason, grant=True)
    held = "granted" if result.changed else "already held:"
    typer.echo(f"{held} {role} on {module} for {scope} to {username}")


@app.command("revoke")
def revoke(
    ctx: typer.Context,
    username: _Name,
    project: _Project,
    module: _Module,
    role: _Role,
    reason: _Reason,
) -> None:
    """Take ROLE on MODULE for the project away from USERNAME (an error if it is not held)."""
    _, scope = _change(ctx, username, project, module, role, reason, grant=False)
    typer.echo(f"revoked {role} on {module} for {scope} from {username}")


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: Annotated[str | None, typer.Option("--project", help="Only this project.")] = None,
    module: Annotated[str | None, typer.Option("--module", help="Only this module.")] = None,
    user: Annotated[str | None, typer.Option("--user", help="Only this account.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print a JSON list.")] = False,
) -> None:
    """List the explicit module role grants: who, where, which role, granted by whom and when."""
    require_admin(ctx.obj)
    backend = backend_of(ctx)
    with service_errors():
        owner = None if user is None else find_account(backend, user).account_id
        with backend(readonly=True) as uow:
            grants = list_module_roles(
                uow.conn(),
                project=None if project is None else scope_of(project),
                module=module,
                account_id=owner,
            )
    if as_json:
        typer.echo(json.dumps([g.model_dump() for g in grants], indent=2))
        return
    for g in grants:
        typer.echo(
            f"{g.username}  {g.project}  {g.module}  {g.role}  by {g.granted_by}  {g.granted_at}"
        )


@app.command("effective")
def effective(
    ctx: typer.Context,
    username: _Name,
    project: _Project,
    as_json: Annotated[bool, typer.Option("--json", help="Print a JSON list.")] = False,
) -> None:
    """Show what USERNAME holds per module on the project, and where each role comes from."""
    require_admin(ctx.obj)
    backend = backend_of(ctx)
    with service_errors():
        target = find_account(backend, username)
        with backend(readonly=True) as uow:
            views = effective_role_views(uow.conn(), target.account_id, scope_of(project))
    if as_json:
        typer.echo(json.dumps([v.model_dump() for v in views], indent=2))
        return
    for v in views:
        typer.echo(f"{v.module}  {','.join(v.roles) or '-'}  {v.source}")
