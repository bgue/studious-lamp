"""Where the rows of a legacy file go: tags (engineering) or documents (documents).

A target reads the grid with the mapping template of the existing import of its module, plans
against the project (what is new, what exists, what cannot be loaded), writes the new rows with the
module's own commands, compares the project with the file, and takes the written records back.

The load is **create-only**: a row whose key the project holds is left alone and counted, never
changed. Every command carries the source ``legacy:<system>`` and the load's correlation id, and
the caller records the ids that were created: compensation reverses those ids and nothing else
(the same rule as the derivation pipeline's, ADR-0014). No text of a cell is put in a problem:
a problem is a line number and fixed words or a field name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import yaml
from sqlalchemy import Connection, bindparam, text
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork
from tl_mod_documents import registry as documents_registry
from tl_mod_documents.handlers.documents import (
    RegisterDocument,
    VoidDocument,
    handle_register_document,
    handle_void_document,
)
from tl_mod_documents.imports import diff as documents_diff
from tl_mod_documents.imports import mapping as documents_mapping
from tl_mod_engineering.imports import apply as engineering_apply
from tl_mod_engineering.imports import diff as engineering_diff
from tl_mod_engineering.imports import mapping as engineering_mapping
from tl_mod_engineering.imports.model import ImportPlan as TagPlan

from tl_mod_legacy.errors import MappingProblemError
from tl_mod_legacy.limits import MAX_REASON
from tl_mod_legacy.model import Grid, LoaderDef, TargetKind

KEY_BATCH = 400
TAG_TYPE = "engineering.Tag"
DOCUMENT_TYPE = "documents.Document"
#: States of a tag that ``delete`` can end (the same list as the derivation pipeline's rollback).
DELETABLE_TAG_STATES = frozenset({"Planned", "Design", "Installed", "Commissioned", "Deleted"})
DOCUMENT_STATES = frozenset({"Draft", "Registered", "Void"})


@dataclass(frozen=True)
class PlannedRow:
    """A row that would be created: the file line, the key and every cell by header."""

    line: int
    key: str
    raw: dict[str, str]
    native: Any = field(default=None, repr=False)  # the module's own row, for ``apply``


@dataclass(frozen=True)
class Plan:
    """What loading would do. ``rows`` are the new ones in file order; ``invalid`` is ``(line,
    problem)`` pairs; ``existing`` the keys the project holds."""

    rows: list[PlannedRow]
    existing: list[str]
    invalid: list[tuple[int, str]]

    def counts(self) -> dict[str, int]:
        return {
            "new": len(self.rows),
            "existing": len(self.existing),
            "invalid": len(self.invalid),
        }


@dataclass(frozen=True)
class Created:
    record_id: str
    key: str
    line: int
    raw: dict[str, str]


@dataclass(frozen=True)
class Reversal:
    """One record a compensation would end, and whether it can be."""

    record_id: str
    key: str | None
    state: str | None
    reversible: bool
    problem: str | None


@dataclass(frozen=True)
class Comparison:
    """The project against the file, row by row (fixed text and field names; no cell)."""

    valid: int
    matched: int
    missing: list[int]  # lines whose record is not in the project (or ended)
    differs: list[tuple[int, str]]  # (line, field) of rows this run created that differ
    left_alone_differs: int  # rows that were already there, left alone, and differ from the file
    invalid: int


class Target(Protocol):
    kind: TargetKind

    def plan(self, conn: Connection, scope: str, loader: LoaderDef, grid: Grid) -> Plan: ...

    def apply(
        self,
        uow: UnitOfWork,
        scope: str,
        loader: LoaderDef,
        plan: Plan,
        *,
        actor: str,
        source: str,
        correlation_id: str,
        confidentiality: str | None,
    ) -> list[Created]: ...

    def compare(
        self, conn: Connection, scope: str, loader: LoaderDef, grid: Grid, created_keys: set[str]
    ) -> Comparison: ...

    def reversals(
        self, conn: Connection, scope: str, record_ids: list[str], correlation_id: str
    ) -> list[Reversal]: ...

    def reverse(
        self,
        uow: UnitOfWork,
        scope: str,
        record_ids: list[str],
        *,
        actor: str,
        source: str,
        correlation_id: str,
        reason: str,
    ) -> int: ...


def comma_mapping_text(loader: LoaderDef) -> str:
    """The loader's template with its delimiter set to a comma: the grid is handed over as CSV."""
    data = yaml.safe_load(loader.mapping_text)
    if not isinstance(data, dict):
        raise MappingProblemError(f"loader {loader.name}: the mapping must be a YAML mapping")
    data["delimiter"] = ","
    return yaml.safe_dump(data, sort_keys=False)


