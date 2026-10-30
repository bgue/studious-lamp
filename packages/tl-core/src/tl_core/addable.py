"""What can still be added to a record: standard properties, sets to adopt, custom fields.

P1-UX3 round 4. One read for the TUI's Add property form, the API (``GET /records/{id}/addable-
properties``) and the MCP tool ``get_addable_properties``, so every entry point offers the same
things:

* ``standard``: the writable properties of the sets the project's effective schema shows for the
  record's type (and the sets its class binds) that the record has no value for;
* ``adoptable``: optional sets of the company standard that apply to the record's type and are not
  in the project's schema, with whether this viewer may adopt them (``AdoptSchemaPackage``, the
  schema registry's own command, an administrator's) and the words to show when not;
* ``custom``: for each standard set, its custom-section rule (allowed, the most names, the names
  held now) and the rule for a name (``name_rule``).

Visibility first (ADR-0016): a record the viewer may not read answers ``RecordNotFoundError`` with
the same text as a record that does not exist, before anything else is looked at. The answer is
advice for a screen; ``SetPsetValues`` and ``AdoptSchemaPackage`` check everything again when they
run.
"""

from __future__ import annotations

import json
from typing import Any, Literal, cast

from pydantic import BaseModel
from sqlalchemy import text
from tl_schema.effective import EffectivePset, EffectiveSchema
from tl_schema.formgen import form_metadata
from tl_schema.forms import EnumValue, FieldKind, FieldMeta, PsetGroupMeta

from tl_core import confidentiality
from tl_core.actions import Holds
from tl_core.modules import bound_psets, require_generic
from tl_core.schema_provider import get_provider
from tl_core.services import psets as pset_services
from tl_core.services.errors import RecordNotFoundError, ServiceError
from tl_core.uow import UnitOfWork

_AGENT_PREFIX = "agent:"
#: The rule for the name of a custom field, in words (``psets.custom_name_problem`` enforces it).
NAME_RULE = (
    "Lower case letters, digits and _, 1 to 40 characters, starting with a letter; "
    "not x, prj, enrich or src (or starting with one and _); not the name of a property of the set."
)
ADOPT_COMMAND = "AdoptSchemaPackage"

_RECORD_SQL = text(
    "SELECT id, key, type, scope, psets_json, voided FROM cur_core_record WHERE id = :id"
)


class AddableProperty(BaseModel):
    """One standard property the record could be given a value for."""

    pset: str  # "valve_data" | "prj.shutdown_tie_in"
    set_label: str
    package: str
    layer: Literal["standard", "project"]  # the layer to write it with
    property: str  # the key inside the set
    path: str  # "psets.valve_data.size_in"
    label: str
    description: str
    unit: str | None = None
    type: FieldKind
    code_list: str | None = None  # name of the code list when type is "enum"
    values: list[EnumValue] | None = None
    enforcement: Literal["advisory", "required", "locked"] | None = None
    required_in_states: list[str] = []
    order: int = 0


class AdoptableSet(BaseModel):
    """An optional company set that applies to the record's type and the project has not adopted.

    ``can_adopt`` is whether this viewer may run ``command`` (``AdoptSchemaPackage`` with
    ``project``, ``package`` and ``version``); ``needs`` is the sentence to show when not.
    """

    pset: str
    set_label: str
    package: str
    version: str
    project: str
    command: str = ADOPT_COMMAND
    can_adopt: bool
    needs: str | None = None
    properties: list[AddableProperty]


class CustomRule(BaseModel):
    """The custom section of one standard set the record's type uses."""

    pset: str
    set_label: str
    package: str
    allowed: bool
    max_properties: int | None = None  # None: the schema states no limit (the command caps it)
    used: int  # distinct custom names the record holds in this set
    declared: list[str] = []  # names the project's schema declares (typed)


class AddableProperties(BaseModel):
    """Everything the Add property form (or an agent) needs to know about one record."""

    record_id: str
    key: str | None
    type: str
    scope: str
    can_write: bool  # False: voided, an agent, or a type that changes through its module only
    write_refusal: str | None = None
    name_rule: str = NAME_RULE
    standard: list[AddableProperty]
    adoptable: list[AdoptableSet]
    custom: list[CustomRule]


def _empty(psets: dict[str, Any], pset: str, name: str) -> bool:
    node: Any = psets
    for part in [*pset.split("."), name]:
        node = cast(dict[str, Any], node).get(part) if isinstance(node, dict) else None
    return node in (None, "")


