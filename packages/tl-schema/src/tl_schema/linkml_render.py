# pyright: basic
"""Render an effective schema as LinkML: pset classes merged into core (brief 27.3).

Psets compile into LinkML classes (``ValveData``, plus ``ValveData_P123_x`` for the project's
custom section), referenced from each record class's ``psets`` slot through a per-record-type
container class (``CoreRecordPsets``). The platform annotations carry the rules LinkML cannot
express (``tl:enforcement``, ``tl:value_list_policy``, ``tl:materialize``,
``tl:required_in_states``, ``tl:adoption``, ``tl:custom_section``); each tag is documented in
``schema/core/annotations.yaml``.

The result is an artefact: JSON Schema, form metadata and conformance read the
``EffectiveSchema`` model directly. The LinkML view serves ``tl schema lint``, semantic exports
and, later, SHACL and JSON-LD generation. It is built with ``SchemaView`` from the core schema
files, so any core change shows up here.
"""

from __future__ import annotations

import json
import re
from contextlib import chdir
from pathlib import Path
from typing import Any

from linkml_runtime.dumpers import yaml_dumper
from linkml_runtime.linkml_model import (
    ClassDefinition,
    EnumDefinition,
    PermissibleValue,
    SlotDefinition,
)
from linkml_runtime.linkml_model.annotations import Annotation
from linkml_runtime.linkml_model.units import UnitOfMeasure
from linkml_runtime.utils.schemaview import SchemaView

from tl_schema.compose import project_of
from tl_schema.effective import ALWAYS, EffectiveProperty, EffectivePset, EffectiveSchema

CORE_SCHEMA_DIR: Path = Path(__file__).resolve().parents[4] / "schema" / "core"
CORE_ROOT = "core.yaml"

_RANGE_FOR_KIND: dict[str, str] = {
    "string": "string",
    "text": "string",
    "int": "integer",
    "decimal": "decimal",
    "bool": "boolean",
    "date": "date",
    "datetime": "datetime",
    "quantity": "decimal",
    "ref": "string",
    "json": "Any",
}


def _new(factory: Any, **fields: Any) -> Any:
    """Build a LinkML metamodel object. Typed ``Any``: the metamodel's own types are too loose."""
    return factory(**fields)


def pascal(name: str) -> str:
    """``valve_data`` becomes ``ValveData``, ``prj.shutdown_tie_in`` ``PrjShutdownTieIn``."""
    return "".join(part[:1].upper() + part[1:] for part in re.split(r"[._]", name) if part)


def record_class_name(record_type: str) -> str:
    """``core.Record`` becomes ``Record`` (the class name inside its module)."""
    return record_type.split(".", 1)[-1]


def _set_annotation(element: Any, tag: str, value: Any) -> None:
    text = value if isinstance(value, (str, bool)) else json.dumps(value)
    element.annotations[tag] = _new(Annotation, tag=tag, value=text)


def _annotate(element: Any, tags: dict[str, Any]) -> None:
    for tag, value in tags.items():
        if value is None or value == [] or value is False:
            continue
        _set_annotation(element, tag, value)


def _slot(prop: EffectiveProperty, enum_name: str | None) -> SlotDefinition:
    slot = _new(SlotDefinition, name=prop.name, description=prop.description, title=prop.label)
    slot.range = enum_name if enum_name else _RANGE_FOR_KIND[prop.kind]
    if ALWAYS in prop.required_in_states:
        slot.required = True
    if prop.minimum is not None:
        slot.minimum_value = prop.minimum
    if prop.maximum is not None:
        slot.maximum_value = prop.maximum
    if prop.pattern is not None:
        slot.pattern = prop.pattern
    if prop.unit is not None:
        slot.unit = _new(UnitOfMeasure, ucum_code=prop.unit)
    for mapping in prop.exact_mappings:
        slot.exact_mappings.append(mapping)
    _annotate(
        slot,
        {
            "tl:enforcement": prop.enforcement,
            "tl:value_list_policy": prop.value_list_policy,
            "tl:materialize": prop.materialize,
            "tl:required_in_states": [s for s in prop.required_in_states if s != ALWAYS],
            "tl:layer": prop.layer,
        },
    )
    return slot


def _enum_for(prop: EffectiveProperty, pset: EffectivePset, enums: dict[str, Any]) -> str:
    assert prop.code_list is not None and prop.enum_values is not None
    wanted = [(v.code, v.label, v.crosswalk) for v in prop.enum_values]
    name = prop.code_list
    existing: Any = enums.get(name)
    if existing is not None:
        have = [
            (code, pv.description, _crosswalk(pv))
            for code, pv in existing.permissible_values.items()
        ]
        if have != wanted:
            name = f"{pascal(pset.name)}{prop.code_list}"
    if name not in enums:
        enum = _new(EnumDefinition, name=name, description=f"Code list {prop.code_list}.")
        for code, label, crosswalk in wanted:
            value = _new(PermissibleValue, text=code, description=label)
            if crosswalk is not None:
                _set_annotation(value, "tl:crosswalk", crosswalk)
            if code in prop.enum_meanings:
                value.meaning = prop.enum_meanings[code]
            enum.permissible_values[code] = value
        enums[name] = enum
    return name


