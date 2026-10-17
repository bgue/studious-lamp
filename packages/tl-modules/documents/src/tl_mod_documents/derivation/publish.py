"""Publishing a valid derived document into records, and rolling a publication back (ADR-0014).

``preview_publication`` reads the stored rows of the latest content revision, maps them through the
schema's mapping and says, row by row, what publishing would do: ``create`` a record, leave an
``exists`` or ``differs`` one alone, or refuse an ``invalid`` row. It writes nothing. The publish
commands do the same check again in their own unit of work and then write, all or nothing:

* **only module commands write.** Tags go through the engineering import (``RecordTag``), documents
  through ``RegisterDocument``; never a generic ``CreateRecord``, so number patterns, code lists,
  limits and the allow-lists hold. A publication **creates** records; a row whose key exists is
  skipped when the caller states ``skip_existing`` and otherwise stops the publication, because
  reversing an update would need old values the ledger events do not carry.
* **one correlation id.** Every event of the import (records, property sets, links) carries the
  same id, and so do the derived document's ``Published`` event and its move to Published; the id is
  what compensation reads.
* **provenance.** Each record created gets ``provenance.source = src.doc.<number>@<revision>``,
  ``provenance.derived_document = <key>`` and a ``derived_from`` link to the derived document.

``preview_compensation`` and ``CompensatePublication`` undo a publication by its correlation id
(brief 24.5): the links the import made are retracted and each created record is ended (a tag is
deleted through its workflow, a document is voided), under a correlation id of their own. A record
that can no longer be ended makes the whole compensation refuse. The original events stay.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Connection, text
from tl_core.derivation.types import MAX_ROWS, ExtractionResult
from tl_core.ledger import NewEvent
from tl_core.schema_provider import get_provider
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import ServiceError
from tl_core.services.links import AddLink, RetractLink, handle_add_link, handle_retract_link
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.reserved import DERIVE_CORRELATION_PREFIX
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid
from tl_mod_engineering import registry as eng_registry
from tl_mod_engineering.imports.apply import apply_plan as apply_tag_plan
from tl_mod_engineering.imports.apply import ended_numbers, existing_tags
from tl_mod_engineering.imports.diff import plan_import as plan_tag_import
from tl_mod_engineering.imports.model import ImportPlan as TagPlan
from tl_mod_engineering.imports.model import ImportRow as TagRow

from tl_mod_documents import registry
from tl_mod_documents.derivation import rows
from tl_mod_documents.derivation.derived import load_derived
from tl_mod_documents.derivation.mapping import MappingInvalidError, PublishMapping, check_mapping
from tl_mod_documents.derivation.store import result_files
from tl_mod_documents.derivation.validation import typed_row
from tl_mod_documents.errors import CompensationRefusedError, PublishRefusedError
from tl_mod_documents.handlers.common import append, correlated, transition
from tl_mod_documents.handlers.documents import (
    RegisterDocument,
    VoidDocument,
    handle_register_document,
    handle_void_document,
)
from tl_mod_documents.imports.diff import plan_import as plan_document_import
from tl_mod_documents.imports.model import ImportRow as DocumentRow
from tl_mod_documents.limits import MAX_REASON
from tl_mod_documents.names import (
    DD_PUBLISHED,
    DD_VALID,
    DERIVED_COMPENSATED,
    DERIVED_DOCUMENT,
    DERIVED_FROM_RELATION,
    DERIVED_PUBLISHED,
    PROVENANCE_PROPERTY,
    PROVENANCE_PSET,
    TARGET_DOCUMENTS,
    TARGET_TAGS,
)

#: A preview lists at most this many rows; the counts are always exact.
MAX_PREVIEW_ROWS = 2000
Action = Literal["create", "exists", "differs", "invalid"]


class PlanRow(BaseModel):
    """What publishing would do with one data row (1-based, header excluded)."""

    row: int
    key: str | None
    action: Action
    problems: list[str] = []
    #: The mapped fields, as they would be written (``class``, ``service``, ``psets``...).
    values: dict[str, Any] = {}


class PublishPlan(BaseModel):
    derived_id: str
    derived_key: str
    content_rev: int
    target: str | None
    schema_key: str | None
    source_ref: str
    mapping_hash: str | None
    result_sha256: str | None
    counts: dict[str, int]
    rows: list[PlanRow]
    #: Reasons that stop the whole publication, apart from single rows.
    problems: list[str]
    can_publish: bool
    #: True when the only thing in the way is rows that exist: ``skip_existing`` lets it through.
    needs_skip_existing: bool
    truncated: bool


class _PublishBase(Command):
    model_config = ConfigDict(extra="forbid")

    derived_id: str
    #: The content revision the person looked at; a newer pass makes the publication refuse.
    expected_content_rev: int = Field(ge=1)
    #: Leave rows whose key already exists alone instead of stopping.
    skip_existing: bool = False


class PublishDerivedTags(_PublishBase):
    """Create the tags of a valid derived document, as one correlated import (admin)."""


class PublishDerivedDocuments(_PublishBase):
    """Register the documents of a valid derived document, as one correlated import (controller)."""


class CompensatePublication(Command):
    """Roll back the publication in force: end every record it created (admin)."""

    model_config = ConfigDict(extra="forbid")

    derived_id: str
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


# --- mapping a row ---------------------------------------------------------------------------


def map_row(
    mapping: PublishMapping, json_schema: dict[str, Any], row: dict[str, str | None]
) -> tuple[dict[str, str], dict[str, dict[str, Any]], list[str]]:
    """``(fields, psets, problems)`` of one row: typed by the schema, then placed by the mapping."""
    typed = typed_row(json_schema, row)
    fields: dict[str, str] = {}
    psets: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for entry in mapping.columns:
        value = typed.get(entry.column)
        if value is None:
            continue
        if entry.values is not None and isinstance(value, str):
            if value not in entry.values:
                problems.append(f"{entry.column}: {value!r} has no translation in the mapping")
                continue
            value = entry.values[value]
        if entry.to.startswith("psets."):
            _, pset, prop = entry.to.split(".", 2)
            psets.setdefault(pset, {})[prop] = value
        else:
            fields[entry.to] = str(value)
    return fields, psets, problems


# --- the plan --------------------------------------------------------------------------------


@dataclass
class _Creatable:
    key: str
    fields: dict[str, str]
    psets: dict[str, dict[str, Any]]
    tag_row: TagRow | None = None
    document_row: DocumentRow | None = None


@dataclass
class _Built:
    plan: PublishPlan
    derived: rows.DerivedRow
    creatable: list[_Creatable]


def _provenance_problem(scope: str, record_type: str) -> str | None:
    pset = get_provider().effective(scope).find_pset(PROVENANCE_PSET)
    if pset is None or record_type not in pset.applies_to:
        return (
            f"the effective schema has no {PROVENANCE_PSET!r} property set for {record_type}: "
            "add it to the company package (see docs/modules/documents/derivation.md)"
        )
    return None


def _build(
    uow: UnitOfWork, scope: str, derived_id: str, *, target: str | None, expected_rev: int | None
) -> _Built:
    conn = uow.conn()
    derived = rows.get_derived(conn, derived_id)
    if derived is None or derived.scope != scope:
        load_derived(uow, Command(actor="x", source="x", scope=scope), derived_id)  # raises
        raise AssertionError("unreachable")
    problems: list[str] = []
    content = (
        rows.get_content(conn, derived.id, derived.content_rev) if derived.content_rev else None
    )
    schema = rows.get_schema(conn, content.schema_id) if content and content.schema_id else None
    mapping: PublishMapping | None = None
    if derived.voided or derived.state != DD_VALID:
        problems.append(
            f"{derived.key} is {derived.state}"
            + (
                f"; the publication is in force (correlation {derived.published_correlation_id})"
                if derived.state == DD_PUBLISHED
                else "; only a Valid derived document is published"
            )
        )
    if expected_rev is not None and derived.content_rev != expected_rev:
        problems.append(
            f"the latest content revision is {derived.content_rev}, not {expected_rev}: "
            "look at the new one first"
        )
    if content is None or content.validation_status != "valid":
        problems.append("the latest content revision has not passed its schema")
    if schema is None:
        problems.append("the document schema of the latest content revision is missing")
    else:
        if target is not None and schema.target_kind != target:
            problems.append(
                f"{schema.key} publishes {schema.target_kind or 'nothing'}, not {target}"
            )
        try:
            mapping = check_mapping(schema.mapping, schema.json_schema, schema.target_kind)
        except MappingInvalidError as exc:
            problems.extend(f"mapping: {p}" for p in exc.problems)
    result: ExtractionResult | None = None
    if content is not None and content.result_file_id is not None and not problems:
        result = result_files().read_result(
            uow, scope, content.result_file_id, content.result_sha256
        )
    plan_rows: list[PlanRow] = []
    creatable: list[_Creatable] = []
    counts = {"create": 0, "exists": 0, "differs": 0, "invalid": 0}
    if result is not None and schema is not None and mapping is not None:
        kind = mapping.target
        record_type = "engineering.Tag" if kind == TARGET_TAGS else "documents.Document"
        found = _provenance_problem(scope, record_type)
        if found:
            problems.append(found)
        plan_rows, creatable, counts = _plan_rows(
            conn, scope, derived, schema, mapping, result, kind
        )
    can = not problems and counts["invalid"] == 0 and counts["create"] > 0
    needs_skip = can and (counts["exists"] + counts["differs"]) > 0
    if counts["create"] == 0 and not problems and counts["invalid"] == 0:
        problems.append("there is nothing to create: every row exists already")
        can = False
    return _Built(
        plan=PublishPlan(
            derived_id=derived.id,
            derived_key=derived.key,
            content_rev=derived.content_rev,
            target=None if mapping is None else mapping.target,
            schema_key=None if schema is None else schema.key,
            source_ref=derived.source_ref,
            mapping_hash=None if schema is None else schema.content_hash,
            result_sha256=None if content is None else content.result_sha256,
            counts=counts,
            rows=plan_rows[:MAX_PREVIEW_ROWS],
            problems=problems,
            can_publish=can,
            needs_skip_existing=needs_skip,
            truncated=len(plan_rows) > MAX_PREVIEW_ROWS,
        ),
        derived=derived,
        creatable=creatable,
    )


def _plan_rows(
    conn: Connection,
    scope: str,
    derived: rows.DerivedRow,
    schema: rows.SchemaRow,
    mapping: PublishMapping,
    result: ExtractionResult,
    kind: str,
) -> tuple[list[PlanRow], list[_Creatable], dict[str, int]]:
    mapped: list[tuple[dict[str, str], dict[str, dict[str, Any]], list[str]]] = [
        map_row(mapping, schema.json_schema, row) for row in result.rows
    ]
    counts = {"create": 0, "exists": 0, "differs": 0, "invalid": 0}
    plan_rows: list[PlanRow] = []
    creatable: list[_Creatable] = []
    if kind == TARGET_TAGS:
        tag_rows = [
            TagRow(
                line=index + 1,
                number=fields.get("number", "").strip(),
                class_code=fields.get("class"),
                service=fields.get("service"),
                psets=psets,
                problems=[*problems, *([] if fields.get("number") else ["no tag number"])],
            )
            for index, (fields, psets, problems) in enumerate(mapped, start=1)
        ]
        tag_plan = plan_tag_import(
            tag_rows, existing_tags(conn, scope), ended=ended_numbers(conn, scope)
        )
        new_lines = {r.line for r in tag_plan.new}
        changed = {c.line for c in tag_plan.changed}
        invalid = {r.line: r.problems for r in tag_plan.invalid}
        for row in tag_rows:
            action: Action
            if row.line in invalid:
                action = "invalid"
            elif row.line in new_lines:
                action = "create"
            elif row.line in changed:
                action = "differs"
            else:
                action = "exists"
            counts[action] += 1
            plan_rows.append(
                _plan_row(
                    row.line - 1,
                    row.number,
                    action,
                    invalid.get(row.line, []),
                    mapped[row.line - 2],
                )
            )
            if action == "create":
                creatable.append(
                    _Creatable(
                        row.number, mapped[row.line - 2][0], mapped[row.line - 2][1], tag_row=row
                    )
                )
        return plan_rows, creatable, counts
    doc_rows = [
        DocumentRow(
            line=index + 1,
            number=fields.get("number", "").strip(),
            title=fields.get("title"),
            doc_type=fields.get("doc_type"),
            discipline=fields.get("discipline"),
            originator=fields.get("originator"),
            legacy_revision=None,
            legacy_status=None,
            legacy_date=None,
            problems=[*problems, *([] if fields.get("number") else ["no document number"])],
        )
        for index, (fields, _psets, problems) in enumerate(mapped, start=1)
    ]
    doc_plan = plan_document_import(conn, scope, doc_rows)
    new_lines = {r.line for r in doc_plan.new}
    invalid = {r.line: r.problems for r in doc_plan.invalid}
    for row in doc_rows:
        action = (
            "invalid" if row.line in invalid else "create" if row.line in new_lines else "exists"
        )
        counts[action] += 1
        plan_rows.append(
            _plan_row(
                row.line - 1, row.number, action, invalid.get(row.line, []), mapped[row.line - 2]
            )
        )
        if action == "create":
            creatable.append(_Creatable(row.number, mapped[row.line - 2][0], {}, document_row=row))
    return plan_rows, creatable, counts


def _plan_row(
    index: int,
    key: str,
    action: Action,
    problems: list[str],
    mapped: tuple[dict[str, str], dict[str, dict[str, Any]], list[str]],
) -> PlanRow:
    fields, psets, _ = mapped
    values: dict[str, Any] = {k: v for k, v in fields.items() if k != "number"}
    if psets:
        values["psets"] = psets
    return PlanRow(row=index, key=key or None, action=action, problems=problems, values=values)


def preview_publication(
    uow: UnitOfWork, scope: str, derived_id: str, *, target: str | None = None
) -> PublishPlan:
    """What publishing the derived document would do now. Reads and writes nothing."""
    return _build(uow, scope, derived_id, target=target, expected_rev=None).plan


# --- publishing ------------------------------------------------------------------------------


def _check_recorded_bounds(record_ids: list[str], link_ids: list[str]) -> None:
    """A publication makes one record and one link per row, so neither list can pass ``MAX_ROWS``.

    The lists go into the ``Published`` event, which compensation trusts; this keeps the event
    bounded whatever the plan says. Raising rolls the whole publication back (security re-review).
    """
    if len(record_ids) > MAX_ROWS or len(link_ids) > MAX_ROWS or len(link_ids) != len(record_ids):
        raise PublishRefusedError(
            f"the publication would record {len(record_ids)} records and {len(link_ids)} links; "
            f"at most {MAX_ROWS} rows can be published",
            [],
        )


def _publish(uow: UnitOfWork, cmd: _PublishBase, target: str) -> CommandResult:
    cmd = correlated(cmd)
    built = _build(
        uow, cmd.scope, cmd.derived_id, target=target, expected_rev=cmd.expected_content_rev
    )
    plan, derived = built.plan, built.derived
    problems = list(plan.problems)
    for row in plan.rows:
        if row.action == "invalid":
            problems.append(f"row {row.row} ({row.key or 'no key'}): {'; '.join(row.problems)}")
    if plan.counts["invalid"] > len([r for r in plan.rows if r.action == "invalid"]):
        problems.append(f"{plan.counts['invalid']} rows are invalid in all")
    if not problems and plan.needs_skip_existing and not cmd.skip_existing:
        problems.append(
            f"{plan.counts['exists'] + plan.counts['differs']} row(s) exist already and are not "
            "created; say skip_existing to publish the rest"
        )
    if problems:
        raise PublishRefusedError(
            f"{derived.key} cannot be published: " + "; ".join(problems[:10]), problems
        )
    correlation = f"{DERIVE_CORRELATION_PREFIX}{new_ulid()}"  # server-made, reserved prefix
    source = f"import:derived-{derived.id}"
    base: dict[str, Any] = {
        "actor": cmd.actor,
        "source": source,
        "scope": cmd.scope,
        "correlation_id": correlation,
        "causation_id": cmd.causation_id,  # the proposal, when an agent proposed this
    }
    provenance = {PROVENANCE_PROPERTY: derived.source_ref, "derived_document": derived.key}
    record_ids = (
        _create_tags(uow, base, built, provenance)
        if target == TARGET_TAGS
        else _create_documents(uow, base, built, provenance)
    )
    link_ids: list[str] = []
    for record_id in record_ids:
        linked = handle_add_link(
            uow,
            AddLink(
                **base,
                from_id=record_id,
                to_id=derived.id,
                relation=DERIVED_FROM_RELATION,
                link_source="import",
                note=f"published from {derived.source_ref}",
            ),
            by_module=True,
        )
        link_ids.append(linked.stream_id)
    _check_recorded_bounds(record_ids, link_ids)
    content = rows.get_content(uow.conn(), derived.id, derived.content_rev)
    assert content is not None and content.result_sha256 is not None
    actor_cmd = Command(**base)
    made = append(
        uow,
        actor_cmd,
        derived.id,
        DERIVED_DOCUMENT,
        [
            NewEvent(
                event_type=DERIVED_PUBLISHED,
                payload={
                    "content_rev": derived.content_rev,
                    "import_correlation_id": correlation,
                    "target_kind": target,
                    "created_count": len(record_ids),
                    "record_ids": record_ids,
                    "link_ids": link_ids,
                    "mapping_hash": plan.mapping_hash,
                    "result_sha256": content.result_sha256,
                },
            )
        ],
    )
    moved = transition(uow, actor_cmd, derived.id, "publish")
    return CommandResult(
        stream_id=derived.id,
        key=derived.key,
        version=moved.version,
        events=[*made.events, *moved.events],
    )


def _create_tags(
    uow: UnitOfWork, base: dict[str, Any], built: _Built, provenance: dict[str, str]
) -> list[str]:
    plan = TagPlan()
    for item in built.creatable:
        assert item.tag_row is not None
        row = item.tag_row
        plan.new.append(
            TagRow(
                line=row.line,
                number=row.number,
                class_code=row.class_code,
                service=row.service,
                psets={**row.psets, PROVENANCE_PSET: dict(provenance)},
            )
        )
    try:
        apply_tag_plan(
            uow,
            base["scope"],
            plan,
            actor=base["actor"],
            source=base["source"],
            reason=f"published from {built.derived.source_ref}",
            correlation_id=base["correlation_id"],
        )
    except ServiceError as exc:
        raise PublishRefusedError(f"{built.derived.key} cannot be published: {exc}") from exc
    ids: list[str] = []
    for item in built.creatable:
        tag = eng_registry.find_tag(uow.conn(), base["scope"], item.key)
        assert tag is not None
        ids.append(tag.id)
    return ids


def _create_documents(
    uow: UnitOfWork, base: dict[str, Any], built: _Built, provenance: dict[str, str]
) -> list[str]:
    ids: list[str] = []
    for item in built.creatable:
        row = item.document_row
        assert row is not None
        try:
            made = handle_register_document(
                uow,
                RegisterDocument(
                    **base,
                    number=row.number,
                    title=row.title or row.number,
                    description=item.fields.get("description"),
                    doc_type=row.doc_type,
                    discipline=row.discipline,
                    originator=row.originator,
                ),
            )
            handle_set_pset_values(
                uow,
                SetPsetValues(
                    **base,
                    stream_id=made.stream_id,
                    expected_version=made.version,
                    pset=PROVENANCE_PSET,
                    layer="standard",
                    values=dict(provenance),
                ),
            )
        except ServiceError as exc:
            raise PublishRefusedError(
                f"{built.derived.key} cannot be published: document {row.number}: {exc}"
            ) from exc
        ids.append(made.stream_id)
    return ids


def handle_publish_derived_tags(uow: UnitOfWork, cmd: PublishDerivedTags) -> CommandResult:
    """Create the tags (admin). Raises ``PublishRefusedError`` listing every reason."""
    return _publish(uow, cmd, TARGET_TAGS)


def handle_publish_derived_documents(
    uow: UnitOfWork, cmd: PublishDerivedDocuments
) -> CommandResult:
    """Register the documents (controller). Raises ``PublishRefusedError`` listing every reason."""
    return _publish(uow, cmd, TARGET_DOCUMENTS)


# --- compensation ----------------------------------------------------------------------------


class CompensationItem(BaseModel):
    record_id: str
    key: str | None
    record_type: str
    state: str | None
    action: Literal["delete_tag", "void_document", "retract_link"]
    reversible: bool
    problem: str | None = None


class CompensationPlan(BaseModel):
    derived_id: str
    derived_key: str
    import_correlation_id: str | None
    items: list[CompensationItem]
    problems: list[str]
    can_compensate: bool


_RECORD_SQL = text("SELECT key, status, voided, type, scope FROM cur_core_record WHERE id = :id")
_PUBLISHED_SQL = text(
    "SELECT payload FROM events WHERE stream_id = :d AND event_type = :t ORDER BY seq DESC"
)


def _recorded(conn: Connection, derived_id: str, correlation: str) -> tuple[list[str], list[str]]:
    """The ids of the records and links the publication in force made, as it wrote them down.

    This is the one source compensation trusts: the ``DerivedDocument.Published`` event the module
    appended, not "the events that carry this correlation id" (a client can set a correlation id).
    """
    for row in conn.execute(_PUBLISHED_SQL, {"d": derived_id, "t": DERIVED_PUBLISHED}).all():
        payload = row.payload
        body: dict[str, Any] = json.loads(payload) if isinstance(payload, str) else dict(payload)
        if body.get("import_correlation_id") == correlation:
            records = [str(i) for i in body.get("record_ids", [])]
            links = [str(i) for i in body.get("link_ids", [])]
            return records, links
    return [], []


def preview_compensation(uow: UnitOfWork, scope: str, derived_id: str) -> CompensationPlan:
    """What rolling the publication back would end, and what stands in the way. Reads only."""
    conn = uow.conn()
    derived = rows.get_derived(conn, derived_id)
    if derived is None or derived.scope != scope:
        load_derived(uow, Command(actor="x", source="x", scope=scope), derived_id)  # raises
        raise AssertionError("unreachable")
    problems: list[str] = []
    items: list[CompensationItem] = []
    correlation = derived.published_correlation_id
    if derived.state != DD_PUBLISHED or correlation is None:
        problems.append(f"{derived.key} is {derived.state}: there is no publication to roll back")
        return CompensationPlan(
            derived_id=derived.id,
            derived_key=derived.key,
            import_correlation_id=correlation,
            items=[],
            problems=problems,
            can_compensate=False,
        )
    record_ids, link_ids = _recorded(conn, derived.id, correlation)
    for link_id in link_ids:
        items.append(
            CompensationItem(
                record_id=link_id,
                key=None,
                record_type="link",
                state=None,
                action="retract_link",
                reversible=True,
            )
        )
    for record_id in record_ids:
        items.append(_record_item(conn, record_id, derived.scope))
    for item in items:
        if not item.reversible:
            problems.append(f"{item.key or item.record_id}: {item.problem}")
    return CompensationPlan(
        derived_id=derived.id,
        derived_key=derived.key,
        import_correlation_id=correlation,
        items=items,
        problems=problems,
        can_compensate=not problems and bool(items),
    )


def _record_item(conn: Connection, record_id: str, scope: str) -> CompensationItem:
    row = conn.execute(_RECORD_SQL, {"id": record_id}).first()
    if row is None or row.scope != scope:
        return CompensationItem(
            record_id=record_id,
            key=None,
            record_type="unknown",
            state=None,
            action="void_document",
            reversible=False,
            problem="a record the publication made is not there",
        )
    record_type = str(row.type)
    key = row.key
    if record_type == "engineering.Tag":
        state = None if row is None else (row.status or "Planned")
        ok = state in ("Planned", "Design", "Installed", "Commissioned", "Deleted")
        return CompensationItem(
            record_id=record_id,
            key=key,
            record_type=record_type,
            state=state,
            action="delete_tag",
            reversible=ok,
            problem=None if ok else f"the tag is {state} and cannot be deleted",
        )
    if record_type == "documents.Document":
        state = None if row is None else ("Void" if bool(row.voided) else (row.status or "Draft"))
        revisions = [r for r in registry.revisions_of(conn, record_id) if not r.voided]
        ok = state in ("Draft", "Registered", "Void") and not revisions
        problem = None
        if not ok:
            problem = (
                f"the document has {len(revisions)} revision(s); void them first"
                if revisions
                else f"the document is {state} and cannot be voided here"
            )
        return CompensationItem(
            record_id=record_id,
            key=key,
            record_type=record_type,
            state=state,
            action="void_document",
            reversible=ok,
            problem=problem,
        )
    return CompensationItem(
        record_id=record_id,
        key=key,
        record_type=record_type,
        state=None,
        action="void_document",
        reversible=False,
        problem=f"a {record_type} cannot be rolled back by this command",
    )


def handle_compensate_publication(uow: UnitOfWork, cmd: CompensatePublication) -> CommandResult:
    """Append the reversing events of the publication in force (admin), all or nothing.

    Raises ``CompensationRefusedError`` listing every reason, before anything is written.
    """
    cmd = correlated(cmd)
    plan = preview_compensation(uow, cmd.scope, cmd.derived_id)
    if not plan.can_compensate:
        raise CompensationRefusedError(
            f"{plan.derived_key} cannot be rolled back: " + "; ".join(plan.problems[:10]),
            plan.problems or ["there is nothing to roll back"],
        )
    derived = load_derived(uow, cmd, cmd.derived_id)
    correlation = f"{DERIVE_CORRELATION_PREFIX}{new_ulid()}"
    base: dict[str, Any] = {
        "actor": cmd.actor,
        "source": f"compensation:{derived.id}",
        "scope": cmd.scope,
        "correlation_id": correlation,
        "causation_id": cmd.causation_id,
    }
    why = f"compensation of {plan.import_correlation_id}: {cmd.reason}"
    reversed_count = 0
    for item in plan.items:
        if item.action == "retract_link":
            handle_retract_link(
                uow, RetractLink(**base, link_id=item.record_id, reason=why), by_module=True
            )
    for item in plan.items:
        if item.action == "retract_link" or item.state in ("Deleted", "Void"):
            continue
        version = int(
            uow.conn()
            .execute(
                text("SELECT version FROM cur_core_record WHERE id = :i"), {"i": item.record_id}
            )
            .scalar_one()
        )
        if item.action == "delete_tag":
            handle_transition_workflow(
                uow,
                TransitionWorkflow(
                    **base,
                    stream_id=item.record_id,
                    expected_version=version,
                    transition="delete",
                    reason=why[:MAX_REASON],
                ),
                by_module=True,
            )
        else:
            handle_void_document(
                uow,
                VoidDocument(
                    **base,
                    stream_id=item.record_id,
                    expected_version=version,
                    reason=why[:MAX_REASON],
                ),
            )
        reversed_count += 1
    actor_cmd = Command(**base)
    made = append(
        uow,
        actor_cmd,
        derived.id,
        DERIVED_DOCUMENT,
        [
            NewEvent(
                event_type=DERIVED_COMPENSATED,
                payload={
                    "content_rev": derived.published_rev or derived.content_rev,
                    "import_correlation_id": plan.import_correlation_id,
                    "compensation_correlation_id": correlation,
                    "reversed_count": reversed_count,
                    "reason": cmd.reason,
                },
            )
        ],
    )
    moved = transition(uow, actor_cmd, derived.id, "compensate", reason=cmd.reason[:MAX_REASON])
    return CommandResult(
        stream_id=derived.id,
        key=derived.key,
        version=moved.version,
        events=[*made.events, *moved.events],
    )
