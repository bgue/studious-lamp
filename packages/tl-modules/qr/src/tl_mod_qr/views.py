"""Read views of scan codes (stub: T01 fills them; the provided test pins the interfaces).

``CodeRow`` holds the register fields and never the code or its hash. Names raise
``NotImplementedError`` until T01.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from tl_core import confidentiality
from tl_core.confidentiality import LOWEST, Viewer
from tl_core.util import utcnow

from tl_mod_qr.names import SCAN_CODE_TABLE

#: The most rows one listing returns.
_LIMIT: int = 100
_STATES: tuple[str, ...] = ("live", "revoked", "expired")


@dataclass(frozen=True)
class CodeRow:
    id: str
    label_text: str | None
    size: str
    issued_by: str
    issued_at: str
    expires_on: str | None
    state: str
    revoked_at: str | None
    replaced_by_id: str | None


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _state(revoked_at: Any, expires_on: Any, today: str) -> str:
    """The rule of ``resolve.py``: revoked when set, else expired when the date is before today."""
    if revoked_at is not None:
        return "revoked"
    if expires_on is not None and str(expires_on)[:10] < today:
        return "expired"
    return "live"


def _row(raw: RowMapping, today: str) -> CodeRow:
    return CodeRow(
        id=str(raw["id"]),
        label_text=_text(raw["label_text"]),
        size=str(raw["size"]),
        issued_by=str(raw["issued_by"]),
        issued_at=str(raw["issued_at"]),
        expires_on=_text(raw["expires_on"]),
        state=_state(raw["revoked_at"], raw["expires_on"], today),
        revoked_at=_text(raw["revoked_at"]),
        replaced_by_id=_text(raw["replaced_by_id"]),
    )


def codes_for_record(conn: Connection, record_id: str, *, viewer: Viewer = LOWEST) -> list[CodeRow]:
    """The codes of one record, newest first, at most 100 (T01)."""
    today = utcnow().date().isoformat()
    visible, extra = confidentiality.not_hidden("c.target_id", viewer)
    statement = text(
        "SELECT c.id, c.label_text, c.size, c.issued_by, c.issued_at, c.expires_on, "
        "c.revoked_at, c.replaced_by_id "
        f"FROM {SCAN_CODE_TABLE} c "
        f"WHERE c.target_id = :record AND {visible} "
        f"ORDER BY c.issued_at DESC, c.id DESC LIMIT {_LIMIT}"
    )
    params: dict[str, Any] = {"record": record_id, **extra}
    return [_row(raw, today) for raw in conn.execute(statement, params).mappings()]


def code_counts(conn: Connection, *, viewer: Viewer = LOWEST) -> dict[str, int]:
    """Counts by state: ``live``, ``revoked``, ``expired`` (T01)."""
    today = utcnow().date().isoformat()
    visible, extra = confidentiality.not_hidden("c.target_id", viewer)
    statement = text(
        "SELECT CASE WHEN c.revoked_at IS NOT NULL THEN 'revoked' "
        "WHEN c.expires_on IS NOT NULL AND substr(c.expires_on, 1, 10) < :today THEN 'expired' "
        "ELSE 'live' END AS state, COUNT(*) AS n "
        f"FROM {SCAN_CODE_TABLE} c WHERE {visible} GROUP BY 1"
    )
    params: dict[str, Any] = {"today": today, **extra}
    counts: dict[str, int] = dict.fromkeys(_STATES, 0)
    for raw in conn.execute(statement, params).mappings():
        counts[str(raw["state"])] = int(raw["n"])
    return counts


def export_rows(rows: list[CodeRow], fmt: Literal["csv", "jsonl"]) -> str:
    """The rows as CSV or JSON lines (T01)."""
    names = [field.name for field in dataclasses.fields(CodeRow)]
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(dataclasses.asdict(row))
        return buffer.getvalue()
    if fmt == "jsonl":
        return "".join(json.dumps(dataclasses.asdict(row)) + "\n" for row in rows)
    raise ValueError(f"unknown export format: {fmt}")
