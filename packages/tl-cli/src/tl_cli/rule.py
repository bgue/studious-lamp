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
    refuse_server_fields,
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
    """List the rules of a scope (every scope when neither option is given), one line each."""
    scope = scope_of(project, company) if (project is not None or company) else None
    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        if scope is None:
            found = rows(uow, "SELECT * FROM cur_rule ORDER BY key")
        else:
            found = rows(
                uow, "SELECT * FROM cur_rule WHERE scope = :scope ORDER BY key", scope=scope
            )
        printed = [rule_line(row) for row in found]
    for text_line in printed:
        typer.echo(text_line)


@app.command("show")
def show(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The rule's key.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
) -> None:
    """Print one rule."""
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        row = one(uow, f"rule {key}", _RULE_SQL, key=key, scope=scope)
    out = [
        f"rule {row['key']}",
        f"id {row['rule_id']}",
        f"scope {row['scope']}",
        f"version {row['version']}",
        f"state {'on' if row['enabled'] else 'off'}",
        f"mode {row['mode']}",
        f"access {row['access']}",
        f"owner {row['owner']}",
        f"title {row['title']}",
        f"when {json.dumps(row['when'], sort_keys=True)}",
    ]
    if row["condition"] is not None:
        out.append(f"condition {row['condition']}")
    for number, step in enumerate(row["then"], start=1):
        out.append(f"step {number} {step['command']} {json.dumps(step['args'], sort_keys=True)}")
    for text_line in out:
        typer.echo(text_line)


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
    """
    admin_gate(ctx)
    scope = scope_of(project, company)
    body = read_json_file(file)
    if not isinstance(body, dict):
        fail("the file must hold a JSON object")
    refuse_server_fields(body)
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
    """Change a rule's mode (a revision with a reason)."""
    admin_gate(ctx)
    if new_mode not in ("act", "propose"):
        fail("the mode is act or propose")
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        row = one(uow, f"rule {key}", _RULE_SQL, key=key, scope=scope)
        handle_revise_rule(
            uow,
            ReviseRule(
                actor=actor,
                source=SOURCE,
                scope=scope,
                rule_id=row["rule_id"],
                changes={"mode": new_mode},
                reason=reason,
            ),
        )
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
    """What the rule would have done over past events. Nothing is written and nothing runs."""
    from tl_api.commands import command_runner

    admin_gate(ctx)
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
        commands = ",".join(planned.command_type for planned in firing.planned) or "-"
        typer.echo(line(firing.seq, firing.outcome, commands))
        for problem in firing.problems:
            typer.echo(f"  problem {problem.code}: {problem.message}")
