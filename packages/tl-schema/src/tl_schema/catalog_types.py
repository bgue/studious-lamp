"""The event catalog's data model, shared by the generator and its renderers (brief 18.3).

``EventTypeInfo`` is what the catalog generator (``generators/catalog.py``) extracts from the
LinkML event classes in ``schema/core/events.yaml`` and hands to the renderers
(``catalog_asyncapi.py``, ``catalog_markdown.py``), which are pure functions of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EventTypeInfo:
    """One event type of the catalog.

    ``event_type`` is the ledger name (``Record.Created``); ``ce_type`` the CloudEvents ``type``
    (``tl.core.Record.Created.v1``); ``payload_class`` the LinkML class of the ledger payload.
    ``title`` is the first sentence of ``description``. ``payload_schema`` is the JSON Schema of the
    ledger payload; ``envelope_schema`` the JSON Schema of the CloudEvent a subscriber receives
    (``type`` fixed to ``ce_type``, ``data.detail`` described by the payload schema);
    ``sample_payload`` and ``sample_envelope`` are examples that validate against them.
    """

    event_type: str
    version: int
    ce_type: str
    title: str
    description: str
    payload_class: str
    payload_schema: dict[str, Any]
    envelope_schema: dict[str, Any]
    sample_payload: dict[str, Any]
    sample_envelope: dict[str, Any]
