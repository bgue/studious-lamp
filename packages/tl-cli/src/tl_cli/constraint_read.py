"""`tl constraint ls|show|groups`: the constraint reads (P2-I2-T04d).

None of these writes anything. Every verb first checks the access word `core.constraint.view` on
the project for the invoking actor (`--actor`, default the dev actor), before any constraint is
read; a refusal is `error: forbidden: ...`. The reads then go through `tl_core.constraints` with
the session's viewer, so a hidden subject is absent from a list, its total and a show, and answers
the same as a missing key. The CLI prints the keys and fields the views return and queries nothing
itself. `register(app)` adds the three commands to the `constraint` group.
"""

from __future__ import annotations

from typing import Annotated, Any

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import holder_for_actor, normalise_word, require_word
from tl_core.confidentiality import Viewer
from tl_core.constraints.commands import ACCESS_MODULE, RECORD_TYPE, VIEW_WORD
from tl_core.constraints.queries import (
    ConstraintView,
    count_constraints,
    get_constraint,
    list_constraints,
)
from tl_core.constraints.review import BY_WORDS, review_groups
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork

from tl_cli.derive_support import DEV_ACTOR, acting, cell, fail, scope_of, service_errors
from tl_cli.session import session_viewer

#: The default and the most rows the list prints (the view clamps to 1..500).
LIST_LIMIT = 200
#: The rows a group read is built from (the view's cap); groups are over the filtered list.
GROUP_LIMIT = 500

Actor = Annotated[
    str,
    typer.Option("--actor", help="The actor whose access words gate the read (default dev)."),
]


def require_view(uow: UnitOfWork, scope: str, actor: str) -> None:
    """The entry check of every constraint read: ``actor`` holds ``core.constraint.view``.

    The word is a role gate, so a refusal is `error: forbidden: ...` and does not hide anything.
    """
    try:
        require_word(
            uow.conn(),
            holder_for_actor(uow.conn(), actor),
            scope=scope,
            module=ACCESS_MODULE,
            word=normalise_word(VIEW_WORD),
            what=VIEW_WORD,
        )
    except ForbiddenError as exc:
        fail(f"forbidden: {exc}")


def enter(db: DbTarget, scope: str, actor: str) -> Viewer:
    """Check the actor (``acting``), check the view word, and return the viewer the reads use."""
    checked = acting(db, actor)
    viewer = session_viewer(db)
    with service_errors(), open_uow(db, readonly=True) as uow:
        require_view(uow, scope, checked)
    return viewer


def subject_id(uow: UnitOfWork, scope: str, key: str, viewer: Viewer) -> str:
    """The id of the record ``key`` names (the lookup of ``tl link``), as ``viewer`` may read it.

    A hidden record answers as one that does not exist: `error: no record <key>`.
    """
    with cf.use_viewer(viewer):
        row = get_record(uow, scope, key)
    if row is None:
        fail(f"no record {key}")
    return str(row["id"])


def constraint_of(uow: UnitOfWork, scope: str, key: str, viewer: Viewer) -> ConstraintView | None:
    """The constraint with this key, or None when it is absent or its subject is hidden."""
    with cf.use_viewer(viewer):
        row = get_record(uow, scope, key)
    if row is None or row.get("type") != RECORD_TYPE:
        return None
    return get_constraint(uow.conn(), str(row["id"]), viewer=viewer)


def filters(
    uow: UnitOfWork,
    scope: str,
    *,
    subject: str | None,
    state: str | None,
    category: str | None,
    phase: str | None,
    blocking: bool | None,
    owner: str | None,
    viewer: Viewer,
) -> dict[str, Any]:
    """The keyword filters the list, the total and the groups share (``--subject`` resolved)."""
    subject_key = None if subject is None else subject_id(uow, scope, subject, viewer)
    return {
        "subject_id": subject_key,
        "state": state,
        "category": category,
        "phase": phase,
        "blocking": blocking,
        "owner": owner,
        "viewer": viewer,
    }


def _owner_check(owner: str | None) -> None:
    if owner == "":
        fail("owner must not be empty")


