"""Read views of scan codes (stub: T01 fills them; the provided test pins the interfaces).

``CodeRow`` holds the register fields and never the code or its hash. Names raise
``NotImplementedError`` until T01.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Connection
from tl_core.confidentiality import LOWEST, Viewer


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


def codes_for_record(conn: Connection, record_id: str, *, viewer: Viewer = LOWEST) -> list[CodeRow]:
    """The codes of one record, newest first, at most 100 (T01)."""
    raise NotImplementedError("T01")


def code_counts(conn: Connection, *, viewer: Viewer = LOWEST) -> dict[str, int]:
    """Counts by state: ``live``, ``revoked``, ``expired`` (T01)."""
    raise NotImplementedError("T01")


def export_rows(rows: list[CodeRow], fmt: Literal["csv", "jsonl"]) -> str:
    """The rows as CSV or JSON lines (T01)."""
    raise NotImplementedError("T01")
