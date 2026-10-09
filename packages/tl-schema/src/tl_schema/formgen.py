"""Form and grid metadata from an effective schema (brief 27.3, 10.2).

``form_metadata`` is the only entry point. It is a pure function of the effective schema, so the
same schema and record type always give the same metadata (and the same hash).
"""

from __future__ import annotations

from tl_schema.effective import ALWAYS, EffectiveProperty, EffectivePset, EffectiveSchema
from tl_schema.forms import EnumValue, FieldKind, FieldMeta, FormMetadata, PsetGroupMeta

#: Group name used by the four envelope fields (they belong to no pset).
CORE_GROUP = "details"


def _core_field(
    order: int,
    path: str,
    label: str,
    description: str,
    kind: FieldKind,
    readonly: bool,
    required_in_states: list[str],
) -> FieldMeta:
    """One envelope field; core fields have no enforcement, unit or enum values."""
    return FieldMeta(
        path=path,
        label=label,
        description=description,
        kind=kind,
        unit=None,
        enum_values=None,
        required_in_states=required_in_states,
        enforcement=None,
        layer="core",
        readonly=readonly,
        group=CORE_GROUP,
        order=order,
    )


def _core_fields() -> list[FieldMeta]:
    """The four envelope fields, in form order."""
    return [
        _core_field(
            0,
            "title",
            "Title",
            "Short human-readable title.",
            "string",
            readonly=False,
            required_in_states=[ALWAYS],
        ),
        _core_field(
            1,
            "description",
            "Description",
            "Longer free-text description.",
            "text",
            readonly=False,
            required_in_states=[],
        ),
        _core_field(
            2,
            "key",
            "Key",
            "Human-readable number, unique within a scope.",
            "string",
            readonly=True,
            required_in_states=[],
        ),
        _core_field(
            3,
            "status",
            "Status",
            "Workflow state.",
            "string",
            readonly=True,
            required_in_states=[],
        ),
    ]


def _enum_values(prop: EffectiveProperty) -> list[EnumValue] | None:
    """A copy of the property's enum values, or None when it has none."""
    if prop.enum_values is None:
        return None
    return [EnumValue(code=v.code, label=v.label, crosswalk=v.crosswalk) for v in prop.enum_values]


def _field(pset: EffectivePset, prop: EffectiveProperty) -> FieldMeta:
    """One pset property as a form field; writable, grouped under its pset."""
    return FieldMeta(
        path=f"psets.{pset.name}.{prop.relative_key()}",
        label=prop.label,
        description=prop.description,
        kind=prop.kind,
        unit=prop.unit,
        enum_values=_enum_values(prop),
        required_in_states=list(prop.required_in_states),
        enforcement=prop.enforcement,
        layer=prop.layer,
        readonly=False,
        group=pset.name,
        order=prop.order,
    )


def _group(pset: EffectivePset) -> PsetGroupMeta:
    """One pset as a form group; fields follow ``all_properties`` order."""
    return PsetGroupMeta(
        name=pset.name,
        label=pset.label,
        package=pset.package,
        version=pset.version,
        enforcement=pset.enforcement,
        layer=pset.layer,
        fields=[_field(pset, prop) for prop in pset.all_properties()],
    )


def form_metadata(schema: EffectiveSchema, record_type: str) -> FormMetadata:
    """Metadata a client needs to render and edit ``record_type`` under ``schema``.

    ``core_fields`` are the four envelope fields, then ``psets`` lists the psets that apply to the
    record type, standard psets first and then project psets, each by name. See the ticket for
    the exact mapping.
    """
    psets = sorted(
        schema.for_record_type(record_type),
        key=lambda p: (p.layer != "standard", p.name),
    )
    return FormMetadata(
        record_type=record_type,
        effective_schema_hash=schema.hash,
        core_fields=_core_fields(),
        psets=[_group(p) for p in psets],
    )
