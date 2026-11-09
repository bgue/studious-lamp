"""`tl awp roc ls|show|set`: the rules of credit in force for a project (P2-I5-T01).

`ls` and `show` read the edition in force and its package content; package content is not record
text, so no viewer is widened and no class filter applies. `set` writes one setting, the edition
of the project (`awp.rules_of_credit.set` at `project:<id>`), after the edition is checked. The
commands parse options and print one fact per line; the engine and the settings service decide.
`register(app)` adds the `roc` group to `tl awp`.
"""

from __future__ import annotations

import json
import re
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core import settings
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of
from tl_core.settings.service import change_setting
from tl_core.settings.values import normalise, parse_text
from tl_mod_awp.names import EDITION_SETTING
from tl_mod_awp.progress import engine

from tl_cli.actors import refuse_agent
from tl_cli.derive_support import DEV_ACTOR, SOURCE, Project, acting, fail, scope_of, service_errors

#: The shape of an edition, ``package@version``: the setting's pattern without the empty value.
EDITION_SHAPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}@[0-9]+\.[0-9]+\.[0-9]+")

_Actor = Annotated[
    str,
    typer.Option("--actor", help="Actor recorded on events.", callback=refuse_agent),
]


def roc_ls(ctx: typer.Context, project: Project) -> None:
    """List the rules-of-credit edition in force for the project.

    `editions: 1`, then `<key>  <n commodities>  in force`. An edition that is unknown or not
    adopted is its `error:` line, exit 1.
    """
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    with service_errors(), open_uow(db, readonly=True) as uow:
        key = engine.edition_key(uow.conn(), scope)
        rules = engine.rules_for(key)
    typer.echo("editions: 1")
    typer.echo(f"{key}  {len(rules.by_commodity)}  in force")


def roc_show(
    ctx: typer.Context,
    project: Project,
    edition: Annotated[
        str | None,
        typer.Option(
            "--edition", help="Show this edition (package@version), not the one in force."
        ),
    ] = None,
) -> None:
    """Show the rules of credit of an edition: its steps for each commodity.

    Lines: `edition <key>`, `source default|setting|argument` (argument when --edition is given),
    `commodities: <n>`, then `<commodity>  <kind>  <name> <weight>, <name> <weight>, ...` for each
    commodity in the order of the package. An unknown edition is its `error:` line, exit 1.
    """
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    with service_errors(), open_uow(db, readonly=True) as uow:
        conn = uow.conn()
        if edition is None:
            key = engine.edition_key(conn, scope)
            stored = value_of(conn, EDITION_SETTING, project=project_of_scope(scope))
            source = "setting" if stored else "default"
        else:
            key = edition
            source = "argument"
        engine.rules_for(key)  # refuses an edition that is not adopted or holds no rules
        doc = engine.package_doc(key)
    typer.echo(f"edition {key}")
    typer.echo(f"source {source}")
    typer.echo(f"commodities: {len(doc.rules_of_credit)}")
    for rule in doc.rules_of_credit:
        steps = ", ".join(f"{step.name} {step.weight}" for step in rule.steps)
        typer.echo(f"{rule.commodity}  {rule.kind}  {steps}")


def roc_set(
    ctx: typer.Context,
    edition: Annotated[
        str, typer.Argument(help="The edition, package@version, for example co.acme.awp@1.1.0.")
    ],
    project: Project,
    reason: Annotated[
        str | None, typer.Option("--reason", help="Why (advanced and dangerous keys).")
    ] = None,
    actor: _Actor = DEV_ACTOR,
) -> None:
    """Adopt an edition of the rules of credit for the project.

    Refuses a value that is not `package@version` (`error: edition: expected package@version`)
    and an edition that is not adopted or holds no rules. Prints `set awp.rules_of_credit.set
    project:<id> "<edition>"`, or `unchanged ...` when the project already has it.
    """
    db: DbTarget = ctx.obj
    if EDITION_SHAPE.fullmatch(edition) is None:
        fail("edition: expected package@version")
    layer = f"project:{project}"
    who = acting(db, actor)
    with service_errors():
        engine.rules_for(edition)
        defn = settings.get_definition(EDITION_SETTING)
        typed = normalise(defn, parse_text(defn, edition))
        with open_uow(db) as uow:
            outcome = change_setting(
                uow,
                key=EDITION_SETTING,
                layer=layer,
                value=typed,
                actor=who,
                source=SOURCE,
                reason=reason,
            )
    shown = json.dumps(typed, sort_keys=True, ensure_ascii=False)
    if not outcome.events:
        typer.echo(f"unchanged {EDITION_SETTING} {layer}")
    else:
        typer.echo(f"set {EDITION_SETTING} {layer} {shown}")


def register(app: typer.Typer) -> None:
    """Add the rules-of-credit group (`ls`, `show`, `set`) to `tl awp`."""
    group = typer.Typer(
        help="The rules of credit in force: ls, show and set the edition.", no_args_is_help=True
    )
    group.command("ls")(roc_ls)
    group.command("show")(roc_show)
    group.command("set")(roc_set)
    app.add_typer(group, name="roc")
