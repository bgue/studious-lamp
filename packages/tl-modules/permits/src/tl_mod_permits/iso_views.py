"""Read views of isolations and gas tests (P2-PTW T02). A stub: S3 pins the names and the shapes the
provided test (``tests/test_iso_views.py``) reads; every function raises ``NotImplementedError``
until T02 writes it. Nothing imports this module yet.

Every view filters hidden records first, before ``LIMIT`` and before any count, for a ``viewer``
that defaults to the lowest clearance (``tl_core.confidentiality.LOWEST``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Connection
from tl_core import confidentiality as cf

ISOLATION_EXPORT_COLUMNS = (
    "number",
    "point",
    "energy",
    "method",
    "lock",
    "tag",
    "state",
    "applied_by",
    "applied",
    "verified_by",
    "verified",
    "depends",
)
GAS_EXPORT_COLUMNS = (
    "number",
    "taken",
    "tester",
    "instrument",
    "o2_pct",
    "lel_pct",
    "h2s_ppm",
    "co_ppm",
    "result",
    "note",
)


@dataclass(frozen=True)
class IsolationRow:
    """One isolation. ``depends`` counts the permits the viewer can read that link it and have
    not unlinked it while Approved, Active or Suspended (``guards.dependent_permits``)."""

    id: str
    key: str
    point_text: str
    energy: str
    method: str | None
    lock_number: str | None
    tag_number: str | None
    state: str
    applied_by: str
    applied_at: datetime
    verified_by: str | None
    verified_at: datetime | None
    depends: int


@dataclass(frozen=True)
class IsolationPage:
    rows: list[IsolationRow]
    total: int


@dataclass(frozen=True)
class IsolationDetail:
    row: IsolationRow
    point_record_id: str | None
    removed_by: str | None
    removed_at: datetime | None
    version: int
    permits: list[str] = field(default_factory=list[str])  # keys of the readable dependents


@dataclass(frozen=True)
class GasRow:
    id: str
    key: str
    taken_at: datetime
    tester: str
    instrument_text: str | None
    o2_pct: Decimal | None
    lel_pct: Decimal | None
    h2s_ppm: Decimal | None
    co_ppm: Decimal | None
    result: str
    note: str | None


def isolation_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    energy: str | None = None,
    limit: int = 100,
    viewer: cf.Viewer = cf.LOWEST,
) -> IsolationPage:
    """The isolations of ``scope`` the viewer can read, by key; ``total`` counts the same set."""
    raise NotImplementedError("T02")


def isolation_detail(
    conn: Connection, scope: str, key: str, *, viewer: cf.Viewer = cf.LOWEST
) -> IsolationDetail | None:
    """The isolation numbered ``key``, or ``None`` when absent, elsewhere or hidden."""
    raise NotImplementedError("T02")


def gas_tests_for(
    conn: Connection, permit_id: str, *, viewer: cf.Viewer = cf.LOWEST
) -> list[GasRow]:
    """The gas tests of a permit, newest first; none when the permit (so its tests) is hidden."""
    raise NotImplementedError("T02")


def gas_export_rows(rows: Sequence[GasRow], fmt: str) -> str:
    """``rows`` as ``csv`` (header, then a line per row) or ``jsonl``; ``ValueError`` otherwise."""
    raise NotImplementedError("T02")


def isolation_export_rows(rows: Sequence[IsolationRow], fmt: str) -> str:
    """``rows`` as ``csv`` (header, then a line per row) or ``jsonl``; ``ValueError`` otherwise."""
    raise NotImplementedError("T02")


__all__ = [
    "GAS_EXPORT_COLUMNS",
    "ISOLATION_EXPORT_COLUMNS",
    "GasRow",
    "IsolationDetail",
    "IsolationPage",
    "IsolationRow",
    "gas_export_rows",
    "gas_tests_for",
    "isolation_detail",
    "isolation_export_rows",
    "isolation_list",
]
