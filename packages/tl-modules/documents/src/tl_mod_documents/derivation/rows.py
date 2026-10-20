"""Reading the derivation tables: document schemas, derived documents, content revisions and jobs.

Every function takes a connection (``uow.conn()`` inside a unit of work, a read transaction
elsewhere) and returns frozen rows read from the module's flat views (``v_documents_<class>``) and
the content table. Nothing here writes. JSON columns come back as Python values on both adapters,
booleans as ``bool``. A record that never moved is in its workflow's first state: a derived
document's ``state`` is then ``Pending``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text
from tl_core import confidentiality

from tl_mod_documents.names import (
    DD_PENDING,
    DERIVED_CONTENT_TABLE,
    DERIVED_DOCUMENT_VIEW,
    DOCUMENT_SCHEMA_VIEW,
    PROCESSING_JOB_VIEW,
)


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value) if isinstance(value, str) else value


@dataclass(frozen=True)
class SchemaRow:
    id: str
    scope: str
    key: str  # <code>@<semver>
    title: str
    code: str
    semver: str
    ordinal: int
    target_kind: str | None
    key_column: str | None
    json_schema: dict[str, Any]
    sample: list[dict[str, Any]]
    mapping: dict[str, Any] | None
    mapping_notes: str | None
    doc_types: list[str]
    content_hash: str
    is_active: bool
    retired_reason: str | None
    version: int  # the stream version
    created_at: str


@dataclass(frozen=True)
class DerivedRow:
    id: str
    scope: str
    key: str  # <number>@<revision>/<schema code>
    title: str
    state: str  # Pending, Processing, Invalid, Valid, Published, Void
    voided: bool
    version: int
    source_document_id: str
    source_revision_id: str
    source_document_number: str
    source_revision_code: str
    source_ref: str  # src.doc.<number>@<revision>
    schema_id: str
    schema_code: str
    schema_version: str
    method: str
    previous_derived_id: str | None
    content_rev: int
    published_rev: int | None
    validation_status: str  # none, valid, invalid
    row_count: int | None
    error_count: int | None
    published_correlation_id: str | None
    published_at: str | None
    published_count: int | None
    last_job_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ContentRow:
    content_id: str
    scope: str
    derived_id: str
    content_rev: int
    job_id: str | None
    source_kind: str  # rendition | upload
    source_file_id: str
    extractor: str
    extractor_version: str
    extraction_status: str
    result_file_id: str | None
    result_sha256: str | None
    row_count: int
    column_count: int
    problem_count: int
    file_metadata: dict[str, Any] | None
    extractor_notes: list[str]
    schema_id: str | None
    schema_version: str | None
    validation_status: str  # none, valid, invalid
    error_count: int
    warning_count: int
    report_file_id: str | None
    report_sha256: str | None
    published: bool
    created_at: str


@dataclass(frozen=True)
class JobRow:
    id: str
    scope: str
    key: str
    kind: str
    derived_id: str
    derived_key: str
    source_ref: str
    source_file_id: str | None
    extractor: str | None
    options: dict[str, Any]
    schema_id: str
    requested_by: str
    state: str  # queued, running, succeeded, failed, cancelled
    attempt: int
    max_attempts: int
    worker: str | None
    started_at: str | None
    finished_at: str | None
    error_code: str | None
    error_message: str | None
    result: dict[str, Any] | None
    created_seq: int
    version: int
    created_at: str

    @property
    def active(self) -> bool:
        return self.state in ("queued", "running")


# --- document schemas ------------------------------------------------------------------------

_SCHEMA_COLUMNS = (
    "id, scope, key, title, code, semver, ordinal, target_kind, key_column, json_schema_json, "
    "sample_json, mapping_json, mapping_notes, doc_types_json, content_hash, is_active, "
    "retired_reason, version, created_at"
)
_SCHEMA_SELECT = f"SELECT {_SCHEMA_COLUMNS} FROM {DOCUMENT_SCHEMA_VIEW} WHERE voided = :no"


def _schema(row: Any) -> SchemaRow:
    return SchemaRow(
        id=row.id,
        scope=row.scope,
        key=row.key,
        title=row.title,
        code=row.code,
        semver=row.semver,
        ordinal=int(row.ordinal),
        target_kind=row.target_kind,
        key_column=row.key_column,
        json_schema=dict(_json(row.json_schema_json, {})),
        sample=list(_json(row.sample_json, [])),
        mapping=_json(row.mapping_json, None),
        mapping_notes=row.mapping_notes,
        doc_types=list(_json(row.doc_types_json, [])),
        content_hash=row.content_hash,
        is_active=bool(row.is_active),
        retired_reason=row.retired_reason,
        version=int(row.version),
        created_at=str(row.created_at),
    )


def get_schema(conn: Connection, schema_id: str) -> SchemaRow | None:
    row = conn.execute(
        text(f"SELECT {_SCHEMA_COLUMNS} FROM {DOCUMENT_SCHEMA_VIEW} WHERE id = :id"),
        {"id": schema_id},
    ).first()
    return None if row is None else _schema(row)


def list_schemas(
    conn: Connection,
    scope: str | None = None,
    *,
    code: str | None = None,
    active_only: bool = False,
) -> list[SchemaRow]:
    """Schema versions, by scope, code and ordinal. ``scope`` None lists every scope."""
    sql = _SCHEMA_SELECT
    params: dict[str, Any] = {"no": False}
    if scope is not None:
        sql += " AND scope = :scope"
        params["scope"] = scope
    if code is not None:
        sql += " AND code = :code"
        params["code"] = code
    if active_only:
        sql += " AND is_active = :yes"
        params["yes"] = True
    sql += " ORDER BY scope, code, ordinal"
    return [_schema(r) for r in conn.execute(text(sql), params).all()]


def find_schema(
    conn: Connection, scope: str, code: str, semver: str | None = None
) -> SchemaRow | None:
    """A schema in exactly ``scope``: the version ``semver``, or the newest active one."""
    if semver is not None:
        row = conn.execute(
            text(_SCHEMA_SELECT + " AND scope = :scope AND code = :code AND semver = :semver"),
            {"no": False, "scope": scope, "code": code, "semver": semver},
        ).first()
        return None if row is None else _schema(row)
    row = conn.execute(
        text(
            _SCHEMA_SELECT
            + " AND scope = :scope AND code = :code AND is_active = :yes ORDER BY ordinal DESC"
        ),
        {"no": False, "scope": scope, "code": code, "yes": True},
    ).first()
    return None if row is None else _schema(row)


def resolve_schema(
    conn: Connection, project_scope: str, code: str, semver: str | None = None
) -> SchemaRow | None:
    """A schema as a project sees it: its own scope first, then the company's."""
    found = find_schema(conn, project_scope, code, semver)
    if found is not None or project_scope == "company":
        return found
    return find_schema(conn, "company", code, semver)


