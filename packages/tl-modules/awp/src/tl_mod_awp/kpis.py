"""The two KPI tiles of the weekly cycle (P2-I5-T09): PPC and percent constraint-free.

Reads only, through the viewer's class filter; figures are counts, one decimal, half-up
(``progress.engine.round_half_up``); a figure with nothing to count is ``None``, never ``0.0``.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Final

from pydantic import BaseModel
from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.confidentiality import Viewer

from tl_mod_awp import iwp_views, week_views
from tl_mod_awp.actions import IWP_LIVE_STATES
from tl_mod_awp.look_ahead_view import _open_blocking
from tl_mod_awp.progress import engine

#: The tile and report names (``tl awp report <name>``); the order is the order of ``kpi_rows``.
KPI_NAMES: Final = ("kpi_ppc", "kpi_constraint_free")
#: The most closed weeks the PPC tile pools.
PPC_WEEKS: Final = 4
#: The most weekly plans the PPC tile reads when it looks for the closed ones.
_PLAN_LIMIT: Final = 520
#: The most IWPs the constraint-free tile reads (the view clamps to 500).
_IWP_LIMIT: Final = 500


class KpiTile(BaseModel):
    """One tile: ``value`` is a percentage with one decimal (``None``: nothing to count)."""

    name: str  # one of KPI_NAMES
    value: Decimal | None
    numerator: int
    denominator: int
    detail: str  # plain words, for example "4 of 5 committed IWPs done, last 2 closed weeks"


def ppc_tile(conn: Connection, scope: str, viewer: Viewer, *, weeks: int = PPC_WEEKS) -> KpiTile:
    """PPC pooled over the last ``weeks`` Closed plans the viewer may read: IWPs done over IWPs
    committed (visible commitments only), by count, through ``progress.engine.ppc``."""
    with confidentiality.use_viewer(viewer):
        closed = [
            w
            for w in week_views.list_weeks(conn, scope, viewer, limit=_PLAN_LIMIT)
            if w.state == "Closed"
        ][: max(0, weeks)]
        done = committed = 0
        for plan in closed:
            for c in week_views.week_detail(conn, plan.id, viewer).commitments:
                committed += 1
                done += 1 if c.outcome == "done" else 0
    value, _ = engine.ppc(done, committed)
    if value is None:
        detail = "nothing committed in closed weeks" if closed else "no closed week yet"
    else:
        detail = f"{done} of {committed} IWPs done, last {len(closed)} closed weeks"
    return KpiTile(
        name="kpi_ppc", value=value, numerator=done, denominator=committed, detail=detail
    )


def constraint_free_tile(conn: Connection, scope: str, viewer: Viewer) -> KpiTile:
    """Percent of the live IWPs (``actions.IWP_LIVE_STATES``, readable by the viewer) with no
    Open or Assigned blocking constraint the viewer may read."""
    with confidentiality.use_viewer(viewer):
        live = [
            iwp.id
            for iwp in iwp_views.iwp_list(conn, scope, limit=_IWP_LIMIT)
            if iwp.state in IWP_LIVE_STATES
        ]
        blocking = _open_blocking(conn, scope, viewer, set(live)) if live else {}
    denominator = len(live)
    numerator = sum(1 for iwp_id in live if blocking.get(iwp_id, 0) == 0)
    if denominator == 0:
        value: Decimal | None = None
        detail = "no live IWP"
    else:
        value = engine.round_half_up(Fraction(numerator * 100, denominator))
        detail = f"{numerator} of {denominator} IWPs"
    return KpiTile(
        name="kpi_constraint_free",
        value=value,
        numerator=numerator,
        denominator=denominator,
        detail=detail,
    )


def kpi_rows(conn: Connection, scope: str, viewer: Viewer) -> list[KpiTile]:
    """Both tiles, in ``KPI_NAMES`` order."""
    return [ppc_tile(conn, scope, viewer), constraint_free_tile(conn, scope, viewer)]
