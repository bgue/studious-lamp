"""Reads of the core constraints (P2-I2-T04c1): the list, the review groups and one constraint.

Thin: one call into ``tl_core.constraints`` per route, through the viewer's class filter (the API
sets the viewer for the request, so a route passes none). Every route first checks the core access
word ``core.constraint.view`` (``VIEW_WORD``, table word ``read``) through ``guard``, before any
lookup. A hidden constraint, whose subject the viewer may not read, answers the same 404 as a
constraint that does not exist; no list total counts it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Connection, bindparam, text
from tl_core.constraints.commands import RECORD_TYPE, VIEW_WORD
from tl_core.constraints.queries import (
    MAX_LIMIT,
    ConstraintView,
    count_constraints,
    get_constraint,
    list_constraints,
)
from tl_core.constraints.review import review_groups
from tl_core.services.errors import RecordNotFoundError

from tl_api.auth import guard
from tl_api.context import ApiContext, get_ctx

router = APIRouter(tags=["constraints"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
Reader = Annotated[str, Depends(guard(VIEW_WORD))]

_KEY_SQL = text(
    "SELECT id FROM cur_core_record WHERE scope = :scope AND type = :type AND key = :key"
)
_ANY_KEY_SQL = text("SELECT id FROM cur_core_record WHERE scope = :scope AND key = :key")


@dataclass(frozen=True)
class ConstraintRow(ConstraintView):
    """A constraint with the key and type of its subject (a visible record: a constraint of a
    hidden subject is hidden whole)."""

    subject_key: str
    subject_type: str


_SUBJECTS_SQL = text("SELECT id, key, type FROM cur_core_record WHERE id IN :ids").bindparams(
    bindparam("ids", expanding=True)
)


def _rows(conn: Connection, views: list[ConstraintView]) -> list[ConstraintRow]:
    """The views with their subjects' key and type, resolved in one batch for the page."""
    ids = sorted({v.subject_id for v in views})
    found = (
        {str(r.id): (str(r.key), str(r.type)) for r in conn.execute(_SUBJECTS_SQL, {"ids": ids})}
        if ids
        else {}
    )
    return [
        ConstraintRow(
            **asdict(v), subject_key=found[v.subject_id][0], subject_type=found[v.subject_id][1]
        )
        for v in views
        if v.subject_id in found
    ]


class ConstraintList(BaseModel):
    """The constraints a viewer may read, and how many the same filters find in all."""

    rows: list[ConstraintRow]
    total: int


class ConstraintGroupRow(BaseModel):
    """One review group: its label, its size, its blocking and aging counts, its keys."""

    label: str
    count: int
    blocking: int
    aging: int
    keys: list[str]
    members: list[ConstraintRow]


class ConstraintGroups(BaseModel):
    """The review groups, and whether more visible constraints exist than the groups cover."""

    groups: list[ConstraintGroupRow]
    truncated: bool


@router.get("/projects/{project}/constraints", operation_id="list_constraints_api")
def list_constraints_api(
    ctx: Ctx,
    actor: Reader,
    project: str,
    subject: Annotated[
        str | None, Query(min_length=1, max_length=200, description="The subject's key.")
    ] = None,
    state: Annotated[str | None, Query(max_length=64, description="The state.")] = None,
    category: Annotated[str | None, Query(max_length=64, description="The category.")] = None,
    phase: Annotated[str | None, Query(max_length=64, description="The phase.")] = None,
    blocking: Annotated[bool | None, Query(description="Blocking or advisory.")] = None,
    owner: Annotated[
        str | None, Query(min_length=1, max_length=200, description="The owner.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT, description="At most this many rows.")] = 200,
) -> ConstraintList:
    """A project's constraints by key, with the total the same filters find. A subject key the
    viewer cannot see, or that does not exist, finds nothing (rows [], total 0)."""
    scope = f"project:{project}"
    with ctx.backend(True) as uow:
        conn = uow.conn()
        subject_id: str | None = None
        if subject is not None:
            found = conn.execute(
                _ANY_KEY_SQL, {"scope": scope, "key": subject}
            ).scalar_one_or_none()
            if found is None:
                return ConstraintList(rows=[], total=0)
            subject_id = str(found)
        filters = {
            "subject_id": subject_id,
            "state": state,
            "category": category,
            "phase": phase,
            "blocking": blocking,
            "owner": owner,
        }
        rows = list_constraints(conn, scope, limit=limit, **filters)
        return ConstraintList(
            rows=_rows(conn, rows), total=count_constraints(conn, scope, **filters)
        )


@router.get("/projects/{project}/constraints/groups", operation_id="constraint_groups")
def constraint_groups(
    ctx: Ctx,
    actor: Reader,
    project: str,
    by: Annotated[Literal["owner", "category", "age"], Query(description="The grouping.")],
    state: Annotated[str | None, Query(max_length=64, description="The state.")] = None,
    category: Annotated[str | None, Query(max_length=64, description="The category.")] = None,
    phase: Annotated[str | None, Query(max_length=64, description="The phase.")] = None,
    blocking: Annotated[bool | None, Query(description="Blocking or advisory.")] = None,
    owner: Annotated[
        str | None, Query(min_length=1, max_length=200, description="The owner.")
    ] = None,
) -> ConstraintGroups:
    """The visible constraints of a project grouped by `owner`, `category` or `age`. Groups cover
    at most the first 500 visible constraints by key; `truncated` is true when more are visible."""
    scope = f"project:{project}"
    with ctx.backend(True) as uow:
        views = list_constraints(
            uow.conn(),
            scope,
            state=state,
            category=category,
            phase=phase,
            blocking=blocking,
            owner=owner,
            limit=MAX_LIMIT,
        )
        by_key = {r.key: r for r in _rows(uow.conn(), views)}
        total = count_constraints(
            uow.conn(),
            scope,
            state=state,
            category=category,
            phase=phase,
            blocking=blocking,
            owner=owner,
        )
    rows = [
        ConstraintGroupRow(
            label=group.label,
            count=group.count,
            blocking=group.blocking,
            aging=group.aging,
            keys=list(group.keys),
            members=[by_key[k] for k in group.keys if k in by_key],
        )
        for group in review_groups(views, by)
    ]
    return ConstraintGroups(groups=rows, truncated=total > MAX_LIMIT)


@router.get("/projects/{project}/constraints/{key}", operation_id="get_constraint_api")
def get_constraint_api(ctx: Ctx, actor: Reader, project: str, key: str) -> ConstraintRow:
    """One constraint by key. 404 `record_not_found` when it is missing or hidden (the same
    answer for both)."""
    scope = f"project:{project}"
    with ctx.backend(True) as uow:
        conn = uow.conn()
        record_id = conn.execute(
            _KEY_SQL, {"scope": scope, "type": RECORD_TYPE, "key": key}
        ).scalar_one_or_none()
        found = None if record_id is None else get_constraint(conn, str(record_id))
        if found is None:
            raise RecordNotFoundError(f"no constraint {key!r}")
        return _rows(conn, [found])[0]
