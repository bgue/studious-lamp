"""Canonical JSON, UTC timestamp formatting, and the per-scope event hash chain (brief §5.1)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any


def canonical_json(payload: Mapping[str, Any]) -> str:
    """json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)"""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def iso_utc(moment: datetime) -> str:
    """Timezone-aware datetimes only (raise ValueError for naive). Convert to UTC and return
    moment.astimezone(UTC).isoformat(timespec="microseconds"),
    e.g. '2026-01-01T00:00:00.000000+00:00'."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("iso_utc requires a timezone-aware datetime")
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def event_hash(
    prev_hash: str | None,
    event_id: str,
    stream_id: str,
    stream_version: int,
    event_type: str,
    payload_canonical_json: str,
    recorded_at_iso: str,
) -> str:
    """SHA-256 hex over the concatenation with '\\n' separators; prev_hash '' when None.
    Chain is per scope: prev_hash is the hash of the previous event in the same scope."""
    parts = [
        prev_hash or "",
        event_id,
        stream_id,
        str(stream_version),
        event_type,
        payload_canonical_json,
        recorded_at_iso,
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
