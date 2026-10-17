"""Reads of the derivation pipeline: schemas, derived documents, jobs, rows, reports and diffs.

The models are what the API returns, the CLI and the TUI show and the MCP tools hand to an agent
(ADR-0014); they are built from the flat rows of ``rows`` and from the stored result and report
files. Every function takes a connection or a read unit of work and writes nothing. A reference to
a derived document is its id or its key (``ISD-001@A/instrument-index``); a reference to a schema
is its code, or ``code@semver``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection
from tl_core.derivation.types import Cell, ExtractionProblem
from tl_core.uow import UnitOfWork

from tl_mod_documents.derivation import rows, store
from tl_mod_documents.derivation.diff import DerivedDiff, diff_rows
from tl_mod_documents.derivation.publish import (
    CompensationPlan,
    PublishPlan,
    preview_compensation,
    preview_publication,
)
from tl_mod_documents.derivation.validation import ValidationReport, validate_result
from tl_mod_documents.errors import (
    DerivedNotFoundError,
    DerivedStateError,
    JobNotFoundError,
    SchemaNotFoundError,
)

#: A page of rows is at most this long.
MAX_PAGE = 500


class _View(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)


class SchemaSummary(_View):
    id: str
    scope: str
    key: str
    title: str
    code: str
    semver: str
    ordinal: int
    target_kind: str | None
    key_column: str | None
    doc_types: list[str]
    content_hash: str
    is_active: bool
    retired_reason: str | None
    created_at: str


class SchemaView(SchemaSummary):
    json_schema: dict[str, Any]
    sample: list[dict[str, Any]]
    mapping: dict[str, Any] | None
    mapping_notes: str | None


class JobView(_View):
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
    state: str
    attempt: int
    max_attempts: int
    worker: str | None
    started_at: str | None
    finished_at: str | None
    error_code: str | None
    error_message: str | None
    result: dict[str, Any] | None
    created_at: str


class ContentView(_View):
    content_rev: int
    job_id: str | None
    source_kind: str
    source_file_id: str
    extractor: str
    extractor_version: str
    extraction_status: str
    result_file_id: str | None
    row_count: int
    column_count: int
    problem_count: int
    file_metadata: dict[str, Any] | None
    extractor_notes: list[str]
    schema_version: str | None
    validation_status: str
    error_count: int
    warning_count: int
    report_file_id: str | None
    published: bool
    created_at: str


class DerivedSummary(_View):
    id: str
    scope: str
    key: str
    title: str
    state: str
    version: int
    source_document_id: str
    source_revision_id: str
    source_document_number: str
    source_revision_code: str
    source_ref: str
    schema_id: str
    schema_code: str
    schema_version: str
    method: str
    previous_derived_id: str | None
    content_rev: int
    published_rev: int | None
    validation_status: str
    row_count: int | None
    error_count: int | None
    published_correlation_id: str | None
    published_at: str | None
    published_count: int | None
    last_job_id: str | None
    created_at: str
    updated_at: str


class DerivedView(DerivedSummary):
    contents: list[ContentView] = Field(default_factory=list[ContentView])
    active_job: JobView | None = None


class RowsPage(BaseModel):
    """A page of the rows of one content revision, as the extractor read them (all text)."""

    derived_id: str
    content_rev: int
    extractor: str
    columns: list[str]
    total: int
    offset: int
    rows: list[dict[str, Cell]]
    problems: list[ExtractionProblem]
    notes: list[str]


# --- schemas ---------------------------------------------------------------------------------


def schema_summaries(
    conn: Connection, scope: str, *, code: str | None = None, active_only: bool = True
) -> list[SchemaSummary]:
    """The schemas a project sees: its own and the company's, by code and version."""
    scopes = [scope] if scope == "company" else [scope, "company"]
    found = [
        s for sc in scopes for s in rows.list_schemas(conn, sc, code=code, active_only=active_only)
    ]
    return [SchemaSummary.model_validate(s) for s in found]


