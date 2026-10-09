"""Bulk loading into the lake through NDJSON files.

DuckDB's Python ``executemany`` is orders of magnitude slower than reading a file (7.6 s for 10 000
single-column rows against 0.16 s for 100 000 wide rows), so rows are written to a scratch NDJSON
file and inserted with ``INSERT ... SELECT FROM read_json``. The column types are declared, so the
file is parsed into the table's types and a malformed value fails the load instead of being guessed.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from tl_lake.duck import Duck, ident, sql_str, table_ref
from tl_lake.schema import Column

CHUNK_ROWS = 50_000


def _utc_naive(value: Any) -> str:
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC).replace(tzinfo=None)
    return moment.isoformat(timespec="microseconds")


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.isoformat(timespec="microseconds")
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    return str(value)


def to_json_value(duck_type: str, value: Any) -> Any:
    """``value`` as the JSON scalar DuckDB parses into ``duck_type``."""
    if value is None:
        return None
    if duck_type == "TIMESTAMP":
        return _utc_naive(value)
    if duck_type == "BOOLEAN":
        return bool(value)
    if duck_type == "BIGINT":
        return int(value)
    if duck_type == "DOUBLE":
        return float(value)
    if duck_type == "DATE":
        return value.isoformat() if isinstance(value, date) else str(value)
    return _text(value)


def _flush(
    con: Duck, table: str, columns: Sequence[Column], lines: list[str], tmp_dir: Path
) -> None:
    path = tmp_dir / f"{table}-{uuid4().hex}.ndjson"
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        spec = ", ".join(f"{sql_str(c.name)}: {sql_str(c.duck_type)}" for c in columns)
        names = ", ".join(ident(c.name) for c in columns)
        con.execute(
            f"INSERT INTO {table_ref(table)} ({names}) SELECT {names} FROM "
            f"read_json({sql_str(str(path))}, format = 'newline_delimited', columns = {{{spec}}})"
        )
    finally:
        path.unlink(missing_ok=True)


def insert_rows(
    con: Duck,
    table: str,
    columns: Sequence[Column],
    rows: Iterable[Mapping[str, Any]],
    tmp_dir: Path,
    *,
    chunk: int = CHUNK_ROWS,
) -> int:
    """Insert ``rows`` (mappings by column name) into lake table ``table``; returns the count."""
    lines: list[str] = []
    total = 0
    for row in rows:
        converted = {c.name: to_json_value(c.duck_type, row[c.name]) for c in columns}
        lines.append(json.dumps(converted, ensure_ascii=False, allow_nan=False))
        if len(lines) >= chunk:
            _flush(con, table, columns, lines, tmp_dir)
            total += len(lines)
            lines = []
    if lines:
        _flush(con, table, columns, lines, tmp_dir)
        total += len(lines)
    return total


def delete_keys(
    con: Duck, table: str, key: str, keys: Iterable[str], tmp_dir: Path, *, chunk: int = CHUNK_ROWS
) -> None:
    """DELETE every row of ``table`` whose ``key`` column is in ``keys``."""
    for batch in batched(keys, chunk):
        path = tmp_dir / f"{table}-keys-{uuid4().hex}.ndjson"
        try:
            path.write_text("\n".join(json.dumps({"k": k}) for k in batch) + "\n", encoding="utf-8")
            con.execute(
                f"DELETE FROM {table_ref(table)} WHERE {ident(key)} IN "
                f"(SELECT k FROM read_json({sql_str(str(path))}, format = 'newline_delimited', "
                "columns = {'k': 'VARCHAR'}))"
            )
        finally:
            path.unlink(missing_ok=True)


def batched(items: Iterable[str], size: int) -> Iterator[list[str]]:
    batch: list[str] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
