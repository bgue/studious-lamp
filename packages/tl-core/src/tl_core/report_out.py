"""Write a module ``Report`` as CSV or JSON lines (``tl report``; V3-P0).

The rows come from the module's own list view read as the viewer, so a hidden record is not in them
and nothing here counts, pads or marks a gap. Dates are ISO, an empty value is empty (CSV) or null
(JSONL), and a CSV cell that a spreadsheet would run as a formula gets a leading quote (the text is
somebody else's).
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from itertools import chain
from typing import Any

from sqlalchemy import Connection

from tl_core import confidentiality
from tl_core.modules import Report

FORMATS = ("csv", "jsonl")
_FORMULA_STARTS = ("=", "+", "-", "@", "|", "\t", "\r")


def plain(value: Any) -> Any:
    """``value`` as a JSON-safe scalar: dates ISO, numbers and booleans as they are, else text."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        return value
    return str(value)


def csv_cell(value: Any) -> str:
    was_text = isinstance(value, str)
    value = plain(value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if was_text and text.startswith(_FORMULA_STARTS):
        return "'" + text  # only text is somebody else's: a number stays -5
    return text


def _line(cells: list[str]) -> str:
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerow(cells)
    return out.getvalue()


def render(
    report: Report,
    conn: Connection,
    scope: str,
    viewer: confidentiality.Viewer,
    fmt: str = "csv",
) -> Iterator[str]:
    """The report's text, one string per line (the header first for CSV), read as ``viewer``."""
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")
    columns = list(report.columns)
    with confidentiality.use_viewer(viewer):
        # Start the rows first: a refusal (a module's view word) comes before any header line.
        rows = iter(report.rows(conn, scope, viewer))
        first = next(rows, None)
        if fmt == "csv":
            yield _line(columns)
        for row in chain([] if first is None else [first], rows):
            if fmt == "csv":
                yield _line([csv_cell(row.get(c)) for c in columns])
            else:
                yield json.dumps({c: plain(row.get(c)) for c in columns}) + "\n"