def con_ls(
    ctx: typer.Context,
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    actor: Actor = DEV_ACTOR,
    subject: Annotated[
        str | None, typer.Option("--subject", help="Only constraints on this record key.")
    ] = None,
    state: Annotated[str | None, typer.Option("--state", help="Only this state.")] = None,
    category: Annotated[str | None, typer.Option("--category", help="Only this category.")] = None,
    phase: Annotated[str | None, typer.Option("--phase", help="Only this phase.")] = None,
    blocking: Annotated[
        bool | None,
        typer.Option("--blocking/--advisory", help="Only blocking (or only advisory) ones."),
    ] = None,
    owner: Annotated[str | None, typer.Option("--owner", help="Only this owner (user:X).")] = None,
    limit: Annotated[
        int, typer.Option("--limit", min=1, help="The most rows to list (default 200).")
    ] = LIST_LIMIT,
) -> None:
    """List the constraints of the project by key, with the total the viewer may see.

    `constraints: <total>`, then `<key>  <state>  <severity>  <category>  <phase>  <owner or ->
    <due or ->  <age>d<*>  <description>` for each, `*` when aging, the description cut to 60.
    """
    _owner_check(owner)
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        kept = filters(
            uow,
            scope,
            subject=subject,
            state=state,
            category=category,
            phase=phase,
            blocking=blocking,
            owner=owner,
            viewer=viewer,
        )
        total = count_constraints(uow.conn(), scope, **kept)
        found = list_constraints(uow.conn(), scope, limit=limit, **kept)
    typer.echo(f"constraints: {total}")
    for v in found:
        typer.echo(
            f"{v.key}  {v.state}  {v.severity}  {v.category}  {v.phase}  {cell(v.owner)}  "
            f"{cell(v.due_at)}  {v.age_days}d{'*' if v.aging else ''}  {cell(v.description, 60)}"
        )


def con_show(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The constraint key, for example P123-CON-0001.")],
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Show one constraint.

    Lines: `constraint <key>`, `state`, `severity`, `category`, `phase`, `source`, `owner or ->`,
    `due or ->`, `raised <raised_on>  age <n>d`, `check`, `target <kind or ref type: text or ->`,
    `description`, and `cleared <at> by <who>: <reason>` when cleared. An absent or hidden
    constraint is `error: no constraint <key>`.
    """
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        v = constraint_of(uow, scope, key, viewer)
    if v is None:
        fail(f"no constraint {key}")
    lines = [
        f"constraint {v.key}",
        f"state {v.state}",
        f"severity {v.severity}",
        f"category {v.category}",
        f"phase {v.phase}",
        f"source {v.source}",
        f"owner {cell(v.owner)}",
        f"due {cell(v.due_at)}",
        f"raised {v.raised_on}  age {v.age_days}d",
        f"check {cell(v.check_name)}",
        _target_line(v),
        f"description {cell(v.description, 1000)}",
    ]
    if v.cleared_at is not None:
        lines.append(
            f"cleared {v.cleared_at} by {cell(v.cleared_by)}: {cell(v.clear_reason, 1000)}"
        )
    for line in lines:
        typer.echo(line)


def _target_line(v: ConstraintView) -> str:
    """``target <kind>``, else ``target <ref type>: <text>``, else ``target -``."""
    if v.target_kind is not None:
        return f"target {v.target_kind}"
    if v.target_ref_type is not None:
        return f"target {v.target_ref_type}: {cell(v.target_ref_text, 1000)}"
    return "target -"


def con_groups(
    ctx: typer.Context,
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    by: Annotated[str, typer.Option("--by", help="Group by owner, category or age.")],
    actor: Actor = DEV_ACTOR,
    subject: Annotated[
        str | None, typer.Option("--subject", help="Only constraints on this record key.")
    ] = None,
    state: Annotated[str | None, typer.Option("--state", help="Only this state.")] = None,
    category: Annotated[str | None, typer.Option("--category", help="Only this category.")] = None,
    phase: Annotated[str | None, typer.Option("--phase", help="Only this phase.")] = None,
    blocking: Annotated[
        bool | None,
        typer.Option("--blocking/--advisory", help="Only blocking (or only advisory) ones."),
    ] = None,
    owner: Annotated[str | None, typer.Option("--owner", help="Only this owner (user:X).")] = None,
) -> None:
    """Group the filtered constraints by owner, category or age band.

    `groups: <n>`, then `<label>  <count>  blocking <b>  aging <a>` for each group. A `--by` that
    is not owner, category or age is a usage error (exit 2).
    """
    if by not in BY_WORDS:
        raise typer.BadParameter(f"must be one of {', '.join(BY_WORDS)}", param_hint="'--by'")
    _owner_check(owner)
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        kept = filters(
            uow,
            scope,
            subject=subject,
            state=state,
            category=category,
            phase=phase,
            blocking=blocking,
            owner=owner,
            viewer=viewer,
        )
        found = list_constraints(uow.conn(), scope, limit=GROUP_LIMIT, **kept)
    groups = review_groups(found, by)
    typer.echo(f"groups: {len(groups)}")
    for g in groups:
        typer.echo(f"{g.label}  {g.count}  blocking {g.blocking}  aging {g.aging}")


def register(app: typer.Typer) -> None:
    """Add the constraint reads (`ls`, `show`, `groups`) to the `constraint` group."""
    for function, name in ((con_ls, "ls"), (con_show, "show"), (con_groups, "groups")):
        app.command(name)(function)
