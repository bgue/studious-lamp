"""JSON Schema for a record type's psets, and a validator over it (brief 27.3).

The schema checks structure and value constraints only (type, range, pattern, enum, unknown keys).
Required-in-state, enforcement levels and waivers are not JSON Schema; the conformance evaluator
uses the issues returned here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from tl_schema.compose import EffectiveCache
from tl_schema.effective import EffectiveProperty, EffectivePset, EffectiveSchema

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
DATETIME_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$"

_SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"
_PROJECT_ROOT = "prj"
_PROJECT_PREFIX = "prj."
_CUSTOM_KEY = "x"
_NUMERIC_KINDS = ("int", "decimal", "quantity")

_CACHE = EffectiveCache()


@dataclass(frozen=True)
class ValueIssue:
    """One violation found in a ``psets`` object."""

    path: str  # "psets.valve_data.size_in", "psets.valve_data.x.nope", "psets.valve_data"
    # The JSON Schema keyword: type, minimum, maximum, pattern, enum, additionalProperties.
    keyword: str
    message: str


def _property_schema(prop: EffectiveProperty) -> dict[str, Any]:
    """The JSON Schema of one property, chosen by its kind."""
    out: dict[str, Any] = {"title": prop.label, "description": prop.description}
    kind = prop.kind
    if kind in ("string", "text", "ref"):
        out["type"] = "string"
        if prop.pattern is not None:
            out["pattern"] = prop.pattern
    elif kind == "int":
        out["type"] = "integer"
    elif kind in ("decimal", "quantity"):
        out["type"] = "number"
    elif kind == "bool":
        out["type"] = "boolean"
    elif kind == "date":
        out["type"] = "string"
        out["pattern"] = DATE_PATTERN
    elif kind == "datetime":
        out["type"] = "string"
        out["pattern"] = DATETIME_PATTERN
    elif kind == "enum":
        out["type"] = "string"
        out["enum"] = [v.code for v in prop.enum_values or []]
    # "json" adds nothing: any JSON value is accepted.
    if kind in _NUMERIC_KINDS:
        if prop.minimum is not None:
            out["minimum"] = prop.minimum
        if prop.maximum is not None:
            out["maximum"] = prop.maximum
    if prop.unit is not None:
        out["x-unit"] = prop.unit
    return out


def _pset_schema(pset: EffectivePset) -> dict[str, Any]:
    """The JSON Schema of one pset object, with its custom section ``x`` when it has one."""
    properties: dict[str, Any] = {
        name: _property_schema(prop) for name, prop in pset.properties.items()
    }
    if pset.custom:
        properties[_CUSTOM_KEY] = {
            "type": "object",
            "properties": {name: _property_schema(prop) for name, prop in pset.custom.items()},
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "title": pset.label,
        "description": pset.description,
        "properties": properties,
        "additionalProperties": False,
    }


def _build_document(schema: EffectiveSchema, record_type: str) -> dict[str, Any]:
    """The uncached document: standard psets at the root, project psets under ``prj``."""
    properties: dict[str, Any] = {}
    project: dict[str, Any] = {}
    for pset in schema.for_record_type(record_type):
        if pset.layer == "standard":
            properties[pset.name] = _pset_schema(pset)
        else:
            project[pset.name.removeprefix(_PROJECT_PREFIX)] = _pset_schema(pset)
    if project:
        properties[_PROJECT_ROOT] = {
            "type": "object",
            "properties": project,
            "additionalProperties": False,
        }
    return {
        "$schema": _SCHEMA_URI,
        "$id": f"urn:tl:effective:{schema.hash}:{record_type}",
        "title": f"{record_type} psets",
        "type": "object",
        "properties": properties,
        "additionalProperties": True,
    }


def record_json_schema(schema: EffectiveSchema, record_type: str) -> dict[str, Any]:
    """JSON Schema (draft 2020-12) of the ``psets`` object of ``record_type``.

    Built only from ``schema``; cached by ``schema.hash`` and ``record_type``; the returned
    dict must not be mutated by callers. See the ticket for the exact shape.
    """
    return _CACHE.get_or_build(
        schema, f"json:{record_type}", lambda: _build_document(schema, record_type)
    )


def validate_psets(
    schema: EffectiveSchema, record_type: str, psets: Mapping[str, Any]
) -> list[ValueIssue]:
    """Every violation of ``psets`` against ``record_json_schema``, sorted by ``(path, keyword)``.

    An ``additionalProperties`` violation yields one issue per unknown key, with that key at the
    end of ``path``. An empty list means the object is valid.
    """
    document = record_json_schema(schema, record_type)
    validator: Any = _CACHE.get_or_build(
        schema, f"validator:{record_type}", lambda: Draft202012Validator(document)
    )
    errors: list[Any] = list(validator.iter_errors(dict(psets)))
    found: set[ValueIssue] = set()
    for error in errors:
        base = ".".join(["psets", *(str(part) for part in error.absolute_path)])
        keyword = str(error.validator)
        if keyword == "additionalProperties":
            known: Any = error.schema.get("properties", {})
            for key in error.instance:
                if key not in known:
                    found.add(
                        ValueIssue(
                            path=f"{base}.{key}",
                            keyword=keyword,
                            message=f"{key!r} is not defined in the effective schema",
                        )
                    )
        else:
            found.add(ValueIssue(path=base, keyword=keyword, message=str(error.message)))
    return sorted(found, key=lambda issue: (issue.path, issue.keyword))
