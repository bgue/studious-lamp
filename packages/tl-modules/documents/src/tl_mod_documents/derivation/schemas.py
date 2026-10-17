"""Document schemas: register a version, retire a version (brief 9 M1; ADR-0014).

A ``DocumentSchema`` is registry data like the engineering standards, so registering and retiring
one is the admin's (gated in the command table). A version is never edited: a change is a new
version with a higher number, and ``RetireDocumentSchema`` stops new work from picking an older
one. Everything a person could get wrong is checked here, before anything is written, and listed
at once (``InvalidDocumentSchemaError.problems``): the JSON Schema is valid and local (no remote
``$ref``), every property is named, the key column is a property, the sample rows validate, and
the mapping fits its format and the row schema (``check_mapping``).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import ConfigDict, Field, field_validator
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_documents.derivation import rows
from tl_mod_documents.derivation.mapping import MappingInvalidError, check_mapping
from tl_mod_documents.derivation.validation import validate_result
from tl_mod_documents.errors import InvalidDocumentSchemaError, SchemaNotFoundError
from tl_mod_documents.handlers.common import append, correlated
from tl_mod_documents.limits import MAX_DESCRIPTION, MAX_REASON, MAX_TEXT
from tl_mod_documents.names import DOCUMENT_SCHEMA, DOCUMENT_SCHEMA_DEFINED, DOCUMENT_SCHEMA_RETIRED

CODE = re.compile(r"[a-z][a-z0-9-]{0,62}")
SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
MAX_SCHEMA_BYTES = 256 * 1024
MAX_PROPERTIES = 200
MAX_SAMPLE_ROWS = 20
MAX_DOC_TYPES = 50


def semver_key(text: str) -> tuple[int, int, int]:
    major, minor, patch = (int(part) for part in text.split("."))
    return major, minor, patch


class RegisterDocumentSchema(Command):
    """Register a new version of a document schema (admin).

    ``scope`` is ``company`` (a company standard) or a project (that project's own variant).
    ``mapping`` and ``target_kind`` go together: a schema that names what its rows are published
    as carries the mapping that does it; one with neither can only validate.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=63)
    semver: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=MAX_TEXT)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    json_schema: dict[str, Any]
    sample: list[dict[str, str | None]] = Field(default_factory=list[dict[str, str | None]])
    mapping: dict[str, Any] | None = None
    mapping_notes: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    target_kind: Literal["tags", "documents"] | None = None
    key_column: str | None = Field(default=None, max_length=MAX_TEXT)
    doc_types: list[str] = Field(default_factory=list[str], max_length=MAX_DOC_TYPES)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class RetireDocumentSchema(Command):
    """Retire a version: new work no longer picks it; documents that named it keep it (admin)."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


def _remote_refs(node: Any, path: str = "") -> list[str]:
    """Every ``$ref`` or ``$dynamicRef`` that does not point inside the document."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():  # pyright: ignore[reportUnknownVariableType]
            if key in ("$ref", "$dynamicRef") and not (
                isinstance(value, str) and value.startswith("#")
            ):
                found.append(f"{path}/{key}")
            found.extend(_remote_refs(value, f"{path}/{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):  # pyright: ignore[reportUnknownVariableType]
            found.extend(_remote_refs(value, f"{path}/{index}"))
    return found


def content_hash(
    json_schema: dict[str, Any],
    mapping: dict[str, Any] | None,
    key_column: str | None,
    target_kind: str | None,
) -> str:
    """Hex SHA-256 of the canonical JSON of everything that decides how rows are judged and used."""
    body = {
        "json_schema": json_schema,
        "mapping": mapping,
        "key_column": key_column,
        "target_kind": target_kind,
    }
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def schema_problems(cmd: RegisterDocumentSchema) -> list[str]:
    """Why this schema cannot be registered (empty when it can). Reads nothing."""
    problems: list[str] = []
    if CODE.fullmatch(cmd.code) is None:
        problems.append(
            "code must be lower case letters, digits and hyphens, starting with a letter"
        )
    if SEMVER.fullmatch(cmd.semver) is None:
        problems.append("semver must be major.minor.patch, for example 1.0.0")
    if not (cmd.scope == "company" or cmd.scope.startswith("project:")):
        problems.append("a document schema belongs to the company or to a project")
    size = len(json.dumps(cmd.json_schema, ensure_ascii=False))
    if size > MAX_SCHEMA_BYTES:
        problems.append(f"the JSON Schema is larger than {MAX_SCHEMA_BYTES} characters")
        return problems
    try:
        Draft202012Validator.check_schema(cmd.json_schema)
    except SchemaError as exc:
        problems.append(f"json_schema is not a valid JSON Schema: {exc.message[:200]}")
        return problems
    remote = _remote_refs(cmd.json_schema)
    if remote:
        problems.append(f"json_schema may refer only to itself ('#...'); found {', '.join(remote)}")
    properties = cmd.json_schema.get("properties")
    if (
        cmd.json_schema.get("type") != "object"
        or not isinstance(properties, dict)
        or not properties
    ):
        problems.append("json_schema must describe a row: type object with properties")
        return problems
    names = [str(n) for n in properties]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    if len(names) > MAX_PROPERTIES:
        problems.append(f"more than {MAX_PROPERTIES} properties")
    if any(not n.strip() or n != n.strip() for n in names):
        problems.append("a property name is blank or has spaces at its ends")
    if (cmd.mapping is None) != (cmd.target_kind is None):
        problems.append("mapping and target_kind go together: give both or neither")
    if cmd.target_kind is not None and cmd.key_column is None:
        problems.append("a schema that names a target needs a key_column")
    if cmd.key_column is not None and cmd.key_column not in properties:
        problems.append(f"key_column {cmd.key_column!r} is not a property")
    if len(cmd.sample) > MAX_SAMPLE_ROWS:
        problems.append(f"at most {MAX_SAMPLE_ROWS} sample rows")
    elif cmd.sample:
        columns = list(cmd.sample[0])
        report = validate_result(
            cmd.json_schema,
            columns,
            cmd.sample,
            schema_code=cmd.code,
            schema_version=cmd.semver,
            key_column=cmd.key_column,
        )
        problems.extend(
            f"sample row {i.row}: {i.column or ''} {i.message}".replace("  ", " ")
            for i in report.issues
            if i.level == "error"
        )
    if cmd.mapping is not None:
        try:
            check_mapping(cmd.mapping, cmd.json_schema, cmd.target_kind)
        except MappingInvalidError as exc:
            problems.extend(f"mapping: {p}" for p in exc.problems)
    if len(cmd.doc_types) != len(set(cmd.doc_types)) or any(not d.strip() for d in cmd.doc_types):
        problems.append("doc_types must be distinct, non-blank codes")
    return problems


def handle_register_document_schema(uow: UnitOfWork, cmd: RegisterDocumentSchema) -> CommandResult:
    """Append ``Record.Created`` and ``DocumentSchema.Defined`` for a new version.

    Raises ``InvalidDocumentSchemaError`` (every problem listed), including a version that is not
    higher than the latest of the same code in the scope, and ``DuplicateKeyError`` for a version
    that exists.
    """
    cmd = correlated(cmd)
    problems = schema_problems(cmd)
    conn = uow.conn()
    if not problems:
        latest = rows.list_schemas(conn, cmd.scope, code=cmd.code)
        if latest and semver_key(cmd.semver) <= max(semver_key(r.semver) for r in latest):
            problems.append(
                f"version {cmd.semver} must be higher than "
                f"{max((r.semver for r in latest), key=semver_key)}"
            )
    if problems:
        raise InvalidDocumentSchemaError(
            f"document schema {cmd.code}@{cmd.semver} cannot be registered: " + "; ".join(problems),
            problems,
        )
    ordinal = rows.next_schema_ordinal(conn, cmd.scope, cmd.code)
    return create_module_record(
        uow,
        cmd,
        record_type=DOCUMENT_SCHEMA,
        title=cmd.title,
        description=cmd.description,
        key=f"{cmd.code}@{cmd.semver}",
        composed_key=True,
        extra_events=[
            NewEvent(
                event_type=DOCUMENT_SCHEMA_DEFINED,
                payload={
                    "code": cmd.code,
                    "semver": cmd.semver,
                    "ordinal": ordinal,
                    "target_kind": cmd.target_kind,
                    "key_column": cmd.key_column,
                    "json_schema": cmd.json_schema,
                    "sample": cmd.sample,
                    "mapping": cmd.mapping,
                    "mapping_notes": cmd.mapping_notes,
                    "doc_types": cmd.doc_types,
                    "content_hash": content_hash(
                        cmd.json_schema, cmd.mapping, cmd.key_column, cmd.target_kind
                    ),
                },
            )
        ],
    )


def handle_retire_document_schema(uow: UnitOfWork, cmd: RetireDocumentSchema) -> CommandResult:
    """Append ``DocumentSchema.Retired``.

    Raises ``SchemaNotFoundError`` and ``InvalidDocumentSchemaError`` (already retired).
    """
    cmd = correlated(cmd)
    found = rows.get_schema(uow.conn(), cmd.stream_id)
    if found is None or found.scope != cmd.scope:
        raise SchemaNotFoundError(f"no document schema {cmd.stream_id!r} in scope {cmd.scope!r}")
    if not found.is_active:
        raise InvalidDocumentSchemaError(f"{found.key} is already retired")
    made = append(
        uow,
        cmd,
        found.id,
        DOCUMENT_SCHEMA,
        [NewEvent(event_type=DOCUMENT_SCHEMA_RETIRED, payload={"reason": cmd.reason})],
        expected=cmd.expected_version,
    )
    return CommandResult(
        stream_id=found.id, key=found.key, version=made.new_version, events=made.events
    )
