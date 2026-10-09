"""Pset write, form-metadata and conformance services (P0-I2; brief 6.3, 27.3).

Signatures are the contract between the schema and TUI workstreams; changing one needs an
orchestrator decision. The effective schema comes from ``tl_core.schema_provider``.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from sqlalchemy import text
from tl_schema.compose import EffectiveCache
from tl_schema.conformance import evaluate
from tl_schema.formgen import form_metadata as build_form_metadata
from tl_schema.forms import ConformanceReport, FormMetadata

from tl_core.schema_provider import get_provider
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import (
    RecordNotFoundError,
)
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow

_CACHE = EffectiveCache()
#: Validator keywords that stop a write. Range, pattern and value-list issues are accepted and
#: show up as conformance instead (advisory and required differ in effect, not in storage).
BLOCKING_KEYWORDS = frozenset({"type", "additionalProperties"})
READ_ONLY_ROOTS = frozenset({"enrich", "src"})

_RECORD_SQL = text(
    "SELECT id, key, type, scope, status, psets_json, voided, version "
    "FROM cur_core_record WHERE id = :id"
)


class SetPsetValues(Command):
    stream_id: str
    expected_version: int
    pset: str  # "valve_data" | "prj.shutdown_tie_in"
    layer: Literal["standard", "custom", "project"]  # enrichment and source are not user-writable
    values: dict[str, Any]  # keys relative to the pset; custom-section keys are prefixed "x."


def load_row(uow: UnitOfWork, stream_id: str, scope: str) -> Any:
    row = uow.conn().execute(_RECORD_SQL, {"id": stream_id}).first()
    if row is None or row.scope != scope:
        raise RecordNotFoundError(f"no record {stream_id!r} in scope {scope!r}")
    return row


def handle_set_pset_values(uow: UnitOfWork, cmd: SetPsetValues) -> CommandResult:
    """Validate against the scope's effective schema and emit ``Pset.ValuesSet``.

    STUB: implemented by P0-I2-T06. The rules are in the ticket.
    """
    raise NotImplementedError


def form_metadata(uow: UnitOfWork, scope: str, record_type: str) -> FormMetadata:
    """Form and grid metadata for a record type under the scope's effective schema."""
    schema = get_provider().effective(scope)
    built = _CACHE.get_or_build(
        schema, f"form:{record_type}", lambda: build_form_metadata(schema, record_type)
    )
    return built.model_copy(deep=True)


def conformance(uow: UnitOfWork, record_id: str) -> ConformanceReport:
    """Conformance of a record's current values against its scope's current effective schema."""
    row = uow.conn().execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None:
        raise RecordNotFoundError(f"no record {record_id!r}")
    schema = get_provider().effective(row.scope)
    psets: dict[str, Any] = json.loads(row.psets_json)
    return evaluate(schema, row.type, psets, state=row.status, on=utcnow().date())
