"""Event types whose dots fall in different places must not share an operation key."""

from __future__ import annotations

import pytest
from tl_schema.catalog_asyncapi import asyncapi_document
from tl_schema.catalog_types import EventTypeInfo


def info(event_type: str) -> EventTypeInfo:
    return EventTypeInfo(
        event_type=event_type,
        version=1,
        ce_type=f"tl.core.{event_type}.v1",
        title="t.",
        description="t.",
        payload_class="P",
        payload_schema={},
        envelope_schema={},
        sample_payload={},
        sample_envelope={},
    )


def test_operation_key_collisions_are_refused_like_duplicates() -> None:
    with pytest.raises(ValueError, match="collide"):
        asyncapi_document([info("A.BC"), info("AB.C")])


def test_distinct_operation_keys_are_fine() -> None:
    assert len(asyncapi_document([info("A.BC"), info("A.BD")])["operations"]) == 2