def _property(schema: EffectiveSchema, group: PsetGroupMeta, field: FieldMeta) -> AddableProperty:
    name = field.path.removeprefix(f"psets.{group.name}.")
    pset = schema.find_pset(group.name)
    prop = pset.find(name) if pset is not None else None
    return AddableProperty(
        pset=group.name,
        set_label=group.label,
        package=group.package,
        layer="project" if field.layer == "project" else "standard",
        property=name,
        path=field.path,
        label=field.label,
        description=field.description,
        unit=field.unit,
        type=field.kind,
        code_list=prop.code_list if prop is not None else None,
        values=field.enum_values,
        enforcement=field.enforcement,
        required_in_states=field.required_in_states,
        order=field.order,
    )


def _writable(field: FieldMeta) -> bool:
    return not field.readonly and field.layer in ("standard", "project")


def _write_state(uow: UnitOfWork, row: Any, actor: str) -> tuple[bool, str | None]:
    if actor.startswith(_AGENT_PREFIX):
        return False, "an agent proposes a change; it does not make one"
    if row.voided:
        return False, "the record is voided"
    try:
        require_generic(uow.conn(), row.type, "SetPsetValues", row.id)
    except ServiceError as exc:
        return False, str(exc)
    return True, None


def _adoptable(
    uow: UnitOfWork,
    row: Any,
    project_schema: EffectiveSchema,
    bound: tuple[str, ...],
    holds: Holds,
) -> list[AdoptableSet]:
    if not row.scope.startswith("project:"):
        return []
    project = row.scope.removeprefix("project:")
    company = get_provider().effective("company")
    allowed = holds("admin")
    found: list[AdoptableSet] = []
    for pset in company.psets_for(row.type, bound):
        if pset.layer != "standard" or pset.adoption != "optional":
            continue
        if pset.name in project_schema.psets:
            continue
        found.append(
            AdoptableSet(
                pset=pset.name,
                set_label=pset.label,
                package=pset.package,
                version=pset.version,
                project=project,
                can_adopt=allowed,
                needs=None if allowed else f"Needs a superuser to adopt this set for {project}",
                properties=_set_properties(company, pset),
            )
        )
    return found


def _set_properties(schema: EffectiveSchema, pset: EffectivePset) -> list[AddableProperty]:
    meta = form_metadata(schema, "core.Record", [pset.name])
    group = next(g for g in meta.psets if g.name == pset.name)
    return [_property(schema, group, f) for f in group.fields if _writable(f)]


def _custom_rules(
    schema: EffectiveSchema, record_type: str, bound: tuple[str, ...], psets: dict[str, Any]
) -> list[CustomRule]:
    rules: list[CustomRule] = []
    for pset in schema.psets_for(record_type, bound):
        if pset.layer != "standard":
            continue
        rules.append(
            CustomRule(
                pset=pset.name,
                set_label=pset.label,
                package=pset.package,
                allowed=pset.custom_allowed,
                max_properties=pset.custom_max if pset.custom_allowed else None,
                used=len(pset_services.stored_custom_names(psets, pset.name)),
                declared=list(pset.custom),
            )
        )
    return rules


def addable_properties(
    uow: UnitOfWork, record_id: str, *, actor: str, holds: Holds
) -> AddableProperties:
    """What ``actor`` could add to the record. Raises ``RecordNotFoundError`` for a record that is
    missing or hidden from the viewer, with the same text for both."""
    conn = uow.conn()
    confidentiality.require_visible(conn, record_id)
    row = conn.execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None:
        raise RecordNotFoundError(f"no record {record_id!r}")
    psets: dict[str, Any] = json.loads(row.psets_json)
    schema = get_provider().effective(row.scope)
    bound = bound_psets(conn, row.type, row.id)
    meta = pset_services.form_metadata(uow, row.scope, row.type, row.id)
    standard = [
        _property(schema, group, field)
        for group in meta.psets
        for field in group.fields
        if _writable(field) and _empty(psets, group.name, field.path.rsplit(".", 1)[-1])
    ]
    can_write, refusal = _write_state(uow, row, actor)
    return AddableProperties(
        record_id=row.id,
        key=row.key,
        type=row.type,
        scope=row.scope,
        can_write=can_write,
        write_refusal=refusal,
        standard=standard,
        adoptable=_adoptable(uow, row, schema, bound, holds),
        custom=_custom_rules(schema, row.type, bound, psets),
    )
