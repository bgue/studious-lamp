"""Check the child's answer before anything uses it (P1-I4-T03).

The child is our own code in a process of its own, but it reads a stranger's bytes: if a parser
bug ever gave the stranger control of it, the answer would be the stranger's. So the parent does
not believe it. Every length is checked against the payload, the report is rebuilt from known keys
with bounded values, the SHA-256 of the typed frame is recomputed, every cell of every typed row is
checked against its column kind, and the raw bundle is inflated (bounded) and hashed. Any
disagreement is ``XerLimitError("crash")``: the same fixed refusal as a child that died.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, cast

from tl_xer import limits
from tl_xer.bundle import BundleError, verify_bundle
from tl_xer.process import CP1252_NOTE, Status
from tl_xer.reader import FORBIDDEN
from tl_xer.result import XerLimitError, XerResult
from tl_xer.typed import COLUMN_KINDS, PROJECT_KEYS, TABLE_COLUMNS, TABLE_LIMITS, Snapshot

STATUSES: tuple[Status, ...] = ("valid", "invalid", "refused")


def _take(payload: memoryview, at: int) -> tuple[memoryview, int]:
    """The frame at ``at`` as a view of the payload (no copy), and where the next one starts."""
    if at + 8 > len(payload):
        raise XerLimitError("crash")
    size = int.from_bytes(payload[at : at + 8], "big")
    end = at + 8 + size
    if end > len(payload):
        raise XerLimitError("crash")
    return payload[at + 8 : end], end


def decode(answer: bytes | memoryview) -> XerResult:
    """The checked result of an answer payload (see ``tl_xer.child``).

    The frames are views of the payload, never slices: the typed frame is hashed where it lies and
    read once as text, and only the raw bundle is copied (the result keeps it).
    """
    payload = memoryview(answer)
    meta_bytes, at = _take(payload, 0)
    typed_bytes, at = _take(payload, at)
    raw_gz = payload[at:]
    try:
        meta = _dict(json.loads(str(meta_bytes, "utf-8")))
        report = _check_report(meta["report"])
        status = cast(Status, report["status"])
        if status != "valid":
            if typed_bytes or raw_gz:
                raise XerLimitError("crash")
            return XerResult(status, report)
        typed_sha, raw_sha = meta["typed_sha256"], meta["raw_sha256"]
        if hashlib.sha256(typed_bytes).hexdigest() != typed_sha or not _is_digest(raw_sha):
            raise XerLimitError("crash")
        snapshot = _check_snapshot(json.loads(str(typed_bytes, "utf-8")))
        kept = bytes(raw_gz)
        verify_bundle(kept, raw_sha)
    except (ValueError, KeyError, TypeError, BundleError, RecursionError, MemoryError):
        raise XerLimitError("crash") from None
    return XerResult(status, report, snapshot, typed_sha, kept, raw_sha)


# --- small typed checks ----------------------------------------------------------------------


def _dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("not an object")
    return cast(dict[str, Any], value)


def _list(value: Any, bound: int) -> list[Any]:
    if not isinstance(value, list) or len(cast(list[Any], value)) > bound:
        raise ValueError("not a list, or too long")
    return cast(list[Any], value)


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _text(value: Any, bound: int) -> str:
    if not isinstance(value, str) or len(value) > bound:
        raise ValueError("bad text")
    return value


def _optional_text(value: Any, bound: int) -> str | None:
    return None if value is None else _text(value, bound)


def _count(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 10**9:
        raise ValueError("bad count")
    return value


# --- the report ------------------------------------------------------------------------------


def _check_problem(item: Any) -> dict[str, Any]:
    found = _dict(item)
    if found.get("severity") not in ("error", "warning"):
        raise ValueError("severity")
    row = found.get("row")
    return {
        "severity": found["severity"],
        "code": _text(found.get("code"), limits.MAX_NAME_CHARS),
        "message": _text(found.get("message"), limits.MAX_MESSAGE_CHARS),
        "table": _optional_text(found.get("table"), limits.MAX_NAME_CHARS),
        "row": None if row is None else _count(row),
        "field": _optional_text(found.get("field"), limits.MAX_NAME_CHARS),
    }


def _check_report(value: Any) -> dict[str, Any]:
    """Rebuild the report from the child's, keeping only known keys with checked values."""
    given = _dict(value)
    status = given.get("status")
    if status not in STATUSES:
        raise ValueError("status")
    counts = _dict(given.get("counts"))
    if len(counts) > limits.MAX_NAME_CHARS:
        raise ValueError("counts")
    project = given.get("project")
    return {
        "report_version": _count(given.get("report_version")),
        "status": status,
        "p6_version": _optional_text(given.get("p6_version"), limits.MAX_HEADER_FIELD_CHARS),
        "encoding": _optional_text(given.get("encoding"), 20),
        "encoding_note": _encoding_note(given.get("encoding_note")),
        "project_option": _optional_text(given.get("project_option"), limits.MAX_ID_CHARS),
        "project": None if project is None else _check_project(project),
        "counts": {_text(k, limits.MAX_NAME_CHARS): _count(v) for k, v in counts.items()},
        "tables": [
            {
                "name": _text(_dict(t).get("name"), limits.MAX_NAME_CHARS),
                "columns": _count(_dict(t).get("columns")),
                "rows": _count(_dict(t).get("rows")),
            }
            for t in _list(given.get("tables"), limits.MAX_TABLES)
        ],
        "error_count": _count(given.get("error_count")),
        "warning_count": _count(given.get("warning_count")),
        "problem_count": _count(given.get("problem_count")),
        "truncated": bool(given.get("truncated")),
        "problems": [_check_problem(p) for p in _list(given.get("problems"), limits.MAX_PROBLEMS)],
    }


