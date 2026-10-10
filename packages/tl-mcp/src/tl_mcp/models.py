"""Structured results of the tools (the schema agents see)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SearchResult(BaseModel):
    """One page of ``search_records``."""

    records: list[dict[str, Any]]  # record envelopes (id, key, type, title, status, psets, ...)
    total: int  # how many records match, ignoring limit and offset
    limit: int
    offset: int


class LakeQueryOutput(BaseModel):
    """The answer of ``lake_query``: rows plus the ledger seq the lake reflected (brief 28.3)."""

    columns: list[str]
    rows: list[list[Any]]  # JSON values, in column order
    row_count: int
    truncated: bool  # more rows existed than were returned
    truncated_by: str | None  # "limit" (row limit) or "bytes" (result size cap)
    limit: int
    as_of_seq: int  # the lake reflects the ledger up to this seq
    snapshot_id: int | None  # the DuckLake snapshot; use it with `AT (VERSION => n)`
    as_of: str  # a ready-made line: "as of seq 12 (snapshot 3)"
