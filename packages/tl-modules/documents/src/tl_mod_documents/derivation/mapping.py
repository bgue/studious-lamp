"""The publish mapping: declarative, checked against its LinkML model (ADR-0014).

A mapping says which column of a derived table becomes which field of the record a publication
creates. The format is declared in ``schema/modules/documents/publish_mapping.yaml``; the JSON
Schema generated from it (``tl_schema/generated/json_schema/documents.publish-mapping.schema.json``)
is what :func:`check_mapping` validates a mapping document against. The rest of the rules need the
document schema the mapping belongs to, so they are checked here: every mapped column is a property
of the row schema, the key column is the one mapped to ``number``, a target is one the kind takes,
nothing is mapped twice, and a translation table is only used on a text column.

The built-in targets are ``tags`` and ``documents``. Any other target registered on the group
``throughline.publish_targets`` is accepted too, with the fields it names in ``mapping_fields``
(the generated format schema lists only the two built-ins, so for a registered target the check
reads a copy of it that lists that target and a plain field name).
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any

import tl_schema.generated as _generated
from jsonschema import Draft201909Validator
from pydantic import BaseModel, ValidationError

from tl_mod_documents.derivation.publish_targets import publish_targets
from tl_mod_documents.names import TARGET_DOCUMENTS, TARGET_KINDS, TARGET_TAGS

TAG_FIELDS = ("number", "class", "service")
DOCUMENT_FIELDS = ("number", "title", "description", "doc_type", "discipline", "originator")
PSET_TARGET = re.compile(r"psets\.([a-z][a-z0-9_]*)\.((?:x\.)?[a-z][a-z0-9_]*)")
MAX_TRANSLATIONS = 500
MAX_TRANSLATION_TEXT = 200


class PublishColumn(BaseModel):
    column: str
    to: str
    values: dict[str, str] | None = None


class PublishMapping(BaseModel):
    target: str
    key_column: str
    columns: list[PublishColumn]
    note: str | None = None


class MappingInvalidError(ValueError):
    """A mapping that does not fit its format or its schema; ``problems`` lists every reason."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@cache