def schema_view(conn: Connection, scope: str, ref: str) -> SchemaView:
    """One schema by ``code`` (the newest active version) or ``code@semver``."""
    code, _, semver = ref.partition("@")
    found = rows.resolve_schema(conn, scope, code, semver or None)
    if found is None:
        raise SchemaNotFoundError(f"no document schema {ref!r} for {scope}")
    return SchemaView.model_validate(found)


# --- jobs ------------------------------------------------------------------------------------


def job_views(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    derived: str | None = None,
    limit: int = 200,
) -> list[JobView]:
    derived_id = find_derived(conn, scope, derived).id if derived is not None else None
    found = rows.list_jobs(conn, scope, state=state, derived_id=derived_id, limit=limit)
    return [JobView.model_validate(j) for j in found]


def job_view(conn: Connection, scope: str, job_id: str) -> JobView:
    found = rows.get_job(conn, job_id)
    if found is None or found.scope != scope:
        raise JobNotFoundError(f"no job {job_id!r} in scope {scope!r}")
    return JobView.model_validate(found)


# --- derived documents -----------------------------------------------------------------------


def find_derived(conn: Connection, scope: str, ref: str) -> rows.DerivedRow:
    """A derived document of ``scope`` by id or by key."""
    found = rows.get_derived(conn, ref)
    if found is None or found.scope != scope:
        found = rows.find_derived_by_key(conn, scope, ref)
    if found is None:
        raise DerivedNotFoundError(f"no derived document {ref!r} in scope {scope!r}")
    return found


def derived_summaries(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    document: str | None = None,
    schema_code: str | None = None,
    include_void: bool = False,
    limit: int = 200,
) -> list[DerivedSummary]:
    found = rows.list_derived(
        conn,
        scope,
        state=state,
        document_number=document,
        schema_code=schema_code,
        include_void=include_void,
        limit=limit,
    )
    return [DerivedSummary.model_validate(d) for d in found]


def derived_view(conn: Connection, scope: str, ref: str) -> DerivedView:
    """One derived document with its content revisions and its running job."""
    found = find_derived(conn, scope, ref)
    active = rows.active_job(conn, found.id)
    base = DerivedSummary.model_validate(found).model_dump()
    return DerivedView(
        **base,
        contents=[ContentView.model_validate(c) for c in rows.contents_of(conn, found.id)],
        active_job=JobView.model_validate(active) if active is not None else None,
    )


def _content(conn: Connection, derived: rows.DerivedRow, rev: int | None) -> rows.ContentRow:
    wanted = derived.content_rev if rev is None else rev
    content = rows.get_content(conn, derived.id, wanted) if wanted > 0 else None
    if content is None:
        raise DerivedStateError(
            f"{derived.key} has no content revision {wanted}"
            if wanted > 0
            else f"{derived.key} has no extracted data yet"
        )
    return content


def derived_rows(
    uow: UnitOfWork,
    scope: str,
    ref: str,
    *,
    content_rev: int | None = None,
    offset: int = 0,
    limit: int = 100,
) -> RowsPage:
    """A page of the rows of a content revision (the latest by default)."""
    derived = find_derived(uow.conn(), scope, ref)
    content = _content(uow.conn(), derived, content_rev)
    if content.result_file_id is None:
        raise DerivedStateError(f"{derived.key} revision {content.content_rev} stored no rows")
    result = store.result_files().read_result(
        uow, scope, content.result_file_id, content.result_sha256
    )
    start = max(offset, 0)
    return RowsPage(
        derived_id=derived.id,
        content_rev=content.content_rev,
        extractor=result.extractor,
        columns=result.columns,
        total=len(result.rows),
        offset=start,
        rows=result.rows[start : start + min(max(limit, 1), MAX_PAGE)],
        problems=result.problems,
        notes=result.notes,
    )


def derived_report(
    uow: UnitOfWork, scope: str, ref: str, *, content_rev: int | None = None
) -> ValidationReport:
    """The stored validation report of a content revision (the latest by default)."""
    derived = find_derived(uow.conn(), scope, ref)
    content = _content(uow.conn(), derived, content_rev)
    if content.report_file_id is None:
        raise DerivedStateError(
            f"{derived.key} revision {content.content_rev} has not been validated"
        )
    data = store.result_files().read(
        uow, scope, content.report_file_id, expect_sha256=content.report_sha256
    )
    return ValidationReport.model_validate_json(data)


