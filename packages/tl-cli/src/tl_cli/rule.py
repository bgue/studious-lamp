"""The `tl rule` group: author and switch rules, and ask what a rule would have done (P1-I7-T03b).

Each subcommand parses options, makes one call into `tl_core.integration.rules`, and prints.
Rules are the admin's to author (FANOUT D12); the services hold the rules (a rule starts disabled
and in `propose` mode, a service actor is made from its key). A rule is named by its key and the
scope it was made in.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from tl_core.integration.rules.dryrun import dry_run_rule
from tl_core.integration.rules.engine import load_rule
from tl_core.integration.rules.service import (
    CreateRule,
    DisableRule,
    EnableRule,
    ReviseRule,
    handle_create_rule,
    handle_disable_rule,
    handle_enable_rule,
    handle_revise_rule,
)

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
    read_json_file,
    rows,
    scope_of,
    service_errors,
)

app = typer.Typer(help="Rules: create, show, enable, disable, dry-run.", no_args_is_help=True)

_RULE_SQL = "SELECT * FROM cur_rule WHERE key = :key AND scope = :scope"


def rule_line(row: dict[str, object]) -> str:
    """``hse-notify  on  propose  user  v1  Notify HSE``: key, on/off, mode, access, version and
    title."""
    state = "on" if row["enabled"] else "off"
    return line(row["key"], state, row["mode"], row["access"], f"v{row['version']}", row["title"])


@app.command("ls")
def ls(ctx: typer.Context, project: ProjectOption = None, company: CompanyOption = False) -> None:
    """List the rules of a scope (every scope when neither option is given), one line each.

    STEPS: ``scope = scope_of(project, company)`` when either option is given, else no scope
    filter. Open ``factory(ctx)`` and a read-only unit of work (``opened(readonly=True)``); inside
    ``service_errors()`` read ``SELECT * FROM cur_rule [WHERE scope = :scope] ORDER BY key`` with
    ``rows(...)`` and print ``rule_line(row)`` for each. Print nothing for no rules.
    """
    scope = scope_of(project, company) if project is not None or company else None
    with factory(ctx) as opened, opened(readonly=True) as uow, service_errors():
        sql = "SELECT * FROM cur_rule" + ("" if scope is None else " WHERE scope = :scope")
        params = {} if scope is None else {"scope": scope}
        for row in rows(uow, sql + " ORDER BY key", **params):
            typer.echo(rule_line(row))


@app.command("show")
def show(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The rule's key.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
) -> None:
    """Print one rule.

    STEPS: ``scope = scope_of(project, company)``; ``row = one(uow, f"rule {key}", _RULE_SQL,
    key=key, scope=scope)`` in a read-only unit of work inside ``service_errors()``. Print, in this
    order: ``rule <key>``, ``id <rule_id>``, ``scope <scope>``, ``version <version>``,
    ``state on|off``, ``mode <mode>``, ``access <access>``, ``owner <owner>``, ``title <title>``,
    ``when <json>`` (``json.dumps(row["when"], sort_keys=True)``), ``condition <text>`` only when
    there is one, then for each step number n from 1 ``step n <command> <json args>``
    (``json.dumps(args, sort_keys=True)``) from ``row["then"]`` (a list of ``{"command", "args"}``).
    """
    scope = scope_of(project, company)
    with factory(ctx) as opened, opened(readonly=True) as uow, service_errors():
        row = one(uow, f"rule {key}", _RULE_SQL, key=key, scope=scope)
    typer.echo(f"rule {row['key']}")
    typer.echo(f"id {row['rule_id']}")
    typer.echo(f"scope {row['scope']}")
    typer.echo(f"version {row['version']}")
    typer.echo(f"state {'on' if row['enabled'] else 'off'}")
    typer.echo(f"mode {row['mode']}")
    typer.echo(f"access {row['access']}")
    typer.echo(f"owner {row['owner']}")
    typer.echo(f"title {row['title']}")
    typer.echo(f"when {json.dumps(row['when'], sort_keys=True)}")
    if row["condition"]:
        typer.echo(f"condition {row['condition']}")
    for number, step in enumerate(row["then"], start=1):
        typer.echo(f"step {number} {step['command']} {json.dumps(step['args'], sort_keys=True)}")


@app.command("create")
def create(
    ctx: typer.Context,
    file: Annotated[str, typer.Option("--file", help="JSON file (or -) holding the rule.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Create a rule from a JSON file. It starts disabled and in propose mode.

    The file holds ``key``, ``title``, ``when``, ``then`` and optionally ``condition``,
    ``access`` and ``integration_app``.

    STEPS: ``admin_gate(ctx)`` first (the given code has it); ``scope = scope_of(project,
    company)``; ``body = read_json_file(file)``; it must be a
    JSON object (else ``fail("the file must hold a JSON object")``). Inside ``service_errors()``
    open a unit of work and call ``handle_create_rule(uow, CreateRule(actor=actor, source=SOURCE,
    scope=scope, **body))``; print ``rule <key>`` and ``id <stream_id>`` (the result's ``key`` and
    ``stream_id``).
    """
    admin_gate(ctx)
    scope = scope_of(project, company)
    body = read_json_file(file)
    if not isinstance(body, dict):
        fail("the file must hold a JSON object")
    with factory(ctx) as opened, service_errors(), opened() as uow:
        made = handle_create_rule(uow, CreateRule(actor=actor, source=SOURCE, scope=scope, **body))
    typer.echo(f"rule {made.key}")
    typer.echo(f"id {made.stream_id}")


