"""The materials module's reports for ``tl report`` (V3-P0): the existing ``tl mat report`` tables
except ``heat_trace`` (it needs a heat number, which ``tl report`` does not take).

Registered here, not in ``tl_mod_materials``, because ``consumables_by_cost_code`` needs the cost
module's codes (the same read ``tl mat report`` makes). Each report is ``build_report``; the cells
are its text cells. A view that hit its row bound (``truncated``) is cut the same way as in
``tl mat report``.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final

from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.modules import Report
from tl_mod_cost import views as cost_views
from tl_mod_materials.reports import _COLUMNS, REPORT_NAMES, build_report

_TITLES: Final = {
    "stock_on_hand": "Stock on hand",
    "movement_log": "Stock movements",
    "mto_status": "Material take-off status",
    "shortages": "Shortages",
    "consumables_by_cost_code": "Consumables by cost code",
}


def _make(name: str) -> Report:
    columns = _COLUMNS[name]

    def rows(
        conn: Connection, scope: str, viewer: confidentiality.Viewer
    ) -> Iterator[Mapping[str, Any]]:
        codes = {c.id: c.code for c in cost_views.cost_codes(conn, scope)}
        built = build_report(conn, scope, name, cost_codes=codes)
        for cells in built.rows:
            yield dict(zip(columns, cells, strict=True))

    return Report(f"materials-{name.replace('_', '-')}", _TITLES[name], columns, rows)


REPORTS: Final = tuple(_make(n) for n in REPORT_NAMES if n != "heat_trace")
