"""Reads of the core constraints (P2-I2-T04c1): the list, the review groups and one constraint.

Thin: one call into ``tl_core.constraints`` per route, through the viewer's class filter (the API
sets the viewer for the request, so a route passes none). Every route first checks the core access
word ``core.constraint.view`` (``VIEW_WORD``, table word ``read``) through ``guard``, before any
lookup. A hidden constraint, whose subject the viewer may not read, answers the same 404 as a
constraint that does not exist; no list total counts it.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
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


class ConstraintList(BaseModel):
    """The constraints a viewer may read, and how many the same filters find in all."""

    rows: list[ConstraintView]
    total: int


class ConstraintGroupRow(BaseModel):
    """One review group: its label, its size, its blocking and aging counts, its keys."""

    label: str
    count: int
    blocking: int
    aging: int
    keys: list[str]


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
        return ConstraintList(rows=rows, total=count_constraints(conn, scope, **filters))


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
) -> list[ConstraintGroupRow]:
    """The visible constraints of a project grouped by `owner`, `category` or `age`. Groups cover
    at most the first 500 visible constraints by key (the list limit of the view)."""
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
    return [
        ConstraintGroupRow(
            label=group.label,
            count=group.count,
            blocking=group.blocking,
            aging=group.aging,
            keys=list(group.keys),
        )
        for group in review_groups(views, by)
    ]


@router.get("/projects/{project}/constraints/{key}", operation_id="get_constraint_api")
def get_constraint_api(ctx: Ctx, actor: Reader, project: str, key: str) -> ConstraintView:
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
        return found
