"""The `tl action` group: define, list and run actions, and read their invocations (P1-I7-T02b).

An action is a named, typed thing a person can ask for on records: a webhook to an outside system
or a registered job. An admin defines it (a webhook's signing secret is printed once, by `define`
and `rotate-secret`); any person the action's `access` allows invokes it. An action that needs
approval becomes a proposal that another person accepts (`tl proposal accept`). Each subcommand
parses options, makes one call into `tl_core.integration.actions`, and prints.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from tl_adapters.db import DbTarget
from tl_core.integration.actions.service import (
    DefineAction,
    RetireAction,
    RotateActionSecret,
    define_action,
    handle_invoke_action,
    handle_retire_action,
    rotate_action_secret,
)
from tl_core.integration.contract import InvokeAction

from tl_cli import session
from tl_cli.integration_support import (
    DEFAULT_ACTOR,
    SOURCE,
    ActorOption,
    CompanyOption,
    ProjectOption,
    admin_gate,
    factory,
    fail,
    line,
    one,
    pairs,
    read_json_file,
    record_id_of,
    rows,
    scope_of,
    service_errors,
)

app = typer.Typer(help="Actions: define, list, invoke, read invocations.", no_args_is_help=True)

_ACTION_SQL = "SELECT * FROM cur_action_definition WHERE name = :name"
_STATUSES = ("requested", "running", "completed", "failed")


def action_line(row: dict[str, object]) -> str:
    """``send_to_nde  webhook  user  v2  Send to NDE``: name, executor, access, version, label;
    a retired action has ``retired`` after the version."""
    version = f"v{row['version']}"
    parts: list[object] = [row["name"], row["executor"], row["access"], version]
    if row["retired"]:
        parts.append("retired")
    parts.append(row["label"])
    return line(*parts)


@app.command("ls")
def ls(ctx: typer.Context) -> None:
    """List the actions that are not retired, by name, one line each."""
    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        found = rows(
            uow,
            "SELECT * FROM cur_action_definition WHERE retired = :retired ORDER BY name",
            retired=False,
        )
        for row in found:
            typer.echo(action_line(row))


@app.command("show")
def show(
    ctx: typer.Context, name: Annotated[str, typer.Argument(help="The action's name.")]
) -> None:
    """Print one action: never its secret and never its executor's configuration."""
    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        row = one(uow, f"action {name}", _ACTION_SQL, name=name)
    state = "retired" if row["retired"] else ("on" if row["enabled"] else "off")
    typer.echo(f"action {row['name']}")
    typer.echo(f"id {row['definition_id']}")
    typer.echo(f"scope {row['scope']}")
    typer.echo(f"version {row['version']}")
    typer.echo(f"label {row['label']}")
    typer.echo(f"executor {row['executor']}")
    typer.echo(f"access {row['access']}")
    typer.echo(f"side_effect {row['side_effect_class']}")
    typer.echo(f"approval {'yes' if row['requires_approval'] else 'no'}")
    typer.echo(f"owner {row['owner']}")
    typer.echo(f"state {state}")
    typer.echo(f"applies_to {json.dumps(row['applies_to'], sort_keys=True)}")
    for parameter in row["parameters"]:
        required = " required" if parameter["required"] else ""
        typer.echo(f"parameter {parameter['name']} {parameter['kind']}{required}")