def _problem_text(problems: list[str]) -> str:
    return "; ".join(problems)[:300]


def _record(conn: Connection, record_id: str) -> Any:
    return conn.execute(
        text(
            "SELECT key, status, voided, type, scope, version FROM cur_core_record WHERE id = :id"
        ),
        {"id": record_id},
    ).first()


def _foreign_events(conn: Connection, record_id: str, correlation_id: str) -> int:
    """Events of a record that the load did not write."""
    return int(
        conn.execute(
            text("SELECT count(*) FROM events WHERE stream_id = :id AND correlation_id <> :c"),
            {"id": record_id, "c": correlation_id},
        ).scalar_one()
    )


def _ids_by_key(conn: Connection, scope: str, record_type: str, keys: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    statement = text(
        "SELECT key, id FROM cur_core_record WHERE scope = :s AND type = :t AND key IN :keys"
    ).bindparams(bindparam("keys", expanding=True))
    for start in range(0, len(keys), KEY_BATCH):
        for row in conn.execute(
            statement, {"s": scope, "t": record_type, "keys": keys[start : start + KEY_BATCH]}
        ):
            found[str(row.key)] = str(row.id)
    return found


def _version(conn: Connection, record_id: str) -> int:
    return int(
        conn.execute(
            text("SELECT version FROM cur_core_record WHERE id = :i"), {"i": record_id}
        ).scalar_one()
    )


def _reversal_item(
    conn: Connection,
    scope: str,
    record_id: str,
    correlation_id: str,
    record_type: str,
    initial_state: str,
) -> Reversal:
    row = _record(conn, record_id)
    if row is None or row.scope != scope or row.type != record_type:
        return Reversal(record_id, None, None, False, "a record the load made is not there")
    state = "Void" if bool(row.voided) else (row.status or initial_state)
    if _foreign_events(conn, record_id, correlation_id):
        return Reversal(record_id, row.key, state, False, "it was changed after the load")
    return Reversal(record_id, row.key, state, True, None)


class TagTarget:
    kind: TargetKind = "tags"

    def _rows(self, loader: LoaderDef, grid: Grid) -> list[Any]:
        try:
            mapping = engineering_mapping.parse_mapping(
                comma_mapping_text(loader), source=loader.name
            )
            return engineering_mapping.read_rows(grid.to_csv(), mapping)
        except engineering_mapping.MappingError as exc:
            raise MappingProblemError(str(exc).splitlines()[0][:300]) from exc

    def plan(self, conn: Connection, scope: str, loader: LoaderDef, grid: Grid) -> Plan:
        rows = self._rows(loader, grid)
        planned: TagPlan = engineering_diff.plan_import(
            rows,
            engineering_apply.existing_tags(conn, scope),
            ended=engineering_apply.ended_numbers(conn, scope),
        )
        return Plan(
            rows=[PlannedRow(r.line, r.number, dict(r.raw), r) for r in planned.new],
            existing=[*planned.unchanged, *(c.number for c in planned.changed)],
            invalid=[(r.line, _problem_text(r.problems)) for r in planned.invalid],
        )

    def apply(
        self,
        uow: UnitOfWork,
        scope: str,
        loader: LoaderDef,
        plan: Plan,
        *,
        actor: str,
        source: str,
        correlation_id: str,
        confidentiality: str | None,
    ) -> list[Created]:
        if not plan.rows:
            return []
        engineering_apply.apply_plan(
            uow,
            scope,
            TagPlan(new=[r.native for r in plan.rows]),
            actor=actor,
            source=source,
            reason=f"legacy load {correlation_id}"[:MAX_REASON],
            correlation_id=correlation_id,
        )
        ids = _ids_by_key(uow.conn(), scope, TAG_TYPE, [r.key for r in plan.rows])
        if len(ids) != len(plan.rows):
            raise MappingProblemError("the tags written are not the tags planned")
        return [Created(ids[r.key], r.key, r.line, r.raw) for r in plan.rows]

    def compare(
        self, conn: Connection, scope: str, loader: LoaderDef, grid: Grid, created_keys: set[str]
    ) -> Comparison:
        rows = self._rows(loader, grid)
        bad = {line for line, _ in self.plan(conn, scope, loader, grid).invalid}
        held = {t.number: t for t in engineering_apply.existing_tags(conn, scope)}
        valid = matched = left = invalid = 0
        missing: list[int] = []
        differs: list[tuple[int, str]] = []
        seen: set[str] = set()
        for row in rows:
            if row.line in bad or row.problems or not row.number or row.number in seen:
                invalid += 1  # a number that appears again is judged on its first row only
                continue
            seen.add(row.number)
            valid += 1
            tag = held.get(row.number)
            if tag is None:
                missing.append(row.line)
                continue
            changes = engineering_diff.row_changes(row, tag)
            if not changes:
                matched += 1
            elif row.number in created_keys:
                differs.extend((row.line, change.field) for change in changes)
            else:
                left += 1
        return Comparison(valid, matched, missing, differs, left, invalid)

    def reversals(
        self, conn: Connection, scope: str, record_ids: list[str], correlation_id: str
    ) -> list[Reversal]:
        found: list[Reversal] = []
        for record_id in record_ids:
            item = _reversal_item(conn, scope, record_id, correlation_id, TAG_TYPE, "Planned")
            if item.reversible and item.state not in DELETABLE_TAG_STATES:
                item = Reversal(
                    record_id,
                    item.key,
                    item.state,
                    False,
                    f"the tag is {item.state}: not deletable",
                )
            found.append(item)
        return found

    def reverse(
        self,
        uow: UnitOfWork,
        scope: str,
        record_ids: list[str],
        *,
        actor: str,
        source: str,
        correlation_id: str,
        reason: str,
    ) -> int:
        count = 0
        for record_id in record_ids:
            row = _record(uow.conn(), record_id)
            if row is not None and row.status == "Deleted":
                continue
            handle_transition_workflow(
                uow,
                TransitionWorkflow(
                    actor=actor,
                    source=source,
                    scope=scope,
                    correlation_id=correlation_id,
                    stream_id=record_id,
                    expected_version=_version(uow.conn(), record_id),
                    transition="delete",
                    reason=reason[:MAX_REASON],
                ),
                by_module=True,
            )
            count += 1
        return count


class DocumentTarget:
    kind: TargetKind = "documents"

    def _rows(self, loader: LoaderDef, grid: Grid) -> list[Any]:
        try:
            mapping = documents_mapping.parse_mapping(
                comma_mapping_text(loader), source=loader.name
            )
            return documents_mapping.read_rows(grid.to_csv(), mapping)
        except documents_mapping.MappingError as exc:
            raise MappingProblemError(str(exc).splitlines()[0][:300]) from exc

    def plan(self, conn: Connection, scope: str, loader: LoaderDef, grid: Grid) -> Plan:
        planned = documents_diff.plan_import(conn, scope, self._rows(loader, grid))
        return Plan(
            rows=[PlannedRow(r.line, r.number, dict(r.raw), r) for r in planned.new],
            existing=list(planned.exists),
            invalid=[(r.line, _problem_text(r.problems)) for r in planned.invalid],
        )

    def apply(
        self,
        uow: UnitOfWork,
        scope: str,
        loader: LoaderDef,
        plan: Plan,
        *,
        actor: str,
        source: str,
        correlation_id: str,
        confidentiality: str | None,
    ) -> list[Created]:
        created: list[Created] = []
        for planned in plan.rows:
            row = planned.native
            made = handle_register_document(
                uow,
                RegisterDocument(
                    actor=actor,
                    source=source,
                    scope=scope,
                    correlation_id=correlation_id,
                    number=row.number,
                    title=row.title or row.number,
                    description=row.note,
                    doc_type=row.doc_type,
                    discipline=row.discipline,
                    originator=row.originator,
                    confidentiality=confidentiality,  # type: ignore[arg-type]
                ),
            )
            created.append(Created(made.stream_id, row.number, row.line, planned.raw))
        return created

    def compare(
        self, conn: Connection, scope: str, loader: LoaderDef, grid: Grid, created_keys: set[str]
    ) -> Comparison:
        valid = matched = left = invalid = 0
        missing: list[int] = []
        differs: list[tuple[int, str]] = []
        seen: set[str] = set()
        bad = {line for line, _ in self.plan(conn, scope, loader, grid).invalid}
        for row in self._rows(loader, grid):
            if row.line in bad or row.problems or not row.number or row.title is None:
                invalid += 1
                continue
            seen.add(row.number)
            valid += 1
            found = documents_registry.find_document(conn, scope, row.number)
            if found is None or found.closed:
                missing.append(row.line)
                continue
            fields = [
                name
                for name, mine, theirs in (
                    ("title", row.title, found.title),
                    ("doc_type", row.doc_type, found.doc_type),
                    ("discipline", row.discipline, found.discipline),
                    ("originator", row.originator, found.originator),
                )
                if mine is not None and mine != theirs
            ]
            if not fields:
                matched += 1
            elif row.number in created_keys:
                differs.extend((row.line, name) for name in fields)
            else:
                left += 1
        return Comparison(valid, matched, missing, differs, left, invalid)

    def reversals(
        self, conn: Connection, scope: str, record_ids: list[str], correlation_id: str
    ) -> list[Reversal]:
        found: list[Reversal] = []
        for record_id in record_ids:
            item = _reversal_item(conn, scope, record_id, correlation_id, DOCUMENT_TYPE, "Draft")
            if item.reversible:
                revisions = [
                    r for r in documents_registry.revisions_of(conn, record_id) if not r.voided
                ]
                if revisions or item.state not in DOCUMENT_STATES:
                    why = (
                        f"the document has {len(revisions)} revision(s)"
                        if revisions
                        else f"the document is {item.state}: not voidable here"
                    )
                    item = Reversal(record_id, item.key, item.state, False, why)
            found.append(item)
        return found

    def reverse(
        self,
        uow: UnitOfWork,
        scope: str,
        record_ids: list[str],
        *,
        actor: str,
        source: str,
        correlation_id: str,
        reason: str,
    ) -> int:
        count = 0
        for record_id in record_ids:
            row = _record(uow.conn(), record_id)
            if row is not None and bool(row.voided):
                continue
            handle_void_document(
                uow,
                VoidDocument(
                    actor=actor,
                    source=source,
                    scope=scope,
                    correlation_id=correlation_id,
                    stream_id=record_id,
                    expected_version=_version(uow.conn(), record_id),
                    reason=reason[:MAX_REASON],
                ),
            )
            count += 1
        return count


def target_for(kind: TargetKind) -> Target:
    return TagTarget() if kind == "tags" else DocumentTarget()
