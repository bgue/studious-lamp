"""The two KPI tiles of the weekly cycle (P2-I5-T09): PPC and percent constraint-free.

STUB: the bodies raise ``NotImplementedError``; T09 writes them and removes this note. Reads only,
through the viewer's class filter; figures are counts, one decimal, half-up
(``progress.engine.round_half_up``); a figure with nothing to count is ``None``, never ``0.0``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from pydantic import BaseModel
from sqlalchemy import Connection
from tl_core.confidentiality import Viewer

#: The tile and report names (``tl awp report <name>``); the order is the order of ``kpi_rows``.
KPI_NAMES: Final = ("kpi_ppc", "kpi_constraint_free")
#: The most closed weeks the PPC tile pools.
PPC_WEEKS: Final = 4


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
    raise NotImplementedError


def constraint_free_tile(conn: Connection, scope: str, viewer: Viewer) -> KpiTile:
    """Percent of the live IWPs (``actions.IWP_LIVE_STATES``, readable by the viewer) with no
    Open or Assigned blocking constraint the viewer may read."""
    raise NotImplementedError


def kpi_rows(conn: Connection, scope: str, viewer: Viewer) -> list[KpiTile]:
    """Both tiles, in ``KPI_NAMES`` order."""
    raise NotImplementedError
