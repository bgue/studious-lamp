"""AsyncAPI 3.0 document of the event catalog (brief 18.3).

STUB (P0-I5-T20): ``asyncapi_document`` raises ``NotImplementedError``. The specification is the
ticket and the provided test.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from tl_schema.catalog_types import EventTypeInfo

ASYNCAPI_VERSION = "3.0.0"


def asyncapi_document(
    events: Sequence[EventTypeInfo],
    *,
    title: str = "Throughline events",
    version: str = "1.0.0",
) -> dict[str, Any]:
    """The AsyncAPI 3.0 document for ``events``. Pure and deterministic. See the ticket."""
    raise NotImplementedError