def _crosswalk(value: Any) -> str | None:
    note = value.annotations.get("tl:crosswalk")
    return None if note is None else str(note.value)


def _pset_class(
    pset: EffectivePset,
    project: str | None,
    classes: dict[str, Any],
    enums: dict[str, Any],
) -> str:
    name = pascal(pset.name)
    cls = _new(ClassDefinition, name=name, description=pset.description, title=pset.label)
    _annotate(
        cls,
        {
            "tl:enforcement": pset.enforcement,
            "tl:adoption": pset.adoption,
            "tl:layer": pset.layer,
            "tl:custom_section": pset.custom_allowed,
            "tl:custom_max_properties": None if pset.custom_max is None else str(pset.custom_max),
            "tl:applies_to": pset.applies_to,
            "tl:class_filter": pset.class_filter,
            "tl:package": f"{pset.package}@{pset.version}",
            "tl:extension": pset.extension,
        },
    )
    for prop in pset.properties.values():
        enum_name = _enum_for(prop, pset, enums) if prop.kind == "enum" else None
        cls.attributes[prop.name] = _slot(prop, enum_name)
    if pset.custom:
        custom_name = f"{name}_{project or 'company'}_x"
        custom_cls = _new(
            ClassDefinition,
            name=custom_name,
            description=f"Custom section of {pset.name} for project {project}.",
        )
        _annotate(custom_cls, {"tl:layer": "custom", "tl:extension": pset.extension})
        for prop in pset.custom.values():
            enum_name = _enum_for(prop, pset, enums) if prop.kind == "enum" else None
            custom_cls.attributes[prop.name] = _slot(prop, enum_name)
        classes[custom_name] = custom_cls
        cls.attributes["x"] = _new(
            SlotDefinition, name="x", range=custom_name, description="Project custom section."
        )
    classes[name] = cls
    return name


def build_view(schema: EffectiveSchema) -> SchemaView:
    """A ``SchemaView`` of the core schema with the schema's pset classes merged in."""
    with chdir(CORE_SCHEMA_DIR):
        view = SchemaView(CORE_ROOT)
        view.merge_imports()
    definition: Any = view.schema
    definition.id = f"https://example.org/throughline/effective/{schema.scope.replace(':', '/')}"
    definition.name = "tl_effective"
    definition.title = f"Throughline effective schema for {schema.scope}"
    _set_annotation(definition, "tl:effective_schema_hash", schema.hash)
    _set_annotation(definition, "tl:scope", schema.scope)

    project = project_of(schema.scope)
    classes: dict[str, Any] = {}
    enums: dict[str, Any] = {}
    class_for_pset: dict[str, str] = {}
    for pset in schema.psets.values():
        class_for_pset[pset.name] = _pset_class(pset, project, classes, enums)

    record_types = sorted({rt for p in schema.psets.values() for rt in p.applies_to})
    for record_type in record_types:
        container = _new(
            ClassDefinition,
            name=f"{pascal(record_type)}Psets",
            description=f"Property sets that apply to {record_type}.",
        )
        project_container = _new(
            ClassDefinition,
            name=f"{pascal(record_type)}ProjectPsets",
            description=f"Project custom property sets that apply to {record_type}.",
        )
        for pset in schema.for_record_type(record_type):
            if pset.layer == "standard":
                container.attributes[pset.name] = _new(
                    SlotDefinition,
                    name=pset.name,
                    range=class_for_pset[pset.name],
                    description=pset.description,
                )
            else:
                short = pset.name.split(".", 1)[1]
                project_container.attributes[short] = _new(
                    SlotDefinition,
                    name=short,
                    range=class_for_pset[pset.name],
                    description=pset.description,
                )
        if project_container.attributes:
            classes[project_container.name] = project_container
            container.attributes["prj"] = _new(
                SlotDefinition,
                name="prj",
                range=project_container.name,
                description="Project custom psets.",
            )
        classes[container.name] = container

    for enum in enums.values():
        definition.enums[enum.name] = enum
    for cls in classes.values():
        definition.classes[cls.name] = cls
    for record_type in record_types:
        target = definition.classes.get(record_class_name(record_type))
        if target is not None:
            usage = _new(SlotDefinition, name="psets", range=f"{pascal(record_type)}Psets")
            target.slot_usage["psets"] = usage
    return SchemaView(definition)


def linkml_yaml(schema: EffectiveSchema) -> str:
    """The effective schema as LinkML YAML text (deterministic for a given schema)."""
    definition: Any = build_view(schema).schema
    return yaml_dumper.dumps(definition)
