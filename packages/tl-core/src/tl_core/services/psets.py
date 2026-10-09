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
from tl_schema.validation import validate_psets

from tl_core.ledger import NewEvent
from tl_core.projection.promoted import ensure_promoted_columns
from tl_core.projection.pset import set_nested
from tl_core.schema_provider import get_provider
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import (
    LayerError,
    NoChangesError,
    PsetValidationError,
    RecordNotFoundError,
    RecordVoidedError,
    UnknownPsetError,
)
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

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


def _nest(pset: str, values: dict[str, Any], into: dict[str, Any]) -> None:
    """Write ``values`` into ``into`` at their pset-qualified paths (``valve_data.x.a``)."""
    for key, value in values.items():
        set_nested(into, [*pset.split("."), *key.split(".")], value)


def handle_set_pset_values(uow: UnitOfWork, cmd: SetPsetValues) -> CommandResult:
    """Validate against the scope's effective schema and emit ``Pset.ValuesSet``.

    Structural problems (wrong layer, unknown key, wrong type, null) refuse the write. Range,
    pattern and value-list problems are stored and show up as conformance. Every refusal raises
    before anything is appended; the handler never commits.
    """
    row = load_row(uow, cmd.stream_id, cmd.scope)
    if row.voided:
        raise RecordVoidedError(f"record {cmd.stream_id!r} is voided and cannot be updated")
    schema = get_provider().effective(cmd.scope)

    if cmd.pset.split(".")[0] in READ_ONLY_ROOTS:
        raise LayerError(f"{cmd.pset} is in an enrichment or source layer and is not writable")
    pset = schema.find_pset(cmd.pset)
    if pset is None:
        raise UnknownPsetError(f"pset {cmd.pset!r} is not in the effective schema")
    if row.type not in pset.applies_to:
        raise UnknownPsetError(f"pset {cmd.pset!r} does not apply to {row.type!r}")
    if not cmd.values:
        raise NoChangesError(f"no values given for {cmd.pset}")
    if cmd.layer == "project" and pset.layer != "project":
        raise LayerError(f"{cmd.pset} is a company standard pset; write it with layer 'standard'")
    if cmd.layer in ("standard", "custom") and pset.layer != "standard":
        raise LayerError(f"{cmd.pset} is a project pset; write it with layer 'project'")
    for key in cmd.values:
        is_custom = key.startswith("x.")
        if cmd.layer == "custom":
            if not pset.custom_allowed:
                raise LayerError(f"{cmd.pset} has no custom section")
            if not is_custom:
                raise LayerError(f"{cmd.pset}.{key} is not in the custom section (keys start 'x.')")
        elif is_custom or key == "x":
            raise LayerError(f"{cmd.pset}.{key} is in the custom section; use layer 'custom'")
        if pset.find(key) is None:
            raise PsetValidationError(
                f"{cmd.pset}.{key} is not defined in the effective schema",
                [f"psets.{cmd.pset}.{key}: not defined"],
            )

    nulls = sorted(key for key, value in cmd.values.items() if value is None)
    if nulls:
        raise PsetValidationError(
            "null values are not supported",
            [f"{cmd.pset}.{key}: null" for key in nulls],
        )

    incoming: dict[str, Any] = {}
    _nest(cmd.pset, cmd.values, incoming)
    issues = validate_psets(schema, row.type, incoming)
    kept = [issue for issue in issues if issue.keyword in BLOCKING_KEYWORDS]
    if kept:
        raise PsetValidationError(
            f"values for {cmd.pset} are invalid",
            [f"{issue.path}: {issue.message}" for issue in kept],
        )

    current: dict[str, Any] = json.loads(row.psets_json)
    merged: dict[str, Any] = json.loads(json.dumps(current))
    _nest(cmd.pset, cmd.values, merged)
    if merged == current:
        raise NoChangesError(f"no value of {cmd.pset} differs from the record")

    ensure_promoted_columns(uow.conn(), schema)
    report = evaluate(schema, row.type, merged, state=row.status, on=utcnow().date())

    units: dict[str, str] = {}
    for key in cmd.values:
        prop = pset.find(key)
        if prop is not None and prop.unit is not None:
            units[key] = prop.unit

    result = uow.append(
        stream_id=cmd.stream_id,
        stream_type=row.type,
        scope=cmd.scope,
        expected_version=cmd.expected_version,
        events=[
            NewEvent(
                event_type="Pset.ValuesSet",
                payload={
                    "pset": cmd.pset,
                    "layer": cmd.layer,
                    "values": cmd.values,
                    "effective_schema_hash": schema.hash,
                    "conformance": report.status,
                    "units": units,
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=cmd.stream_id,
        key=row.key,
        version=result.new_version,
        events=result.events,
    )


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
