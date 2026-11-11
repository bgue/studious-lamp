"""Read views of the punch list (P2-PUNCH T01 fills the bodies; the interface is fixed here).

Every read takes keyword-only ``viewer=`` (default ``confidentiality.LOWEST``). Nothing here
reads the clock: an overdue filter takes ``today``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection
from tl_core import confidentiality


@dataclass(frozen=True)
class PunchRow:
    id: str  # the record id, for commands; no screen or line prints it
    key: str
    subject: str
    state: str
    category: str
    area: str | None
    system: str | None
    due_on: str | None
    assignee: str | None
    raised_by: str
    source_key: str | None


@dataclass(frozen=True)
class PunchDetail:
    row: PunchRow
    description: str | None
    cleared_by: str | None
    cleared_on: str | None
    clear_note: str | None
    verified_by: str | None
    verified_on: str | None
    reopen_count: int
    last_reopen_reason: str | None
    void_reason: str | None
    source_type: str | None
    version: int


@dataclass(frozen=True)
class PunchPage:
    rows: list[PunchRow]
    total: int


def punch_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    area: str | None = None,
    system: str | None = None,
    assignee: str | None = None,
    category: str | None = None,
    source_key: str | None = None,
    overdue: bool = False,
    today: str | None = None,
    limit: int = 200,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> PunchPage:
    """Visible items of ``scope`` by key; ``total`` counts the matches before ``limit``."""
    raise NotImplementedError


def punch_detail(
    conn: Connection,
    scope: str,
    key: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> PunchDetail | None:
    """One item; ``None`` when it is absent, in another project or hidden."""
    raise NotImplementedError


def punch_counts(
    conn: Connection,
    scope: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> dict[str, int]:
    """Visible items by state: ``Open``, ``Cleared``, ``Verified``, ``Void`` (each present)."""
    raise NotImplementedError


__all__ = [
    "PunchDetail",
    "PunchPage",
    "PunchRow",
    "punch_counts",
    "punch_detail",
    "punch_list",
]