def derived_diff(
    uow: UnitOfWork,
    scope: str,
    ref: str,
    *,
    against: str = "previous_pass",
    content_rev: int | None = None,
) -> DerivedDiff:
    """What changed in a content revision (the latest by default) against an earlier one.

    ``against`` is ``previous_pass`` (the revision before it, of the same derived document) or
    ``previous_revision`` (the latest pass of the derived document of the source document's
    previous revision, same schema code). ``DerivedStateError`` when there is nothing to compare.
    """
    conn = uow.conn()
    derived = find_derived(conn, scope, ref)
    new = _content(conn, derived, content_rev)
    schema = rows.get_schema(conn, derived.schema_id)
    if schema is None or schema.key_column is None:
        raise DerivedStateError(f"{derived.key}: its schema names no key column to compare by")
    if against == "previous_pass":
        old_derived, old = derived, rows.get_content(conn, derived.id, new.content_rev - 1)
    elif against == "previous_revision":
        old_derived = (
            rows.get_derived(conn, derived.previous_derived_id)
            if derived.previous_derived_id
            else None
        )
        old = (
            rows.get_content(conn, old_derived.id, old_derived.content_rev)
            if old_derived is not None and old_derived.content_rev > 0
            else None
        )
    else:
        raise DerivedStateError(f"cannot compare against {against!r}")
    if old is None or old.result_file_id is None or new.result_file_id is None:
        raise DerivedStateError(f"{derived.key}: there is no earlier data to compare with")
    files = store.result_files()
    old_result = files.read_result(uow, scope, old.result_file_id, old.result_sha256)
    new_result = files.read_result(uow, scope, new.result_file_id, new.result_sha256)
    return diff_rows(
        old_result.columns, old_result.rows, new_result.columns, new_result.rows, schema.key_column
    )


def publish_preview(
    uow: UnitOfWork, scope: str, ref: str, *, target: str | None = None
) -> PublishPlan:
    """What publishing would do now (writes nothing)."""
    return preview_publication(uow, scope, find_derived(uow.conn(), scope, ref).id, target=target)


def compensation_preview(uow: UnitOfWork, scope: str, ref: str) -> CompensationPlan:
    """What compensating the publication in force would reverse (writes nothing)."""
    return preview_compensation(uow, scope, find_derived(uow.conn(), scope, ref).id)


def validate_stored(
    uow: UnitOfWork,
    scope: str,
    ref: str,
    *,
    schema_ref: str | None = None,
    content_rev: int | None = None,
) -> ValidationReport:
    """Check the stored rows of a content revision against a schema and return the report.

    The schema is the derived document's own unless ``schema_ref`` (``code`` or ``code@semver``)
    names another. Nothing is stored and no job runs: this is the read-only check an agent may
    make before it proposes anything (``validate_against_schema``).
    """
    conn = uow.conn()
    derived = find_derived(conn, scope, ref)
    content = _content(conn, derived, content_rev)
    if content.result_file_id is None:
        raise DerivedStateError(f"{derived.key} revision {content.content_rev} stored no rows")
    if schema_ref is None:
        schema = rows.get_schema(conn, derived.schema_id)
        if schema is None:
            raise SchemaNotFoundError(f"the schema of {derived.key} is gone")
    else:
        code, _, semver = schema_ref.partition("@")
        schema = rows.resolve_schema(conn, scope, code, semver or None)
        if schema is None:
            raise SchemaNotFoundError(f"no document schema {schema_ref!r} for {scope}")
    result = store.result_files().read_result(
        uow, scope, content.result_file_id, content.result_sha256
    )
    return validate_result(
        schema.json_schema,
        result.columns,
        result.rows,
        schema_code=schema.code,
        schema_version=schema.semver,
        key_column=schema.key_column,
        problems=result.problems,
    )
