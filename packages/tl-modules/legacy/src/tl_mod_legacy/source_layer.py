"""The Python-only write path of the source layer ``src.legacy-<system>.<table>`` (brief 29.6).

``SetPsetValues`` refuses the root ``src`` (``READ_ONLY_ROOTS``), so no client can write there; this
function is the loader's way in, the way ``write_enrichment_layer`` is the enrichers'. Columns of
the file that the mapping does not use are kept, so nothing in the source is lost.

Every name and value comes from an untrusted file: a property name is folded to
``[a-z][a-z0-9_]{0,62}``, a value is text of at most 500 characters without control characters,
and a record takes at most 60 columns. The type's own allow-list and guards for ``SetPsetValues``
run first (``require_generic``), so a closed type stays closed: a record type that does not allow
the command is skipped and the caller counts it.
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import text
from tl_core.ledger import NewEvent
from tl_core.modules import bound_psets, require_generic
from tl_core.projection.pset import apply_values
from tl_core.schema_provider import get_provider
from tl_core.services.errors import ServiceError
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow
from tl_schema.conformance import evaluate

from tl_mod_legacy.limits import MAX_UNMAPPED_CELL, MAX_UNMAPPED_COLUMNS

LAYER = "source"
_PROPERTY = re.compile(r"[a-z][a-z0-9_]{0,62}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_RECORD_SQL = text(
    "SELECT id, type, scope, status, psets_json, voided, version FROM cur_core_record "
    "WHERE id = :id"
)


def property_name(column: str) -> str | None:
    """The property a column becomes, or ``None`` when nothing usable is left of its name."""
    folded = re.sub(r"[^a-z0-9]+", "_", column.lower()).strip("_")[:62]
    if folded and not folded[0].isalpha():
        folded = f"c_{folded}"[:62]
    return folded if _PROPERTY.fullmatch(folded) else None


def clean_values(raw: dict[str, str]) -> dict[str, str]:
    """The columns that can be kept: usable name, non-empty text without control characters.

    A cell longer than 500 characters is cut. At most 60 columns are kept (the first 60 in file
    order); a name that two columns fold to keeps the first.
    """
    kept: dict[str, str] = {}
    for column, value in raw.items():
        name = property_name(column)
        cell = value.strip()
        if name is None or not cell or name in kept or _CONTROL.search(cell):
            continue
        kept[name] = cell[:MAX_UNMAPPED_CELL]
        if len(kept) >= MAX_UNMAPPED_COLUMNS:
            break
    return kept


def write_source_layer(
    uow: UnitOfWork,
    *,
    record_id: str,
    scope: str,
    system: str,
    table: str,
    values: dict[str, str],
    actor: str,
    source: str,
    correlation_id: str,
) -> bool:
    """Set ``values`` in ``src.legacy-<system>.<table>`` of one record; ``False`` when the record's
    type does not allow ``SetPsetValues`` or there is nothing to write."""
    if not values:
        return False
    row = uow.conn().execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None or row.scope != scope or row.voided:
        return False
    try:
        require_generic(uow.conn(), row.type, "SetPsetValues", record_id)
    except ServiceError:
        return False
    pset = f"src.legacy-{system}.{table}"
    current: dict[str, Any] = json.loads(row.psets_json)
    merged: dict[str, Any] = json.loads(json.dumps(current))
    apply_values(merged, pset, dict(values))
    if merged == current:
        return False
    schema = get_provider().effective(scope)
    report = evaluate(
        schema,
        row.type,
        merged,
        state=row.status,
        on=utcnow().date(),
        bound=bound_psets(uow.conn(), row.type, row.id),
    )
    uow.append(
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
                    "values": dict(values),
                    "effective_schema_hash": schema.hash,
                    "conformance": report.status,
                    "units": {},
                },
            )
        ],
        actor=actor,
        source=source,
        correlation_id=correlation_id,
    )
    return True
