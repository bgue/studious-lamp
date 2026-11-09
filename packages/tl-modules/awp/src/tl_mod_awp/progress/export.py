"""The progress CSV by cost code (P2-I5 S3): ``export_progress`` over ``progress_rollup``.

Reads only. Every cell is text and goes through the ``csv`` module with ``QUOTE_ALL``; a cell whose
first character could start a formula in a spreadsheet gets a leading apostrophe (``csv_cell``).
The CSV is built in memory; its size is bounded by ``MAX_ROWS`` cost code lines (a longer one is
refused). A viewer, a system viewer included, takes the viewer path of ``progress_rollup``: the
budgets are computed from what it can open, never read from the stored rows.
"""

from __future__ import annotations

import csv
import io
import re
from decimal import Decimal
from fractions import Fraction
from typing import Final

from sqlalchemy import Connection
from tl_core.confidentiality import Viewer

from tl_mod_awp.progress.engine import round_half_up
from tl_mod_awp.progress.rollup import progress_rollup

PERIOD_PATTERN: Final = r"^[0-9]{4}-W(0[1-9]|[1-4][0-9]|5[0-3])$"
HEADER: Final = (
    "period",
    "scope",
    "cost_code",
    "earned_hours",
    "budget_hours",
    "earned_pct",
    "as_of_seq",
)
UNALLOCATED: Final = "Unallocated"
MSG_PERIOD: Final = "period: expected YYYY-Www"
MSG_TOO_MANY: Final = "export: too many rows"
#: At most this many cost code lines are written (the cost code limit of the awp reports).
MAX_ROWS: Final = 20000
_FORMULA_START: Final = ("=", "+", "-", "@", "\t", "\r")
_PERIOD = re.compile(PERIOD_PATTERN)


class ExportError(ValueError):
    """A refusal with a fixed text (never a cell of the input)."""


def csv_cell(value: object) -> str:
    """The text of one cell; a leading ``= + - @`` TAB or CR gets a leading apostrophe."""
    cell = "" if value is None else str(value)
    return f"'{cell}" if cell.startswith(_FORMULA_START) else cell


def _figure(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")


def export_progress(
    conn: Connection, scope: str, period: str, *, viewer: Viewer | None = None
) -> str:
    """Header, then one row per cost code line (the unallocated line last).

    ``ExportError`` for a period that is not ``YYYY-Www``. An empty cell is a null budget or pct.
    """
    if not isinstance(period, str) or _PERIOD.fullmatch(period) is None:
        raise ExportError(MSG_PERIOD)
    found = progress_rollup(conn, scope, viewer=viewer)
    if len(found.lines) > MAX_ROWS:
        raise ExportError(MSG_TOO_MANY)
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerow(HEADER)
    for line in found.lines:
        pct = None
        if line.budget_hours:
            pct = round_half_up(Fraction(line.earned_hours) / Fraction(line.budget_hours) * 100)
        writer.writerow(
            [
                csv_cell(period),
                csv_cell(scope),
                csv_cell(
                    UNALLOCATED if line.cost_code_id is None and line.code is None else line.code
                ),
                csv_cell(_figure(line.earned_hours)),
                csv_cell(_figure(line.budget_hours)),
                csv_cell(_figure(pct)),
                csv_cell(found.as_of_seq),
            ]
        )
    return buffer.getvalue()
