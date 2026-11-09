"""The look-ahead joined with the IWPs linked to each activity and their readiness (P2-I5-T03).

STUB: the interface is fixed here; T03 writes the body. Reads only; ids and counts only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import Connection
from tl_core.confidentiality import Viewer
from tl_mod_schedule.lookahead import LookAheadRow
from tl_mod_schedule.registry import SnapshotRow


@dataclass(frozen=True)
class LookAheadIwp:
    id: str
    number: str
    state: str
    planned_start: str | None
    need_by: str | None  # planned_start minus awp.iwp.ready_lead_weeks weeks (ISO date)
    evaluated: bool  # False: never evaluated (then ready False, checks 0/0)
    ready: bool
    checks_ok: int  # checks in state ok or n_a
    checks_total: int
    open_blocking: int  # Open or Assigned blocking constraints the viewer may read


@dataclass(frozen=True)
class LookAheadItem:
    row: LookAheadRow
    iwps: tuple[LookAheadIwp, ...]  # by IWP number


@dataclass(frozen=True)
class LookAheadView:
    snapshot_key: str
    data_date: str
    window_start: str
    window_end: str
    weeks: int
    lead_weeks: int
    counts: Mapping[str, int]  # the look_ahead counts
    items: tuple[LookAheadItem, ...]  # the look_ahead rows, same order


def look_ahead_view(
    conn: Connection,
    scope: str,
    snapshot: SnapshotRow,
    viewer: Viewer | None = None,
    *,
    weeks: int = 4,
) -> LookAheadView:
    raise NotImplementedError("P2-I5-T03")  # STEPS in the ticket