def next_schema_ordinal(conn: Connection, scope: str, code: str) -> int:
    row = conn.execute(
        text(
            f"SELECT COALESCE(MAX(ordinal), 0) FROM {DOCUMENT_SCHEMA_VIEW} "
            "WHERE scope = :scope AND code = :code"
        ),
        {"scope": scope, "code": code},
    ).scalar_one()
    return int(row) + 1


# --- derived documents -----------------------------------------------------------------------

_DERIVED_COLUMNS = (
    "id, scope, key, title, status, voided, version, source_document_id, source_revision_id, "
    "source_document_number, source_revision_code, source_ref, schema_id, schema_code, "
    "schema_version, method, previous_derived_id, content_rev, published_rev, validation_status, "
    "row_count, error_count, published_correlation_id, published_at, published_count, "
    "last_job_id, created_at, updated_at"
)


def _derived(row: Any) -> DerivedRow:
    return DerivedRow(
        id=row.id,
        scope=row.scope,
        key=row.key,
        title=row.title,
        state="Void" if bool(row.voided) else (row.status or DD_PENDING),
        voided=bool(row.voided),
        version=int(row.version),
        source_document_id=row.source_document_id,
        source_revision_id=row.source_revision_id,
        source_document_number=row.source_document_number,
        source_revision_code=row.source_revision_code,
        source_ref=row.source_ref,
        schema_id=row.schema_id,
        schema_code=row.schema_code,
        schema_version=row.schema_version,
        method=row.method,
        previous_derived_id=row.previous_derived_id,
        content_rev=int(row.content_rev),
        published_rev=None if row.published_rev is None else int(row.published_rev),
        validation_status=row.validation_status,
        row_count=None if row.row_count is None else int(row.row_count),
        error_count=None if row.error_count is None else int(row.error_count),
        published_correlation_id=row.published_correlation_id,
        published_at=row.published_at,
        published_count=None if row.published_count is None else int(row.published_count),
        last_job_id=row.last_job_id,
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def _hidden(conn: Connection, record_id: str) -> bool:
    """The viewer may not read this record (ADR-0016): a derived document or job hangs on a
    document, and is as hidden as it."""
    return confidentiality.is_hidden(conn, record_id)


def get_derived(conn: Connection, derived_id: str) -> DerivedRow | None:
    row = conn.execute(
        text(f"SELECT {_DERIVED_COLUMNS} FROM {DERIVED_DOCUMENT_VIEW} WHERE id = :id"),
        {"id": derived_id},
    ).first()
    return None if row is None or _hidden(conn, derived_id) else _derived(row)


def find_derived(
    conn: Connection, scope: str, revision_id: str, schema_code: str
) -> DerivedRow | None:
    """The derived document of a revision for a schema code (at most one)."""
    row = conn.execute(
        text(
            f"SELECT {_DERIVED_COLUMNS} FROM {DERIVED_DOCUMENT_VIEW} WHERE scope = :scope "
            "AND source_revision_id = :rev AND schema_code = :code"
        ),
        {"scope": scope, "rev": revision_id, "code": schema_code},
    ).first()
    return None if row is None or _hidden(conn, row.id) else _derived(row)


def find_derived_by_key(conn: Connection, scope: str, key: str) -> DerivedRow | None:
    row = conn.execute(
        text(
            f"SELECT {_DERIVED_COLUMNS} FROM {DERIVED_DOCUMENT_VIEW} "
            "WHERE scope = :scope AND key = :key"
        ),
        {"scope": scope, "key": key},
    ).first()
    return None if row is None or _hidden(conn, row.id) else _derived(row)


def list_derived(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    document_number: str | None = None,
    schema_code: str | None = None,
    include_void: bool = False,
    limit: int = 200,
) -> list[DerivedRow]:
    """Derived documents of a project, newest first (by creation, then key)."""
    sql = f"SELECT {_DERIVED_COLUMNS} FROM {DERIVED_DOCUMENT_VIEW} WHERE scope = :scope"
    params: dict[str, Any] = {"scope": scope, "limit": limit}
    visible, visible_params = confidentiality.not_hidden("id")
    sql += f" AND {visible}"
    params.update(visible_params)
    if not include_void:
        sql += " AND voided = :no"
        params["no"] = False
    if state is not None:
        sql += " AND COALESCE(status, 'Pending') = :state"
        params["state"] = state
    if document_number is not None:
        sql += " AND source_document_number = :number"
        params["number"] = document_number
    if schema_code is not None:
        sql += " AND schema_code = :code"
        params["code"] = schema_code
    sql += " ORDER BY created_at DESC, key LIMIT :limit"
    return [_derived(r) for r in conn.execute(text(sql), params).all()]


def previous_derived(
    conn: Connection, scope: str, document_id: str, schema_code: str, before_ordinal: int
) -> DerivedRow | None:
    """The derived document of the closest earlier revision of the same document and schema code.

    ``before_ordinal`` is the ordinal of the revision being derived now; the earlier revision with
    the highest ordinal that has a derived document wins.
    """
    row = conn.execute(
        text(
            f"SELECT {', '.join('d.' + c.strip() for c in _DERIVED_COLUMNS.split(','))} "
            f"FROM {DERIVED_DOCUMENT_VIEW} d JOIN v_documents_revision rv "
            "ON rv.id = d.source_revision_id "
            "WHERE d.scope = :scope AND d.source_document_id = :doc AND d.schema_code = :code "
            "AND d.voided = :no AND rv.ordinal < :ord ORDER BY rv.ordinal DESC"
        ),
        {
            "scope": scope,
            "doc": document_id,
            "code": schema_code,
            "no": False,
            "ord": before_ordinal,
        },
    ).first()
    return None if row is None or _hidden(conn, row.id) else _derived(row)


# --- content revisions -----------------------------------------------------------------------

_CONTENT_COLUMNS = (
    "content_id, scope, derived_id, content_rev, job_id, source_kind, source_file_id, extractor, "
    "extractor_version, extraction_status, result_file_id, result_sha256, row_count, column_count, "
    "problem_count, file_metadata_json, extractor_notes_json, schema_id, schema_version, "
    "validation_status, error_count, warning_count, report_file_id, report_sha256, published, "
    "created_at"
)


def _content(row: Any) -> ContentRow:
    return ContentRow(
        content_id=row.content_id,
        scope=row.scope,
        derived_id=row.derived_id,
        content_rev=int(row.content_rev),
        job_id=row.job_id,
        source_kind=row.source_kind,
        source_file_id=row.source_file_id,
        extractor=row.extractor,
        extractor_version=row.extractor_version,
        extraction_status=row.extraction_status,
        result_file_id=row.result_file_id,
        result_sha256=row.result_sha256,
        row_count=int(row.row_count),
        column_count=int(row.column_count),
        problem_count=int(row.problem_count),
        file_metadata=_json(row.file_metadata_json, None),
        extractor_notes=list(_json(row.extractor_notes_json, [])),
        schema_id=row.schema_id,
        schema_version=row.schema_version,
        validation_status=row.validation_status,
        error_count=int(row.error_count),
        warning_count=int(row.warning_count),
        report_file_id=row.report_file_id,
        report_sha256=row.report_sha256,
        published=bool(row.published),
        created_at=str(row.created_at),
    )


def contents_of(conn: Connection, derived_id: str) -> list[ContentRow]:
    """Every content revision of a derived document, oldest first."""
    if _hidden(conn, derived_id):
        return []
    rows = conn.execute(
        text(
            f"SELECT {_CONTENT_COLUMNS} FROM {DERIVED_CONTENT_TABLE} "
            "WHERE derived_id = :id ORDER BY content_rev"
        ),
        {"id": derived_id},
    ).all()
    return [_content(r) for r in rows]


def get_content(conn: Connection, derived_id: str, content_rev: int) -> ContentRow | None:
    if _hidden(conn, derived_id):
        return None
    row = conn.execute(
        text(
            f"SELECT {_CONTENT_COLUMNS} FROM {DERIVED_CONTENT_TABLE} "
            "WHERE derived_id = :id AND content_rev = :rev"
        ),
        {"id": derived_id, "rev": content_rev},
    ).first()
    return None if row is None else _content(row)


# --- jobs ------------------------------------------------------------------------------------

_JOB_COLUMNS = (
    "id, scope, key, kind, derived_id, derived_key, source_ref, source_file_id, extractor, "
    "options_json, schema_id, requested_by, state, attempt, max_attempts, worker, started_at, "
    "finished_at, error_code, error_message, result_json, created_seq, version, created_at"
)


def _job(row: Any) -> JobRow:
    return JobRow(
        id=row.id,
        scope=row.scope,
        key=row.key,
        kind=row.kind,
        derived_id=row.derived_id,
        derived_key=row.derived_key,
        source_ref=row.source_ref,
        source_file_id=row.source_file_id,
        extractor=row.extractor,
        options=dict(_json(row.options_json, {})),
        schema_id=row.schema_id,
        requested_by=row.requested_by,
        state=row.state,
        attempt=int(row.attempt),
        max_attempts=int(row.max_attempts),
        worker=row.worker,
        started_at=row.started_at,
        finished_at=row.finished_at,
        error_code=row.error_code,
        error_message=row.error_message,
        result=_json(row.result_json, None),
        created_seq=int(row.created_seq),
        version=int(row.version),
        created_at=str(row.created_at),
    )


def get_job(conn: Connection, job_id: str) -> JobRow | None:
    row = conn.execute(
        text(f"SELECT {_JOB_COLUMNS} FROM {PROCESSING_JOB_VIEW} WHERE id = :id"), {"id": job_id}
    ).first()
    return None if row is None or _hidden(conn, job_id) else _job(row)


def list_jobs(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    derived_id: str | None = None,
    limit: int = 200,
) -> list[JobRow]:
    """Jobs of a project, newest first."""
    sql = f"SELECT {_JOB_COLUMNS} FROM {PROCESSING_JOB_VIEW} WHERE scope = :scope"
    params: dict[str, Any] = {"scope": scope, "limit": limit}
    visible, visible_params = confidentiality.not_hidden("id")
    sql += f" AND {visible}"
    params.update(visible_params)
    if state is not None:
        sql += " AND state = :state"
        params["state"] = state
    if derived_id is not None:
        sql += " AND derived_id = :derived"
        params["derived"] = derived_id
    sql += " ORDER BY created_seq DESC LIMIT :limit"
    return [_job(r) for r in conn.execute(text(sql), params).all()]


def active_job(conn: Connection, derived_id: str) -> JobRow | None:
    """The queued or running job of a derived document, if there is one."""
    if _hidden(conn, derived_id):
        return None
    row = conn.execute(
        text(
            f"SELECT {_JOB_COLUMNS} FROM {PROCESSING_JOB_VIEW} WHERE derived_id = :derived "
            "AND state IN ('queued', 'running') ORDER BY created_seq DESC"
        ),
        {"derived": derived_id},
    ).first()
    return None if row is None else _job(row)