def _switch(
    ctx: typer.Context, key: str, project: str | None, company: bool, actor: str, *, on: bool
) -> None:
    admin_gate(ctx)
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        row = one(uow, f"rule {key}", _RULE_SQL, key=key, scope=scope)
        command = (EnableRule if on else DisableRule)(
            actor=actor, source=SOURCE, scope=scope, rule_id=row["rule_id"]
        )
        (handle_enable_rule if on else handle_disable_rule)(uow, command)  # type: ignore[arg-type]
    typer.echo(f"rule {key} {'on' if on else 'off'}")


@app.command("enable")
def enable(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The rule's key.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Switch a rule on. Prints ``rule <key> on``. (Given: it calls ``_switch``.)"""
    _switch(ctx, key, project, company, actor, on=True)


@app.command("disable")
def disable(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The rule's key.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Switch a rule off. Prints ``rule <key> off``. (Given: it calls ``_switch``.)"""
    _switch(ctx, key, project, company, actor, on=False)


@app.command("mode")
def mode(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The rule's key.")],
    new_mode: Annotated[str, typer.Argument(help="act or propose.")],
    reason: Annotated[str, typer.Option("--reason", help="Why (kept on the revision).")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Change a rule's mode (a revision with a reason).

    STEPS: ``new_mode`` not in ("act", "propose"): ``fail("the mode is act or propose")``.
    ``scope = scope_of(project, company)``. Inside ``service_errors()`` open a unit of work, read
    the row with ``one(...)`` as ``show`` does, and call ``handle_revise_rule(uow,
    ReviseRule(actor=actor, source=SOURCE, scope=scope, rule_id=row["rule_id"],
    changes={"mode": new_mode}, reason=reason))``. Print ``rule <key> mode <new_mode>``.
    """
    admin_gate(ctx)
    if new_mode not in ("act", "propose"):
        fail("the mode is act or propose")
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        row = one(uow, f"rule {key}", _RULE_SQL, key=key, scope=scope)
        handle_revise_rule(
            uow,
            ReviseRule(
                actor=actor, source=SOURCE, scope=scope, rule_id=row["rule_id"],
                changes={"mode": new_mode}, reason=reason,
            ),
        )  # fmt: skip
    typer.echo(f"rule {key} mode {new_mode}")


@app.command("dry-run")
def dry_run(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The rule's key.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    from_seq: Annotated[int, typer.Option("--from-seq", min=0, help="First seq to read.")] = 0,
    to_seq: Annotated[int | None, typer.Option("--to-seq", min=0, help="Last seq.")] = None,
) -> None:
    """What the rule would have done over past events. Nothing is written and nothing runs.

    STEPS: ``scope = scope_of(project, company)``. Inside ``service_errors()`` open
    ``factory(ctx)``; read the rule id with ``one(...)`` in a read-only unit of work; then
    ``stored = load_rule(uow.conn(), rule_id)`` (there; not ``None``) and ``report =
    dry_run_rule(opened, runner, stored, from_seq=from_seq, to_seq=to_seq)`` where ``runner`` is
    ``tl_api.commands.command_runner()`` (import it inside the function). Print
    ``events <report.events_read>``, ``firings <len(report.firings)>``, ``truncated yes|no``;
    then for each firing ``<seq>  <outcome>  <commands>`` (``line(...)``; ``commands`` is the
    command types of ``firing.planned`` joined by ``,``, or ``-`` when there are none), and for
    each problem of the firing one line ``  problem <code>: <message>``.
    """
    from tl_api.commands import command_runner

    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors():
        with opened(readonly=True) as uow:
            row = one(uow, f"rule {key}", _RULE_SQL, key=key, scope=scope)
            stored = load_rule(uow.conn(), row["rule_id"])
        if stored is None:
            fail(f"no rule {key}")
        report = dry_run_rule(opened, command_runner(), stored, from_seq=from_seq, to_seq=to_seq)
    typer.echo(f"events {report.events_read}")
    typer.echo(f"firings {len(report.firings)}")
    typer.echo(f"truncated {'yes' if report.truncated else 'no'}")
    for firing in report.firings:
        planned = ",".join(p.command_type for p in firing.planned) or "-"
        typer.echo(line(firing.seq, firing.outcome, planned))
        for problem in firing.problems:
            typer.echo(f"  problem {problem.code}: {problem.message}")
