"""What a screen, a client or an agent reads about cost codes and cost snapshots (brief 9 M11).

The API (and so the API client), the CLI and the MCP tools return these models. Every function
here only reads, and none checks a role (the entry points need ``document.read``).
"""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import Connection

from tl_mod_cost import registry
from tl_mod_cost.errors import CostCodeNotFoundError
from tl_mod_cost.names import MEASURE_COLUMNS

MAX_CODES = 20_000


class CostCodeView(BaseModel):
    """A cost code with the latest figures a snapshot stated for it."""

    id: str
    code: str
    title: str
    parent_code: str | None
    level: int
    uom: str | None
    is_active: bool
    period: str | None  # the snapshot the figures come from
    as_of: str | None
    figures: dict[str, float | None]

    @classmethod
    def of(cls, row: registry.CostCodeRow) -> CostCodeView:
        return cls(
            id=row.id,
            code=row.code,
            title=row.title,
            parent_code=row.parent_code,
            level=row.level,
            uom=row.uom,
            is_active=row.is_active,
            period=row.period,
            as_of=row.as_of,
            figures=row.figures,
        )


class SnapshotValueView(BaseModel):
    """What one snapshot said about one code."""

    period: str
    revision: int
    as_of: str
    figures: dict[str, float | None]


class CostCodeDetailView(CostCodeView):
    """A code with its children's codes and the figures of every snapshot, oldest first."""

    children: list[str]
    history: list[SnapshotValueView]


class CostSnapshotView(BaseModel):
    id: str
    period: str
    revision: int
    key: str  # period@revision
    as_of: str
    currency: str | None
    source_name: str | None
    source_sha256: str | None
    row_count: int
    new_code_count: int
    revised_code_count: int
    created_at: str

    @classmethod
    def of(cls, row: registry.CostSnapshotRow) -> CostSnapshotView:
        return cls(
            id=row.id,
            period=row.period,
            revision=row.revision,
            key=f"{row.period}@{row.revision}",
            as_of=row.as_of,
            currency=row.currency,
            source_name=row.source_name,
            source_sha256=row.source_sha256,
            row_count=row.row_count,
            new_code_count=row.new_code_count,
            revised_code_count=row.revised_code_count,
            created_at=row.created_at,
        )


def cost_codes(
    conn: Connection,
    scope: str,
    *,
    parent: str | None = None,
    search: str | None = None,
    limit: int = 1000,
) -> list[CostCodeView]:
    """The cost codes of a scope by code. ``parent`` keeps the direct children of one code,
    ``search`` the codes whose code or title holds a text (any case). At most ``limit``."""
    needle = search.lower() if search else None
    found: list[CostCodeView] = []
    for row in registry.list_cost_codes(conn, scope):
        if parent is not None and row.parent_code != parent:
            continue
        if (
            needle is not None
            and needle not in row.code.lower()
            and needle not in row.title.lower()
        ):
            continue
        found.append(CostCodeView.of(row))
        if len(found) >= max(1, min(limit, MAX_CODES)):
            break
    return found


def cost_code_detail(conn: Connection, scope: str, code: str) -> CostCodeDetailView:
    row = registry.get_cost_code(conn, scope, code)
    if row is None:
        raise CostCodeNotFoundError(f"no cost code {code!r} in {scope}")
    children = [c.code for c in registry.list_cost_codes(conn, scope) if c.parent_code == code]
    history = [
        SnapshotValueView(period=v.period, revision=v.revision, as_of=v.as_of, figures=v.figures)
        for v in registry.code_history(conn, row.id)
    ]
    return CostCodeDetailView(
        **CostCodeView.of(row).model_dump(), children=children, history=history
    )


def cost_snapshots(conn: Connection, scope: str) -> list[CostSnapshotView]:
    """The snapshots of a scope, newest period and revision first."""
    return [CostSnapshotView.of(s) for s in registry.list_snapshots(conn, scope)]


__all__ = [
    "MEASURE_COLUMNS",
    "CostCodeDetailView",
    "CostCodeView",
    "CostSnapshotView",
    "SnapshotValueView",
    "cost_code_detail",
    "cost_codes",
    "cost_snapshots",
]
