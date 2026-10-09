"""Browsable Markdown page of the event catalog (brief 18.3).

STUB (P0-I5-T21): ``render_catalog_markdown`` raises ``NotImplementedError``. The specification is
the ticket and the provided test.
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_schema.catalog_types import EventTypeInfo


def render_catalog_markdown(
    events: Sequence[EventTypeInfo], *, title: str = "Throughline event catalog"
) -> str:
    """The catalog page for ``events``. Pure and deterministic. See the ticket."""
    raise NotImplementedError
