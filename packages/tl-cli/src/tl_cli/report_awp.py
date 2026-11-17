"""The awp module's line-level reports for ``tl report`` (V3-P0): the existing ``tl awp report``
tables that list records (the KPI tiles and the grouped constraint counts are totals, not lines).

Registered here, not in ``tl_mod_awp``, because ``wbs_vs_cost_code`` needs the cost module's codes
(the same read ``tl awp report`` makes). Each row is the existing report's own row, so the numbers
match ``tl awp report NAME`` for the same viewer.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any, Final

from pydantic import BaseModel
from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.modules import Report
from tl_mod_awp import iwp_reports, reports

from tl_cli.awp_report import _cost_figures


def _make(
    name: str,
    title: str,
    model: type[BaseModel],
    read: Callable[[Connection, str], Sequence[BaseModel]],
) -> Report:
    def rows(
        conn: Connection, scope: str, viewer: confidentiality.Viewer
    ) -> Iterator[Mapping[str, Any]]:
        for row in read(conn, scope):
            yield row.model_dump()

    return Report(name, title, tuple(model.model_fields), rows)


def _wbs(conn: Connection, scope: str) -> Sequence[BaseModel]:
    return reports.wbs_vs_cost_code(conn, scope, _cost_figures(conn, scope.split(":", 1)[1]))


REPORTS: Final = (
    _make("awp-cwp-status", "CWPs by state and discipline", reports.StatusRow, reports.cwp_status),
    _make("awp-wbs-vs-cost-code", "WBS hours against cost codes", reports.CostRow, _wbs),
    _make("awp-cwa-sequence", "CWAs in sequence", reports.SequenceRow, reports.cwa_sequence),
    _make(
        "awp-iwp-status",
        "IWPs by state and discipline",
        iwp_reports.IwpStatusRow,
        iwp_reports.iwp_status,
    ),
    _make(
        "awp-iwp-readiness",
        "IWP readiness",
        iwp_reports.IwpReadinessRow,
        iwp_reports.iwp_readiness,
    ),
    _make(
        "awp-constraint-log",
        "Constraint log",
        iwp_reports.ConstraintLogRow,
        iwp_reports.constraint_log,
    ),
)
