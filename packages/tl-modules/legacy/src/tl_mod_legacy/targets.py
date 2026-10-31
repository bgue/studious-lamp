"""Where the rows of a legacy file go: a registered load target (built in: tags, documents).

Targets are plugins of the group ``throughline.load_targets``: each entry point names a
zero-argument callable that returns a :class:`Target`. The built-ins are registered by this
package's own ``pyproject.toml``; a module adds its own by adding a line to its own. A target
declares its ``scope`` (``project`` or ``company``): ``tl load open --company`` opens a run for a
company target, and a project target refuses it (and the reverse). A module without a handler
class can build a target from a declarative mapping with :func:`mapping_target`.

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

import logging
import re
import threading
from collections.abc import Generator, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib import metadata
from typing import Any, Literal, Protocol, runtime_checkable

import yaml
from sqlalchemy import Connection, bindparam, text
from tl_core.ledger import NewEvent
from tl_core.modules import ModuleLoadError
from tl_core.services.commands import Command
from tl_core.services.records import create_module_record
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

from tl_mod_legacy.errors import LoadRefusedError, MappingProblemError
from tl_mod_legacy.limits import MAX_REASON
from tl_mod_legacy.model import Grid, LoaderDef, TargetKind

LOAD_TARGET_ENTRY_POINT = "throughline.load_targets"
TargetScope = Literal["project", "company"]
KEY_BATCH = 400
_NAME = re.compile(r"[a-z][a-z0-9_]*")
log = logging.getLogger(__name__)
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


class TargetLoadError(ModuleLoadError):
    """An installed load target cannot be loaded, is misnamed, or is declared twice."""


@runtime_checkable
class Target(Protocol):
    #: The registered name (the entry point's name) a loader's ``target`` refers to.
    kind: TargetKind
    #: The module that registers it (listed by ``tl load targets``).
    module: str
    #: ``project`` (a run is opened with ``--project``) or ``company`` (with ``--company``).
    scope: TargetScope

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
    module = "legacy"
    scope: TargetScope = "project"

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
    module = "legacy"
    scope: TargetScope = "project"

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


def tags_target() -> Target:
    """Entry point ``tags`` of the group ``throughline.load_targets``."""
    return TagTarget()


def documents_target() -> Target:
    """Entry point ``documents`` of the group ``throughline.load_targets``."""
    return DocumentTarget()


# --- a target built from a declarative mapping --------------------------------------------------

MAPPING_FIELDS = ("title", "description")


class MappingTarget:
    """A target with no handler class: a record type, a key column and a column -> field map.

    A row is a record of ``record_type`` keyed by the ``key_column`` cell. ``columns`` maps a file
    column to ``title`` or ``description`` (no ``title`` mapped: the key is the title). Records are
    created with ``create_module_record`` (an envelope event, no other event of the module), so
    the form fits a record type that its module projects from that event alone. Create-only: a key
    the scope holds is left alone, and compensation voids exactly the records the run made.
    """

    def __init__(
        self,
        kind: str,
        *,
        module: str,
        record_type: str,
        key_column: str,
        columns: Mapping[str, str],
        scope: TargetScope = "project",
    ) -> None:
        if _NAME.fullmatch(kind) is None:
            raise ValueError(f"target {kind!r}: the name must match ^[a-z][a-z0-9_]*$")
        if scope not in ("project", "company"):
            raise ValueError(f"target {kind}: scope is project or company")
        unknown = sorted(set(columns.values()) - set(MAPPING_FIELDS))
        if unknown:
            raise ValueError(
                f"target {kind}: a column maps to {', '.join(MAPPING_FIELDS)}, not {unknown[0]!r}"
            )
        self.kind = kind
        self.module = module
        self.scope: TargetScope = scope
        self.record_type = record_type
        self.key_column = key_column
        self.columns = dict(columns)

    def _check(self, grid: Grid) -> None:
        missing = [c for c in (self.key_column, *self.columns) if c not in grid.columns]
        if missing:
            raise MappingProblemError(f"target {self.kind}: the file has no column {missing[0]!r}")

    def _cells(self, grid: Grid) -> list[tuple[int, str, dict[str, str]]]:
        """``(line, key, raw)`` per data row; ``key`` is empty for a row without one."""
        self._check(grid)
        out: list[tuple[int, str, dict[str, str]]] = []
        for index, cells in enumerate(grid.rows):
            raw = {c: ("" if v is None else v) for c, v in zip(grid.columns, cells, strict=False)}
            out.append((index + 2, raw.get(self.key_column, "").strip(), raw))
        return out

    def _field(self, raw: dict[str, str], name: str) -> str | None:
        for column, target in self.columns.items():
            if target == name and raw.get(column, "").strip():
                return raw[column].strip()
        return None

    def plan(self, conn: Connection, scope: str, loader: LoaderDef, grid: Grid) -> Plan:
        cells = self._cells(grid)
        held = _ids_by_key(conn, scope, self.record_type, [k for _, k, _ in cells if k])
        new: list[PlannedRow] = []
        existing: list[str] = []
        invalid: list[tuple[int, str]] = []
        seen: set[str] = set()
        for line, key, raw in cells:
            if not key:
                invalid.append((line, "no key"))
            elif key in seen:
                invalid.append((line, "key repeated"))
            elif key in held:
                seen.add(key)
                existing.append(key)
            else:
                seen.add(key)
                new.append(PlannedRow(line, key, raw))
        return Plan(rows=new, existing=existing, invalid=invalid)

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
        made: list[Created] = []
        for row in plan.rows:
            result = create_module_record(
                uow,
                Command(actor=actor, source=source, scope=scope, correlation_id=correlation_id),
                record_type=self.record_type,
                title=self._field(row.raw, "title") or row.key,
                description=self._field(row.raw, "description"),
                key=row.key,
            )
            made.append(Created(result.stream_id, row.key, row.line, row.raw))
        return made

    def compare(
        self, conn: Connection, scope: str, loader: LoaderDef, grid: Grid, created_keys: set[str]
    ) -> Comparison:
        cells = self._cells(grid)
        held: dict[str, Any] = {}
        statement = text(
            "SELECT key, title, description, voided FROM cur_core_record "
            "WHERE scope = :s AND type = :t AND key IN :keys"
        ).bindparams(bindparam("keys", expanding=True))
        keys = [k for _, k, _ in cells if k]
        for start in range(0, len(keys), KEY_BATCH):
            for row in conn.execute(
                statement,
                {"s": scope, "t": self.record_type, "keys": keys[start : start + KEY_BATCH]},
            ):
                held[str(row.key)] = row
        valid = matched = left = invalid = 0
        missing: list[int] = []
        differs: list[tuple[int, str]] = []
        seen: set[str] = set()
        for line, key, raw in cells:
            if not key or key in seen:
                invalid += 1
                continue
            seen.add(key)
            valid += 1
            found = held.get(key)
            if found is None or bool(found.voided):
                missing.append(line)
                continue
            fields = [
                name
                for name, mine, theirs in (
                    ("title", self._field(raw, "title"), found.title),
                    ("description", self._field(raw, "description"), found.description),
                )
                if mine is not None and mine != theirs
            ]
            if not fields:
                matched += 1
            elif key in created_keys:
                differs.extend((line, name) for name in fields)
            else:
                left += 1
        return Comparison(valid, matched, missing, differs, left, invalid)

    def reversals(
        self, conn: Connection, scope: str, record_ids: list[str], correlation_id: str
    ) -> list[Reversal]:
        return [
            _reversal_item(conn, scope, record_id, correlation_id, self.record_type, "Created")
            for record_id in record_ids
        ]

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
            uow.append(
                stream_id=record_id,
                stream_type=self.record_type,
                scope=scope,
                expected_version=_version(uow.conn(), record_id),
                events=[
                    NewEvent(event_type="Record.Voided", payload={"reason": reason[:MAX_REASON]})
                ],
                actor=actor,
                source=source,
                correlation_id=correlation_id,
            )
            count += 1
        return count


def mapping_target(
    kind: str,
    *,
    module: str,
    record_type: str,
    key_column: str,
    columns: Mapping[str, str],
    scope: TargetScope = "project",
) -> Target:
    """A target from a declarative mapping (record type, key column, column -> field map)."""
    return MappingTarget(
        kind,
        module=module,
        record_type=record_type,
        key_column=key_column,
        columns=columns,
        scope=scope,
    )


# --- the registry -------------------------------------------------------------------------------

_lock = threading.Lock()
_found: dict[str, Target] | None = None
_override: dict[str, Target] | None = None


def load_targets(entry_points: Iterable[metadata.EntryPoint] | None = None) -> dict[str, Target]:
    """The load targets by name, sorted by name.

    ``entry_points`` is an iterable of entry points (a test injects plugins); the default reads
    the group ``throughline.load_targets``. Raises :class:`TargetLoadError` (a ``ModuleLoadError``)
    naming the group and the entry point for a plugin that does not load, does not return a
    ``Target`` of its own name, has a name outside ``^[a-z][a-z0-9_]*$`` or repeats a name.
    """
    points = (
        metadata.entry_points(group=LOAD_TARGET_ENTRY_POINT)
        if entry_points is None
        else entry_points
    )
    found: dict[str, Target] = {}
    for entry in sorted(points, key=lambda e: (e.name, e.value)):
        where = f"{LOAD_TARGET_ENTRY_POINT} entry point {entry.name!r}"
        if _NAME.fullmatch(entry.name) is None:
            raise TargetLoadError(f"{where}: the name must match ^[a-z][a-z0-9_]*$")
        try:
            produced = entry.load()()
        except Exception as exc:
            log.warning("%s cannot be loaded: %s", where, exc, exc_info=True)
            raise TargetLoadError(f"{where} cannot be loaded: {type(exc).__name__}") from exc
        if (
            not isinstance(produced, Target)
            or produced.kind != entry.name
            or produced.scope not in ("project", "company")
        ):
            raise TargetLoadError(
                f"{where} must return a Target of the same name with scope project or company"
            )
        if entry.name in found:
            raise TargetLoadError(
                f"{LOAD_TARGET_ENTRY_POINT}: target {entry.name!r} is declared twice"
            )
        found[entry.name] = produced
    return dict(sorted(found.items()))


def installed_targets() -> Mapping[str, Target]:
    """The installed load targets by name, found once per process."""
    global _found
    with _lock:
        if _override is not None:
            return _override
        if _found is None:
            _found = load_targets()
        return _found


@contextmanager
def use_targets(targets: Mapping[str, Target]) -> Generator[None]:
    """Make ``targets`` the only load targets for the block (tests)."""
    global _override
    with _lock:
        previous, _override = _override, dict(targets)
    try:
        yield
    finally:
        with _lock:
            _override = previous


def target_for(kind: TargetKind) -> Target:
    """The target registered as ``kind``; ``LoadRefusedError`` names the known ones."""
    targets = installed_targets()
    found = targets.get(kind)
    if found is None:
        known = ", ".join(sorted(targets)) or "none installed"
        raise LoadRefusedError(f"no load target {kind!r} (known: {known})")
    return found


def check_scope(target: Target, scope: str) -> None:
    """A company target is opened for ``company`` and a project target for ``project:<ID>``."""
    if target.scope == "company" and scope != "company":
        raise LoadRefusedError(
            f"load target {target.kind} loads into the company: open the run with --company"
        )
    if target.scope == "project" and not scope.startswith("project:"):
        raise LoadRefusedError(
            f"load target {target.kind} loads into a project: open the run with --project"
        )
