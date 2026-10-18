# ruff: noqa: F401
# pyright: reportUnusedImport=false, reportUnusedVariable=false
"""The `tl action` group: define, list and run actions, and read their invocations (P1-I7-T02b).

An action is a named, typed thing a person can ask for on records: a webhook to an outside system
or a registered job. An admin defines it (a webhook's signing secret is printed once, by `define`
and `rotate-secret`); any person the action's `access` allows invokes it. An action that needs
approval becomes a proposal that another person accepts (`tl proposal accept`). Each subcommand
parses options, makes one call into `tl_core.integration.actions`, and prints.


STUB (P1-I7): the functions below whose body is `raise NotImplementedError` are yours;
everything else is final. Remove this paragraph and the two lint-silencing lines at the top
of the file, and `NotImplementedError`, when you implement them.
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
    """List the actions that are not retired, by name, one line each.

    STEPS: in a read-only unit of work (``factory(ctx)`` then ``opened(readonly=True)``) inside
    ``service_errors()`` read ``SELECT * FROM cur_action_definition WHERE retired = :retired ORDER
    BY name`` (``retired=False``) with ``rows(...)`` and print ``action_line(row)`` for each.
    """
    raise NotImplementedError


@app.command("show")
def show(
    ctx: typer.Context, name: Annotated[str, typer.Argument(help="The action's name.")]
) -> None:
    """Print one action: never its secret and never its executor's configuration.

    STEPS: ``row = one(uow, f"action {name}", _ACTION_SQL, name=name)`` in a read-only unit of
    work inside ``service_errors()``. Print, in this order: ``action <name>``, ``id
    <definition_id>``, ``scope``, ``version``, ``label``, ``executor``, ``access``, ``side_effect
    <side_effect_class>``, ``approval yes|no`` (``requires_approval``), ``owner``, ``state
    retired|on|off`` (retired wins, then ``enabled``), ``applies_to <json.dumps(row["applies_to"],
    sort_keys=True)>``; then for each parameter of ``row["parameters"]`` one line ``parameter
    <name> <kind>`` (``required`` after the kind when it is required).
    """
    raise NotImplementedError


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

    STEPS: ``admin_gate(ctx)``; ``scope = scope_of(project, company)``; ``body =
    read_json_file(file)``, which must be a JSON object (else ``fail("the file must hold a JSON
    object")``). In a write unit of work inside ``service_errors()`` call ``made =
    define_action(uow, DefineAction(actor=actor, source=SOURCE, scope=scope, **body))``. Print
    ``action <name>`` (from ``body["name"]``), ``id <made.definition_id>``; and, only when
    ``made.secret`` is not ``None``, ``secret_id <made.secret_id>`` and ``secret
    <made.secret.secret>`` to stdout and ``keep the secret: it is not shown again`` to stderr.
    """
    raise NotImplementedError


@app.command("retire")
def retire(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The action's name.")],
    reason: Annotated[str, typer.Option("--reason", help="Why (kept on the ledger).")],
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Retire an action: it can no longer be invoked. Invocations already made are kept.

    STEPS: ``admin_gate(ctx)``. In a write unit of work inside ``service_errors()``: ``row =
    one(uow, f"action {name}", _ACTION_SQL, name=name)`` and ``handle_retire_action(uow,
    RetireAction(actor=actor, source=SOURCE, scope=row["scope"], definition_id=row["definition_id"],
    reason=reason))``. Print ``action <name> retired``.
    """
    raise NotImplementedError


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
    """Issue a new signing secret for a webhook action. Printed once.

    STEPS: ``admin_gate(ctx)``. In a write unit of work inside ``service_errors()``: read the row
    as ``retire`` does, ``made = rotate_action_secret(uow, RotateActionSecret(actor=actor,
    source=SOURCE, scope=row["scope"], definition_id=row["definition_id"],
    overlap_hours=overlap_hours))``. Print ``action <name>``, ``secret_id <made.secret_id>``,
    ``secret <made.secret.secret>`` (``made.secret`` is not ``None`` here) and, to stderr,
    ``keep the secret: it is not shown again``.
    """
    raise NotImplementedError


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

    STEPS: ``scope = scope_of(project, company)``; ``values = pairs(param or [], "--param")``.
    ``db: DbTarget = ctx.obj``; ``principal = session.current_principal(db)``; ``holds(level)``
    is true when ``principal`` is not ``None`` and ``principal.actor == actor`` and (``level ==
    "user"``, or ``level == "controller"`` and ``principal.is_controller``, or ``level == "admin"``
    and ``principal.is_admin``); with no session it is true only for ``"user"``. In a write unit
    of work inside ``service_errors()``: resolve each ``--target`` key to a record id with
    ``record_id_of(uow, key, scope)``; call
    ``handle_invoke_action(uow, InvokeAction(actor=actor, source=SOURCE, scope=scope, action=name,
    targets=ids, parameters=values), holds=holds)``. When the result's first event type is
    ``Proposal.Created`` print ``proposed <result.stream_id>`` and
    ``needs approval: another person accepts it with tl proposal accept``; otherwise print
    ``invoked <result.stream_id>``.
    """
    raise NotImplementedError


@app.command("invocations")
def invocations(
    ctx: typer.Context,
    action: Annotated[str | None, typer.Option("--action", help="Only this action.")] = None,
    status: Annotated[str | None, typer.Option("--status", help="requested, running, ...")] = None,
    n: Annotated[int, typer.Option("-n", min=1, help="How many (newest first).")] = 50,
) -> None:
    """List invocations, newest first.

    STEPS: ``status`` given and not in ``_STATUSES``: ``fail(f"--status must be one of {',
    '.join(_STATUSES)}")``. Build ``WHERE`` clauses on ``SELECT * FROM cur_action_invocation``:
    ``action = :action`` and ``status = :status`` when given; add ``ORDER BY seq DESC LIMIT :n``.
    In a read-only unit of work inside ``service_errors()`` print, for each row, ``line(row[
    "invocation_id"], row["status"], row["action"], row["invoked_by"], row["requested_at"])``.
    """
    raise NotImplementedError