def _format_schema() -> dict[str, Any]:
    path = (
        Path(_generated.__file__).parent / "json_schema" / "documents.publish-mapping.schema.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


_FIELD_NAME = r"[a-z][a-z0-9_]*"


def known_targets() -> tuple[str, ...]:
    """The built-in targets, then the other registered ones, sorted."""
    extra = sorted(n for n in publish_targets() if n not in TARGET_KINDS)
    return (*TARGET_KINDS, *extra)


def known_target(name: str) -> bool:
    """Whether ``name`` is a built-in target or a registered one."""
    return name in TARGET_KINDS or name in publish_targets()


def _registered_fields(name: str) -> tuple[str, ...]:
    return tuple(getattr(publish_targets()[name], "mapping_fields", ("number",)))


def _format_for(raw: Mapping[str, Any]) -> dict[str, Any]:
    """The format schema; for a registered target other than the built-ins, a copy that takes it."""
    schema = _format_schema()
    name = raw.get("target")
    if not isinstance(name, str) or name in TARGET_KINDS or name not in publish_targets():
        return schema
    adapted = copy.deepcopy(schema)
    adapted["$defs"]["PublishTarget"]["enum"] = [name]
    adapted["$defs"]["PublishColumn"]["properties"]["to"]["pattern"] = (
        rf"^({_FIELD_NAME}|psets\.{_FIELD_NAME}\.(x\.)?{_FIELD_NAME})$"
    )
    return adapted


def _is_text(prop: Mapping[str, Any]) -> bool:
    declared = prop.get("type")
    names = [t for t in declared if t != "null"] if isinstance(declared, list) else [declared]  # pyright: ignore[reportUnknownVariableType]
    return names in ([None], ["string"])


def check_mapping(
    raw: Any, json_schema: Mapping[str, Any], target_kind: str | None
) -> PublishMapping:
    """The mapping, parsed, or ``MappingInvalidError`` listing every problem.

    ``raw`` is the mapping as data (a dict from YAML or JSON), ``json_schema`` the row schema of
    the document schema version it belongs to, ``target_kind`` that version's ``target_kind``.
    """
    if not isinstance(raw, dict):
        raise MappingInvalidError(["the mapping must be an object"])
    problems = [
        f"{'.'.join(str(p) for p in e.absolute_path) or '(mapping)'}: {e.message}"
        for e in sorted(
            Draft201909Validator(_format_for(raw)).iter_errors(raw),
            key=lambda e: [str(p) for p in e.absolute_path],
        )
    ]
    if problems:
        raise MappingInvalidError(problems)
    try:
        mapping = PublishMapping.model_validate(raw)
    except ValidationError as exc:
        raise MappingInvalidError(
            [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        ) from exc
    properties: Mapping[str, Any] = json_schema.get("properties", {})
    if not known_target(mapping.target):  # the format already says so; defence in depth
        problems.append(f"target {mapping.target!r} is not one of {', '.join(known_targets())}")
    if target_kind is None:
        problems.append("the document schema has no target_kind, so it cannot be published")
    elif mapping.target != target_kind:
        problems.append(
            f"the mapping publishes {mapping.target!r} but the schema's target_kind is "
            f"{target_kind!r}"
        )
    if mapping.target == TARGET_TAGS:
        fields = TAG_FIELDS
    elif mapping.target == TARGET_DOCUMENTS:
        fields = DOCUMENT_FIELDS
    elif known_target(mapping.target):
        fields = _registered_fields(mapping.target)
    else:
        fields = ()
    seen_columns: set[str] = set()
    seen_targets: set[str] = set()
    for entry in mapping.columns:
        prop = properties.get(entry.column)
        if prop is None:
            problems.append(f"column {entry.column!r} is not a property of the row schema")
        if entry.column in seen_columns:
            problems.append(f"column {entry.column!r} is mapped twice")
        seen_columns.add(entry.column)
        if entry.to in seen_targets:
            problems.append(f"two columns map to {entry.to}")
        seen_targets.add(entry.to)
        if entry.to not in fields:
            if PSET_TARGET.fullmatch(entry.to) is None:
                problems.append(f"{entry.to!r} is not a field a {mapping.target} row takes")
            elif mapping.target != TARGET_TAGS:
                problems.append(f"{entry.to!r}: only tags take property sets")
        if entry.values is not None:
            if len(entry.values) > MAX_TRANSLATIONS:
                problems.append(
                    f"column {entry.column!r}: more than {MAX_TRANSLATIONS} translations"
                )
            if any(
                len(k) > MAX_TRANSLATION_TEXT or len(v) > MAX_TRANSLATION_TEXT
                for k, v in entry.values.items()
            ):
                problems.append(
                    f"column {entry.column!r}: a translation is longer than "
                    f"{MAX_TRANSLATION_TEXT} characters"
                )
            if isinstance(prop, Mapping) and not _is_text(prop):  # pyright: ignore[reportUnknownArgumentType]
                problems.append(f"column {entry.column!r}: translations apply to text columns only")
    numbered = [e for e in mapping.columns if e.to == "number"]
    if len(numbered) != 1:
        problems.append("exactly one column must map to number")
    elif numbered[0].column != mapping.key_column:
        problems.append(
            f"key_column {mapping.key_column!r} must be the column mapped to number "
            f"({numbered[0].column!r})"
        )
    if mapping.target == TARGET_DOCUMENTS and "title" not in seen_targets:
        problems.append("a document needs a title: map a column to title")
    if mapping.key_column not in properties:
        problems.append(f"key_column {mapping.key_column!r} is not a property of the row schema")
    if problems:
        raise MappingInvalidError(problems)
    return mapping
