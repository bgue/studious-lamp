"""Pset write, form-metadata and conformance services (P0-I2; brief 6.3, 27.3).

Signatures are the contract between the schema and TUI workstreams; changing one needs an
orchestrator decision. The effective schema comes from ``tl_core.schema_provider``.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from typing import Any, Literal, cast

from sqlalchemy import text
from tl_schema.compose import EffectiveCache
from tl_schema.conformance import evaluate
from tl_schema.formgen import form_metadata as build_form_metadata
from tl_schema.forms import ConformanceReport, FormMetadata
from tl_schema.packages import RESERVED_PSET_NAMES
from tl_schema.validation import validate_psets

from tl_core import confidentiality
from tl_core.extypes.service import refuse_index_write
from tl_core.ledger import NewEvent
from tl_core.modules import bound_psets, require_generic
from tl_core.projection.promoted import ensure_promoted_columns
from tl_core.projection.pset import apply_values
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

#: The name of an ad-hoc custom field (P1-UX3 round 4): lower case letters, digits and ``_``,
#: 1 to 40 characters, starting with a letter. It is written ``x.<name>`` in the set's values.
CUSTOM_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,39}")
#: Where the name of an ad-hoc field may not start: the roots of the value layers (``x``, ``prj``,
#: ``enrich``, ``src``), alone or followed by ``_``. The same list the schema reserves for sets.
RESERVED_CUSTOM_PREFIXES = tuple(sorted(RESERVED_PSET_NAMES))
#: The most ad-hoc fields a set takes when its schema states no limit (a guard, not a design).
AD_HOC_CAP = 100
#: The longest text value of an ad-hoc field.
AD_HOC_TEXT_MAX = 2000

_RECORD_SQL = text(
    "SELECT id, key, type, scope, status, psets_json, voided, version "
    "FROM cur_core_record WHERE id = :id"
)


def custom_name_problem(name: str) -> str | None:
    """Why ``name`` cannot name an ad-hoc custom field, in words; ``None`` when it can.

    The name is the part after ``x.``. This is the one rule; the API, MCP proposals, inbound
    mappings and the CLI all reach it through ``SetPsetValues``.
    """
    if CUSTOM_NAME_PATTERN.fullmatch(name) is None:
        return (
            f"{name!r} is not a usable custom field name: lower case letters, digits and _, "
            "1 to 40 characters, starting with a letter"
        )
    if "__" in name:
        return f"{name!r} is not a usable custom field name: no double underscore"
    for prefix in RESERVED_CUSTOM_PREFIXES:
        if name == prefix or name.startswith(prefix + "_"):
            return f"{name!r} starts with {prefix!r}, which is reserved"
    return None


def custom_value_problem(value: Any) -> str | None:
    """Why ``value`` cannot be kept in an ad-hoc custom field; ``None`` when it can.

    A field with no declared type holds text; a number the form could validate is kept as a number
    (a date as its ISO text). Anything else (a list, an object, a boolean) is refused.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return "a custom field holds text or a number"
    if isinstance(value, float) and not math.isfinite(value):
        return "a custom field holds a finite number"
    if isinstance(value, str) and len(value) > AD_HOC_TEXT_MAX:
        return f"a custom field holds at most {AD_HOC_TEXT_MAX} characters"
    return None


def stored_custom_names(psets: Mapping[str, Any], pset: str) -> set[str]:
    """The names held in a set's custom section of a record's ``psets`` object."""
    node: Any = psets
    for part in pset.split("."):
        node = cast(dict[str, Any], node).get(part) if isinstance(node, dict) else None
    if not isinstance(node, dict):
        return set()
    held: Any = cast(dict[str, Any], node).get("x")
    return set(cast(dict[str, Any], held)) if isinstance(held, dict) else set()


class SetPsetValues(Command):
    stream_id: str
    expected_version: int
    pset: str  # "valve_data" | "prj.shutdown_tie_in"
    layer: Literal["standard", "custom", "project"]  # enrichment and source are not user-writable
    values: dict[str, Any]  # keys relative to the pset; custom-section keys are prefixed "x."


def load_row(uow: UnitOfWork, stream_id: str, scope: str) -> Any:
    row = uow.conn().execute(_RECORD_SQL, {"id": stream_id}).first()
    if row is None or row.scope != scope or confidentiality.is_hidden(uow.conn(), stream_id):
        raise RecordNotFoundError(f"no record {stream_id!r} in scope {scope!r}")
    return row


def handle_set_pset_values(uow: UnitOfWork, cmd: SetPsetValues) -> CommandResult:
    """Validate against the scope's effective schema and emit ``Pset.ValuesSet``.

    The index fields of an object-backed extension record are copies of its body, so a direct write
    to its type's pset is refused (``BodyNotAllowedError``); ``tl_core.extypes.body`` writes them
    through ``apply_index_values``.

    Structural problems (wrong layer, unknown key, wrong type) refuse the write. A ``None`` value
    unsets that property (a key with no value is a no-op; if nothing changes at all the write is
    refused with ``NoChangesError``). Range, pattern and value-list problems are stored and show
    up as conformance. Every refusal raises before anything is appended; the handler never commits.
    """
    return _set_pset_values(uow, cmd, from_body=False)


def apply_index_values(uow: UnitOfWork, cmd: SetPsetValues) -> CommandResult:
    """``handle_set_pset_values`` for the body store: it may write an object-backed type's pset."""
    return _set_pset_values(uow, cmd, from_body=True)


