"""The Python-only write path of the enrichment layer (FANOUT D2, D6; brief §18.9).

``SetPsetValues`` refuses the roots ``enrich`` and ``src`` (``READ_ONLY_ROOTS``), so no client can
write a value into ``psets.enrich.<enricher>.<property>``. This function is the only other writer:
the enrichment service calls it when a value is accepted, by a person or by an enricher's ``auto``
policy. It writes **only** the layer ``enrich.<enricher>``, never an authoritative pset, and it
runs the target type's own allow-list and guards for ``SetPsetValues`` first (ADR-0010), so a closed
type stays closed. Promoting a value to a real field is the person's own ``SetPsetValues``.

Nothing is appended when the layer already holds the value (the result is empty).
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import text
from tl_schema.conformance import evaluate

from tl_core.integration.contract import ENRICHER_NAME_RE, ENRICHMENT_PSET_PREFIX
from tl_core.ledger import Event, NewEvent
from tl_core.modules import bound_psets, require_generic
from tl_core.projection.pset import apply_values
from tl_core.schema_provider import get_provider
from tl_core.services.errors import RecordNotFoundError, RecordVoidedError
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

LAYER = "enrichment"
_PROPERTY_RE = r"[a-z][a-z0-9_]{0,62}"
_RECORD_SQL = text(
    "SELECT id, key, type, scope, status, psets_json, voided, version "
    "FROM cur_core_record WHERE id = :id"
)


def write_enrichment_layer(
    uow: UnitOfWork,
    *,
    record_id: str,
    scope: str,
    enricher: str,
    values: dict[str, Any],
    actor: str,
    source: str,
    correlation_id: str | None,
    causation_id: str | None,
) -> list[Event]:
    """Set ``values`` (property name to value) in the layer of ``enricher`` of one record."""
    if ENRICHER_NAME_RE.fullmatch(enricher) is None:
        raise ValueError("not an enricher name")
    if not values or any(re.fullmatch(_PROPERTY_RE, key) is None for key in values):
        raise ValueError("not a property of an enrichment layer")
    row = uow.conn().execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None or row.scope != scope:
        raise RecordNotFoundError(f"no record {record_id!r} in scope {scope!r}")
    require_generic(uow.conn(), row.type, "SetPsetValues", record_id)
    if row.voided:
        raise RecordVoidedError(f"record {record_id!r} is voided and cannot be updated")
    pset = f"{ENRICHMENT_PSET_PREFIX}{enricher}"
    current: dict[str, Any] = json.loads(row.psets_json)
    merged: dict[str, Any] = json.loads(json.dumps(current))
    apply_values(merged, pset, values)
    if merged == current:
        return []
    schema = get_provider().effective(scope)
    report = evaluate(
        schema,
        row.type,
        merged,
        state=row.status,
        on=utcnow().date(),
        bound=bound_psets(uow.conn(), row.type, row.id),
    )
    result = uow.append(
        stream_id=record_id,
        stream_type=row.type,
        scope=scope,
        expected_version=int(row.version),
        events=[
            NewEvent(
                event_type="Pset.ValuesSet",
                payload={
                    "pset": pset,
                    "layer": LAYER,
                    "values": values,
                    "effective_schema_hash": schema.hash,
                    "conformance": report.status,
                    "units": {},
                },
            )
        ],
        actor=actor,
        source=source,
        correlation_id=correlation_id or new_ulid(),
        causation_id=causation_id,
    )
    return result.events


__all__ = ["LAYER", "write_enrichment_layer"]
