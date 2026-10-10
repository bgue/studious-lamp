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