def _encoding_note(value: Any) -> str | None:
    if value is not None and value != CP1252_NOTE:
        raise ValueError("encoding note")
    return value


def _check_project(value: Any) -> dict[str, Any]:
    given = _dict(value)
    if set(given) != set(PROJECT_KEYS):
        raise ValueError("project")
    found: dict[str, Any] = {}
    for key in PROJECT_KEYS:
        item = given[key]
        found[key] = (
            _count(item) if key == "other_projects" else _optional_text(item, limits.MAX_ID_CHARS)
        )
    return found


# --- the typed snapshot ----------------------------------------------------------------------


def _check_cell(kind: str, cell: Any) -> None:
    if kind in "sS":
        if cell is None and kind == "S":
            return
        if (
            not isinstance(cell, str)
            or len(cell) > limits.MAX_FIELD_CHARS
            or FORBIDDEN.search(cell) is not None  # the reader refused these: nothing may add them
        ):
            raise ValueError("text cell")
    elif kind in "fF":
        if cell is None and kind == "F":
            return
        if isinstance(cell, bool) or not isinstance(cell, (int, float)) or not math.isfinite(cell):
            raise ValueError("number cell")
    elif kind == "b":
        if not isinstance(cell, bool):
            raise ValueError("boolean cell")
    elif kind == "i":
        if isinstance(cell, bool) or not isinstance(cell, int):
            raise ValueError("integer cell")
    else:  # pragma: no cover - the kinds are constants
        raise ValueError("kind")


def _check_snapshot(value: Any) -> Snapshot:
    given = _dict(value)
    if set(given) != {"project", "tables"}:
        raise ValueError("snapshot")
    project = _check_project(given["project"])
    tables = _dict(given["tables"])
    if set(tables) != set(TABLE_COLUMNS):
        raise ValueError("tables")
    snapshot = Snapshot(project=project)
    for name, columns in TABLE_COLUMNS.items():
        table = _dict(tables[name])
        if table.get("columns") != list(columns):
            raise ValueError("columns")
        kinds = COLUMN_KINDS[name]
        rows = _list(table.get("rows"), TABLE_LIMITS[name])
        for index, row in enumerate(rows):
            cells = _list(row, len(kinds))
            for kind, cell in zip(kinds, cells, strict=True):  # strict: a short row is an error
                _check_cell(kind, cell)
            rows[index] = tuple(cells)  # in place: the list of the row is freed at once
        snapshot.tables[name] = cast(list[tuple[Any, ...]], rows)
    return snapshot
