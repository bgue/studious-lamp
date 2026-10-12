"""What a screen or a client reads about a tag: ``TagView`` (brief 9 M2; P1-I1).

The TUI client interface and the API client return this model, so an embedded screen and a remote
one see the same fields. ``issues`` is filled for one tag (``tag_view``), not for a listing.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlalchemy import Connection
from tl_core.services.psets import conformance
from tl_core.uow import UnitOfWork
from tl_schema.forms import ConformanceIssue

from tl_mod_engineering import registry
from tl_mod_engineering.errors import TagNotFoundError


class TagView(BaseModel):
    id: str
    number: str
    title: str
    class_code: str | None
    status: str | None
    area: str | None
    mnemonic: str | None
    sequence: int | None
    segments: dict[str, str]
    pattern_code: str | None
    number_status: str  # ok | violation
    violations: list[dict[str, Any]]
    origin: str
    conformance: str  # ok | warning | nonconformant | waived
    version: int
    psets: dict[str, Any]
    issues: list[ConformanceIssue] = []

    @classmethod
    def of(cls, row: registry.TagRow, issues: list[ConformanceIssue] | None = None) -> TagView:
        fields = {name: getattr(row, name) for name in cls.model_fields if name != "issues"}
        return cls(**fields, issues=issues or [])


def tag_views(
    conn: Connection,
    scope: str,
    *,
    class_code: str | None = None,
    status: str | None = None,
    number_status: str | None = None,
    include_ended: bool = False,
    limit: int = 1000,
) -> list[TagView]:
    """The tags of ``scope`` by number, with the filters given and no issues."""
    rows = registry.list_tags(
        conn,
        scope,
        class_code=class_code,
        status=status,
        number_status=number_status,
        include_ended=include_ended,
        limit=limit,
    )
    return [TagView.of(row) for row in rows]


def tag_view(uow: UnitOfWork, scope: str, number: str) -> TagView:
    """One tag with its conformance issues now. Raises ``TagNotFoundError`` when unknown."""
    row = registry.find_tag(uow.conn(), scope, number)
    if row is None:
        raise TagNotFoundError(f"no tag {number!r} in scope {scope!r}")
    return TagView.of(row, conformance(uow, row.id).issues)
