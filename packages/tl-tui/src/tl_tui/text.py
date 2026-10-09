"""Small display-text helpers shared by widgets (brief 10.3: status as text and symbol)."""

from __future__ import annotations

import json
from typing import Any

EMPTY = "—"
CONFORMANCE_MARK = {"ok": "✓ ok", "warning": "! warning", "nonconformant": "✗ nonconformant"}


def short_hash(value: str | None) -> str:
    """``#a91f…3c`` for a content hash (first 4 and last 2 characters), ``—`` when absent."""
    if not value:
        return EMPTY
    return f"#{value[:4]}…{value[-2:]}"


def timestamp(value: str | None) -> str:
    """``2026-10-09 09:05`` from an ISO timestamp string, ``—`` when absent."""
    if not value:
        return EMPTY
    return value[:16].replace("T", " ")


def conformance_mark(value: str | None) -> str:
    """The conformance level with its symbol, for example ``✗ nonconformant``."""
    return CONFORMANCE_MARK.get(str(value), str(value))


def format_value(value: Any) -> str:
    if value is None or value == "":
        return EMPTY
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)