@app.command("define")
def define(
    ctx: typer.Context,
    file: Annotated[str, typer.Option("--file", help="JSON file (or -) holding the action.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Define an action from a JSON file. A webhook action's signing secret is printed once.

    The file holds ``name``, ``label``, ``executor``, ``executor_config``, ``side_effect_class``
    and optionally ``description``, ``applies_to``, ``parameters``, ``requires_approval``,
    ``access``, ``result_handling`` and ``integration_app``.
    """
    admin_gate(ctx)
    scope = scope_of(project, company)
    body = read_json_file(file)
    if not isinstance(body, dict):
        fail("the file must hold a JSON object")
    with factory(ctx) as opened, service_errors(), opened() as uow:
        made = define_action(uow, DefineAction(actor=actor, source=SOURCE, scope=scope, **body))
    typer.echo(f"action {body['name']}")
    typer.echo(f"id {made.definition_id}")
    if made.secret is not None:
        typer.echo(f"secret_id {made.secret_id}")
        typer.echo(f"secret {made.secret.secret}")
        typer.echo("keep the secret: it is not shown again", err=True)


@app.command("retire")
def retire(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The action's name.")],
    reason: Annotated[str, typer.Option("--reason", help="Why (kept on the ledger).")],
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Retire an action: it can no longer be invoked. Invocations already made are kept."""
    admin_gate(ctx)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        row = one(uow, f"action {name}", _ACTION_SQL, name=name)
        handle_retire_action(
            uow,
            RetireAction(
                actor=actor,
                source=SOURCE,
                scope=row["scope"],
                definition_id=row["definition_id"],
                reason=reason,
            ),
        )
    typer.echo(f"action {name} retired")


@app.command("rotate-secret")
def rotate_secret(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="A webhook action's name.")],
    overlap_hours: Annotated[
        float,
        typer.Option("--overlap-hours", min=0, max=24, help="Hours the old secret still signs."),
    ] = 24.0,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Issue a new signing secret for a webhook action. Printed once."""
    admin_gate(ctx)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        row = one(uow, f"action {name}", _ACTION_SQL, name=name)
        made = rotate_action_secret(
            uow,
            RotateActionSecret(
                actor=actor,
                source=SOURCE,
                scope=row["scope"],
                definition_id=row["definition_id"],
                overlap_hours=overlap_hours,
            ),
        )
    if made.secret is None:  # a webhook action always gets a new secret here
        fail(f"action {name} has no signing secret")
    typer.echo(f"action {name}")
    typer.echo(f"secret_id {made.secret_id}")
    typer.echo(f"secret {made.secret.secret}")
    typer.echo("keep the secret: it is not shown again", err=True)


@app.command("invoke")
def invoke(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The action's name.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    target: Annotated[
        list[str] | None, typer.Option("--target", help="A record key; repeatable.")
    ] = None,
    param: Annotated[
        list[str] | None, typer.Option("--param", help="name=value; repeatable.")
    ] = None,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Ask for an action on records. Prints the invocation id, or the proposal id when the action
    needs approval.
    """
    scope = scope_of(project, company)
    values = pairs(param or [], "--param")
    db: DbTarget = ctx.obj
    principal = session.current_principal(db)

    def holds(level: str) -> bool:
        if principal is None:  # with no session only the user level is held
            return level == "user"
        return principal.actor == actor and (
            level == "user"
            or (level == "controller" and principal.is_controller)
            or (level == "admin" and principal.is_admin)
        )

    with factory(ctx) as opened, service_errors(), opened() as uow:
        ids = [record_id_of(uow, key, scope) for key in (target or [])]
        result = handle_invoke_action(
            uow,
            InvokeAction(
                actor=actor,
                source=SOURCE,
                scope=scope,
                action=name,
                targets=ids,
                parameters=values,
            ),
            holds=holds,
        )
    # A proposal comes back with no events of its own; an invocation carries Action.Requested.
    if not result.events or result.events[0].event_type == "Proposal.Created":
        typer.echo(f"proposed {result.stream_id}")
        typer.echo("needs approval: another person accepts it with tl proposal accept")
    else:
        typer.echo(f"invoked {result.stream_id}")


@app.command("invocations")
def invocations(
    ctx: typer.Context,
    action: Annotated[str | None, typer.Option("--action", help="Only this action.")] = None,
    status: Annotated[str | None, typer.Option("--status", help="requested, running, ...")] = None,
    n: Annotated[int, typer.Option("-n", min=1, help="How many (newest first).")] = 50,
) -> None:
    """List invocations, newest first."""
    if status is not None and status not in _STATUSES:
        fail(f"--status must be one of {', '.join(_STATUSES)}")
    clauses: list[str] = []
    params: dict[str, object] = {"n": n}
    if action is not None:
        clauses.append("action = :action")
        params["action"] = action
    if status is not None:
        clauses.append("status = :status")
        params["status"] = status
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"SELECT * FROM cur_action_invocation{where} ORDER BY seq DESC LIMIT :n"
    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        for row in rows(uow, query, **params):
            typer.echo(
                line(
                    row["invocation_id"],
                    row["status"],
                    row["action"],
                    row["invoked_by"],
                    row["requested_at"],
                )
            )