def _set_pset_values(uow: UnitOfWork, cmd: SetPsetValues, *, from_body: bool) -> CommandResult:
    row = load_row(uow, cmd.stream_id, cmd.scope)
    require_generic(uow.conn(), row.type, "SetPsetValues", cmd.stream_id)
    if row.voided:
        raise RecordVoidedError(f"record {cmd.stream_id!r} is voided and cannot be updated")
    if not from_body:
        refuse_index_write(uow, row.type, cmd.pset)
    schema = get_provider().effective(cmd.scope)

    if cmd.pset.split(".")[0] in READ_ONLY_ROOTS:
        raise LayerError(f"{cmd.pset} is in an enrichment or source layer and is not writable")
    bound = bound_psets(uow.conn(), row.type, row.id)
    pset = schema.find_pset(cmd.pset)
    if pset is None:
        raise UnknownPsetError(f"pset {cmd.pset!r} is not in the effective schema")
    if row.type not in pset.applies_to and cmd.pset not in bound:
        raise UnknownPsetError(f"pset {cmd.pset!r} does not apply to {row.type!r}")
    if not cmd.values:
        raise NoChangesError(f"no values given for {cmd.pset}")
    if cmd.layer == "project" and pset.layer != "project":
        raise LayerError(f"{cmd.pset} is a company standard pset; write it with layer 'standard'")
    if cmd.layer in ("standard", "custom") and pset.layer != "standard":
        raise LayerError(f"{cmd.pset} is a project pset; write it with layer 'project'")
    ad_hoc: list[str] = []  # custom names the schema does not declare, new to this write
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
            if not is_custom or not pset.custom_allowed:
                raise PsetValidationError(
                    f"{cmd.pset}.{key} is not defined in the effective schema",
                    [f"psets.{cmd.pset}.{key}: not defined"],
                )
            problem = _ad_hoc_problem(pset, key, cmd.values[key])
            if problem is not None:
                raise PsetValidationError(
                    f"{cmd.pset}.{key}: {problem}", [f"psets.{cmd.pset}.{key}: {problem}"]
                )
            ad_hoc.append(key[2:])
    if ad_hoc:
        _check_ad_hoc_room(cmd, pset, row, ad_hoc)

    # A None value unsets the property: nothing to type-check, and the key is recorded in the
    # event as the ledgered clear.
    incoming: dict[str, Any] = {}
    apply_values(incoming, cmd.pset, {k: v for k, v in cmd.values.items() if v is not None})
    issues = validate_psets(schema, row.type, incoming, bound)
    kept = [issue for issue in issues if issue.keyword in BLOCKING_KEYWORDS]
    if kept:
        raise PsetValidationError(
            f"values for {cmd.pset} are invalid",
            [f"{issue.path}: {issue.message}" for issue in kept],
        )

    current: dict[str, Any] = json.loads(row.psets_json)
    merged: dict[str, Any] = json.loads(json.dumps(current))
    apply_values(merged, cmd.pset, cmd.values)
    if merged == current:
        raise NoChangesError(f"no value of {cmd.pset} differs from the record")

    ensure_promoted_columns(uow.conn(), schema)
    report = evaluate(schema, row.type, merged, state=row.status, on=utcnow().date(), bound=bound)

    units: dict[str, str] = {}
    for key, value in cmd.values.items():
        prop = pset.find(key)
        if value is not None and prop is not None and prop.unit is not None:
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


def _ad_hoc_problem(pset: Any, key: str, value: Any) -> str | None:
    """Why ``key`` (``x.<name>``) is no acceptable ad-hoc field of ``pset``; ``None`` if it is."""
    name = key[2:]
    problem = custom_name_problem(name)
    if problem is not None:
        return problem
    if name in pset.properties:
        return f"{name!r} is already a property of this set; write it without 'x.'"
    return custom_value_problem(value)


def _check_ad_hoc_room(cmd: SetPsetValues, pset: Any, row: Any, names: list[str]) -> None:
    """Refuse when the new ad-hoc names take the custom section over its limit."""
    held = stored_custom_names(json.loads(row.psets_json), cmd.pset)
    added = {n for n in names if cmd.values.get(f"x.{n}") is not None} - held
    if not added:
        return
    limit = pset.custom_max if pset.custom_max is not None else AD_HOC_CAP
    kept = held | {k[2:] for k, v in cmd.values.items() if k.startswith("x.") and v is not None}
    if len(kept) > limit:
        raise PsetValidationError(
            f"{cmd.pset} takes at most {limit} custom fields on a record "
            f"({len(held)} are there already)",
            [f"psets.{cmd.pset}.x: more than {limit} custom fields"],
        )


def form_metadata(
    uow: UnitOfWork, scope: str, record_type: str, record_id: str | None = None
) -> FormMetadata:
    """Form and grid metadata for a record type under the scope's effective schema.

    With ``record_id`` the form also lists the psets the record's class binds to it (ADR-0010).
    """
    schema = get_provider().effective(scope)
    bound = bound_psets(uow.conn(), record_type, record_id) if record_id is not None else ()
    key = f"form:{record_type}" + (f"+{'|'.join(sorted(bound))}" if bound else "")
    built = _CACHE.get_or_build(
        schema, key, lambda: build_form_metadata(schema, record_type, bound)
    )
    return built.model_copy(deep=True)


def conformance(uow: UnitOfWork, record_id: str) -> ConformanceReport:
    """Conformance of a record's current values against its scope's current effective schema."""
    row = uow.conn().execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None or confidentiality.is_hidden(uow.conn(), record_id):
        raise RecordNotFoundError(f"no record {record_id!r}")
    schema = get_provider().effective(row.scope)
    psets: dict[str, Any] = json.loads(row.psets_json)
    return evaluate(
        schema,
        row.type,
        psets,
        state=row.status,
        on=utcnow().date(),
        bound=bound_psets(uow.conn(), row.type, row.id),
    )
