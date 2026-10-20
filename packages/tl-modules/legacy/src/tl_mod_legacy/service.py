"""The stages of a legacy load run (brief 29.6).

``LoadService`` is the one object the entry points call: the CLI today, anything else later. A
stage reads the run, does its work, and appends its event and workflow move in one unit of work.
Nothing here checks a role: who may run a stage is the entry point's business (D9: every stage is
an administrator's). The file is untrusted, so it is read in the derivation envelope
(:mod:`tl_mod_legacy.extract`), never in this process.

Stages and states::

    open -> Opened -> extract -> Extracted -> profile -> Profiled -> plan -> Planned -> load ->
    Loaded -> reconcile -> Reconciled -> compensate -> Compensated;  void from Opened..Planned

``bronze`` copies the extract into the lake (any time after extract); ``plan`` may be repeated.
A stage that fails after the file is read appends ``LoadRun.Failed`` (fixed text, no cell) and
leaves the run where it was, so the stage can be run again.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

from sqlalchemy import Connection, bindparam, text
from tl_adapters.db import DbTarget, open_uow
from tl_core.files.service import FileService
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command
from tl_core.services.errors import ServiceError
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid
from tl_lake import LakeConfig

from tl_mod_legacy import bronze as bronze_module
from tl_mod_legacy import registry
from tl_mod_legacy.common import append, sha256_text, transition
from tl_mod_legacy.errors import (
    CompensationRefusedError,
    LegacyError,
    LoadRefusedError,
    LoadRunNotFoundError,
    LoadRunStateError,
    NotConfiguredError,
    SourceFileError,
    UnknownLoaderError,
)
from tl_mod_legacy.extract import content_type_of, kind_of, read_grid
from tl_mod_legacy.limits import MAX_PROBLEMS_SHOWN, MAX_REASON, MAX_RECORD_IDS
from tl_mod_legacy.model import Grid, LoaderDef, load_loaders
from tl_mod_legacy.names import (
    ACTOR,
    CORRELATION_PREFIX,
    EXTRACTED,
    LOAD_RUN,
    LOADED,
    OPENED,
    PLANNED,
    PROFILED,
    RECONCILED,
    RUN_BRONZED,
    RUN_COMPENSATED,
    RUN_EXTRACTED,
    RUN_FAILED,
    RUN_LOADED,
    RUN_OPENED,
    RUN_PLANNED,
    RUN_PROFILED,
    RUN_RECONCILED,
    RUN_VOIDED,
    SLOT_EXTRACTED,
    SLOT_PROFILE,
    SLOT_REPORT,
    SLOT_SOURCE,
    SOURCE_PREFIX,
)
from tl_mod_legacy.profile import profile_grid
from tl_mod_legacy.registry import RunRow
from tl_mod_legacy.source_layer import clean_values, write_source_layer
from tl_mod_legacy.store import JSON_TYPE, RunFiles, canonical_bytes, grid_bytes
from tl_mod_legacy.targets import Plan, target_for

MAX_SOURCE_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class LoadOutcome:
    created: int
    skipped_existing: int
    skipped_invalid: int
    source_layer_rows: int
    correlation_id: str


@dataclass(frozen=True)
class CompensationOutcome:
    reversed: int
    correlation_id: str


def _failure(stage: str, code: str, message: str) -> NewEvent:
    return NewEvent(
        event_type=RUN_FAILED, payload={"stage": stage, "code": code, "message": message[:300]}
    )


class LoadService:
    def __init__(self, db: DbTarget, files: FileService, *, lake: LakeConfig | None = None) -> None:
        self._db = db
        self._store = RunFiles(files)
        self._lake = lake

    # --- reads ------------------------------------------------------------------------------

    def get(self, scope: str, key_or_id: str) -> RunRow:
        with open_uow(self._db, readonly=True) as uow:
            return self._find(uow.conn(), scope, key_or_id)

    def runs(self, scope: str, *, state: str | None = None, limit: int = 100) -> list[RunRow]:
        with open_uow(self._db, readonly=True) as uow:
            return registry.list_runs(uow.conn(), scope, state=state, limit=limit)

    def profile_of(self, scope: str, key_or_id: str) -> dict[str, Any]:
        with open_uow(self._db, readonly=True) as uow:
            run = self._find(uow.conn(), scope, key_or_id)
            if run.profile_file_id is None or run.profile_sha256 is None:
                raise LoadRunStateError(f"{run.key} has no profile yet")
            body = self._store.read_json(uow, run.scope, run.profile_file_id, run.profile_sha256)
        return dict(body)

    def report_of(self, scope: str, key_or_id: str) -> dict[str, Any]:
        with open_uow(self._db, readonly=True) as uow:
            run = self._find(uow.conn(), scope, key_or_id)
            if run.report_file_id is None or run.report_sha256 is None:
                raise LoadRunStateError(f"{run.key} has no reconciliation report yet")
            body = self._store.read_json(uow, run.scope, run.report_file_id, run.report_sha256)
        return dict(body)

    # --- open -------------------------------------------------------------------------------

    def open(
        self,
        scope: str,
        loader_name: str,
        filename: str,
        data: bytes,
        *,
        actor: str,
        confidentiality: str | None = None,
    ) -> RunRow:
        """Record a run for a file and keep the file. Raises ``UnknownLoaderError`` or
        ``SourceFileError`` (too large, or a kind the loader does not read).

        The run has a class (ADR-0016): ``confidentiality``, else the loader's, else ``internal``.
        A ``restricted`` run, its files, its events and the ids it records are read by those who
        may read restricted records, and the documents it registers are ``restricted``.
        """
        loader = _loader(loader_name)
        klass = confidentiality or loader.confidentiality or "internal"
        if klass not in ("internal", "restricted"):
            raise LoadRefusedError("confidentiality is internal or restricted")
        name = PurePath(filename).name[:255] or "upload"
        if len(data) == 0:
            raise SourceFileError("the file is empty")
        if len(data) > MAX_SOURCE_BYTES:
            raise SourceFileError(f"the file is larger than {MAX_SOURCE_BYTES} bytes")
        kind = kind_of(name)
        if kind is None or kind not in loader.file_types:
            raise SourceFileError(
                f"loader {loader.name} reads {', '.join(loader.file_types)} files"
            )
        digest = hashlib.sha256(data).hexdigest()
        with open_uow(self._db) as uow:
            number = registry.next_number(uow.conn(), scope, loader.system, loader.table)
            key = f"{loader.system}/{loader.table}#{number}"
            cmd = self._command(scope, loader, actor, new_ulid())
            made = create_module_record(
                uow,
                cmd,
                record_type=LOAD_RUN,
                title=f"Legacy load {key}",
                key=key,
                composed_key=True,
                description=f"{loader.description}"[:500],
                extra_events=[
                    NewEvent(
                        event_type=RUN_OPENED,
                        payload={
                            "source_system": loader.system,
                            "source_table": loader.table,
                            "run_number": number,
                            "loader": loader.name,
                            "source_name": name,
                            "source_sha256": digest,
                            "source_size": len(data),
                            "opened_by": actor,
                            "confidentiality": klass,
                        },
                    )
                ],
            )
            self._store.write(
                uow,
                scope=scope,
                record_id=made.stream_id,
                slot=SLOT_SOURCE,
                filename=name,
                content_type=content_type_of(name),
                data=data,
                actor=ACTOR,
                source=cmd.source,
                correlation_id=cmd.correlation_id or new_ulid(),
            )
            run_id = made.stream_id
        return self.get(scope, run_id)

    # --- extract ----------------------------------------------------------------------------

    def extract(self, scope: str, key_or_id: str, *, actor: str) -> RunRow:
        with open_uow(self._db, readonly=True) as uow:
            run = self._find(uow.conn(), scope, key_or_id)
            _require(run, "extract", OPENED)
            loader = _loader(run.loader)
            file_id, digest = _current(uow.conn(), run.id, SLOT_SOURCE)
            data = self._store.read(uow, run.scope, file_id, digest)
            name = _source_name(uow.conn(), file_id)
        try:
            grid, extractor = read_grid(data, name, loader)
        except SourceFileError as exc:
            self._fail(run, "extract", "source_file", str(exc), actor)
            raise
        body = grid_bytes(grid)
        with open_uow(self._db) as uow:
            cmd = self._command(run.scope, loader, actor, new_ulid())
            stored = self._store.write(
                uow,
                scope=run.scope,
                record_id=run.id,
                slot=SLOT_EXTRACTED,
                filename="extracted.json",
                content_type=JSON_TYPE,
                data=body,
                actor=ACTOR,
                source=cmd.source,
                correlation_id=cmd.correlation_id or new_ulid(),
            )
            append(
                uow,
                cmd,
                run.id,
                LOAD_RUN,
                [
                    NewEvent(
                        event_type=RUN_EXTRACTED,
                        payload={
                            "row_count": len(grid.rows),
                            "column_count": len(grid.columns),
                            "extractor": extractor,
                            "extracted_file_id": stored.file_id,
                            "extracted_sha256": stored.sha256,
                        },
                    )
                ],
            )
            transition(uow, cmd, run.id, "extract")
        return self.get(scope, run.id)

    # --- profile and bronze -----------------------------------------------------------------

    def profile(self, scope: str, key_or_id: str, *, actor: str) -> RunRow:
        with open_uow(self._db, readonly=True) as uow:
            run = self._find(uow.conn(), scope, key_or_id)
            _require(run, "profile", EXTRACTED)
            loader = _loader(run.loader)
            grid = self._grid(uow, run)
        result = profile_grid(grid)
        body = canonical_bytes(result.model_dump())
        with open_uow(self._db) as uow:
            cmd = self._command(run.scope, loader, actor, new_ulid())
            stored = self._store.write(
                uow,
                scope=run.scope,
                record_id=run.id,
                slot=SLOT_PROFILE,
                filename="profile.json",
                content_type=JSON_TYPE,
                data=body,
                actor=ACTOR,
                source=cmd.source,
                correlation_id=cmd.correlation_id or new_ulid(),
            )
            append(
                uow,
                cmd,
                run.id,
                LOAD_RUN,
                [
                    NewEvent(
                        event_type=RUN_PROFILED,
                        payload={
                            "profile_file_id": stored.file_id,
                            "profile_sha256": stored.sha256,
                        },
                    )
                ],
            )
            transition(uow, cmd, run.id, "profile")
        return self.get(scope, run.id)

    def bronze(
        self, scope: str, key_or_id: str, *, actor: str, include_confidential: bool = False
    ) -> int:
        """Copy the rows as they are into the lake table ``legacy_<system>_<table>`` (replacing
        this run's rows). Returns the rows written.

        Every reader of the lake can read the copy (ADR-0016), so a run that is not ``internal``
        is never copied. For an ``internal`` run the file may still hold rows of records that are
        not: the caller says so with ``include_confidential=True``, and the choice is recorded in
        ``LoadRun.Bronzed``.
        """
        if self._lake is None:
            raise NotConfiguredError("no lake is configured for this process")
        with open_uow(self._db, readonly=True) as uow:
            run = self._find(uow.conn(), scope, key_or_id)
            if run.confidentiality not in (None, "internal"):
                raise LoadRefusedError(
                    f"{run.key} is {run.confidentiality}: the lake is read by every user, so its "
                    "rows are not copied there"
                )
            if run.state in (OPENED, "Void"):
                raise LoadRunStateError(f"{run.key} is {run.state}: extract it before bronze")
            if not include_confidential:
                raise LoadRefusedError(
                    "the file may hold rows of records that are not open to every reader, and "
                    "every reader of the lake can read a copy; pass include_confidential to copy "
                    "the rows all the same"
                )
            loader = _loader(run.loader)
            grid = self._grid(uow, run)
        written = bronze_module.write_bronze(self._lake, run.system, run.table, run.id, grid)
        with open_uow(self._db) as uow:
            append(
                uow,
                self._command(run.scope, loader, actor, new_ulid()),
                run.id,
                LOAD_RUN,
                [
                    NewEvent(
                        event_type=RUN_BRONZED,
                        payload={"bronze_rows": written, "include_confidential": True},
                    )
                ],
            )
        return written

    # --- plan -------------------------------------------------------------------------------

    def plan(self, scope: str, key_or_id: str, *, actor: str) -> tuple[RunRow, Plan]:
        """Map the rows and count what a load would do. Writes the counts to the run."""
        with open_uow(self._db, readonly=True) as uow:
            run = self._find(uow.conn(), scope, key_or_id)
            _require(run, "plan", PROFILED, PLANNED)
            loader = _loader(run.loader)
            grid = self._grid(uow, run)
            planned = target_for(loader.target).plan(uow.conn(), run.scope, loader, grid)
        counts = planned.counts()
        with open_uow(self._db) as uow:
            cmd = self._command(run.scope, loader, actor, new_ulid())
            append(
                uow,
                cmd,
                run.id,
                LOAD_RUN,
                [
                    NewEvent(
                        event_type=RUN_PLANNED,
                        payload={
                            "mapping_name": loader.name,
                            "mapping_sha256": sha256_text(loader.mapping_text),
                            "plan_new": counts["new"],
                            "plan_existing": counts["existing"],
                            "plan_invalid": counts["invalid"],
                        },
                    )
                ],
            )
            transition(uow, cmd, run.id, "plan")
        return self.get(scope, run.id), planned

    # --- load -------------------------------------------------------------------------------

    def load(
        self, scope: str, key_or_id: str, *, actor: str, expect_new: int | None = None
    ) -> LoadOutcome:
        """Write the new rows as one correlated batch: records first, then their source layer.

        The plan is made again inside the transaction and must give the counts the run recorded
        (and ``expect_new`` when the caller saw them): the project or the mapping changed since
        the plan otherwise, and the caller plans again. Rows the project holds are left alone;
        rows that cannot be loaded are skipped and counted.
        """
        with open_uow(self._db, readonly=True) as uow:
            run = self._find(uow.conn(), scope, key_or_id)
            _require(run, "load", PLANNED)
            loader = _loader(run.loader)
            grid = self._grid(uow, run)
        if run.mapping_sha256 != sha256_text(loader.mapping_text):
            raise LoadRefusedError("the mapping changed since the plan; plan the run again")
        correlation = f"{CORRELATION_PREFIX}{new_ulid()}"
        target = target_for(loader.target)
        try:
            with open_uow(self._db) as uow:
                planned = target.plan(uow.conn(), run.scope, loader, grid)
                counts = planned.counts()
                recorded = (run.plan_new, run.plan_existing, run.plan_invalid)
                if (counts["new"], counts["existing"], counts["invalid"]) != recorded:
                    raise LoadRefusedError(
                        "the project changed since the plan "
                        f"(plan {recorded[0]} new, {recorded[1]} existing, {recorded[2]} invalid; "
                        f"now {counts['new']}, {counts['existing']}, {counts['invalid']}); "
                        "plan the run again"
                    )
                if expect_new is not None and expect_new != counts["new"]:
                    raise LoadRefusedError(
                        f"you expected {expect_new} new row(s) and the plan has {counts['new']}"
                    )
                if counts["new"] == 0:
                    raise LoadRefusedError("there is nothing to load: no new rows")
                if counts["new"] > MAX_RECORD_IDS:
                    raise LoadRefusedError(f"a load writes at most {MAX_RECORD_IDS} records")
                cmd = self._command(run.scope, loader, actor, correlation)
                created = target.apply(
                    uow,
                    run.scope,
                    loader,
                    planned,
                    actor=actor,
                    source=cmd.source,
                    correlation_id=correlation,
                    confidentiality=run.confidentiality
                    if run.confidentiality == "restricted"
                    else None,
                )
                layered = 0
                for item in created:
                    if write_source_layer(
                        uow,
                        record_id=item.record_id,
                        scope=run.scope,
                        system=run.system,
                        table=run.table,
                        values=clean_values(item.raw),
                        actor=actor,
                        source=cmd.source,
                        correlation_id=correlation,
                    ):
                        layered += 1
                append(
                    uow,
                    cmd,
                    run.id,
                    LOAD_RUN,
                    [
                        NewEvent(
                            event_type=RUN_LOADED,
                            payload={
                                "loaded_count": len(created),
                                "record_ids": [c.record_id for c in created],
                                "skipped_existing": counts["existing"],
                                "skipped_invalid": counts["invalid"],
                                "correlation_id": correlation,
                            },
                        )
                    ],
                )
                transition(uow, cmd, run.id, "load")
        except ServiceError as exc:
            if not isinstance(exc, LoadRefusedError):
                self._fail(run, "load", "refused", str(exc), actor)
            raise
        return LoadOutcome(
            created=len(created),
            skipped_existing=counts["existing"],
            skipped_invalid=counts["invalid"],
            source_layer_rows=layered,
            correlation_id=correlation,
        )

    # --- reconcile --------------------------------------------------------------------------

    def reconcile(self, scope: str, key_or_id: str, *, actor: str) -> tuple[RunRow, dict[str, Any]]:
        """Compare the project with the file and store the report (counts, line numbers and field
        names; no cell). A run may be reconciled again; each report replaces the last."""
        with open_uow(self._db, readonly=True) as uow:
            run = self._find(uow.conn(), scope, key_or_id)
            _require(run, "reconcile", LOADED, RECONCILED)
            loader = _loader(run.loader)
            grid = self._grid(uow, run)
            created_keys = _keys_of(uow.conn(), run.record_ids)
            comparison = target_for(loader.target).compare(
                uow.conn(), run.scope, loader, grid, created_keys
            )
        problems = [f"line {n}: not in the project" for n in comparison.missing]
        problems += [f"line {n}: {name} differs" for n, name in comparison.differs]
        mismatches = len(comparison.missing) + len(comparison.differs)
        report: dict[str, Any] = {
            "run": run.key,
            "loader": run.loader,
            "source_sha256": run.source_sha256,
            "rows": run.row_count,
            "valid_rows": comparison.valid,
            "invalid_rows": comparison.invalid,
            "created_by_this_run": run.loaded_count,
            "matched": comparison.matched,
            "left_alone_that_differ": comparison.left_alone_differs,
            "mismatches": mismatches,
            "problems": problems[:MAX_PROBLEMS_SHOWN],
            "problems_cut": max(0, len(problems) - MAX_PROBLEMS_SHOWN),
        }
        body = canonical_bytes(report)
        with open_uow(self._db) as uow:
            cmd = self._command(run.scope, loader, actor, new_ulid())
            stored = self._store.write(
                uow,
                scope=run.scope,
                record_id=run.id,
                slot=SLOT_REPORT,
                filename="reconciliation.json",
                content_type=JSON_TYPE,
                data=body,
                actor=ACTOR,
                source=cmd.source,
                correlation_id=cmd.correlation_id or new_ulid(),
            )
            append(
                uow,
                cmd,
                run.id,
                LOAD_RUN,
                [
                    NewEvent(
                        event_type=RUN_RECONCILED,
                        payload={
                            "report_file_id": stored.file_id,
                            "report_sha256": stored.sha256,
                            "mismatches": mismatches,
                        },
                    )
                ],
            )
            transition(uow, cmd, run.id, "reconcile")
        return self.get(scope, run.id), report

    # --- compensate -------------------------------------------------------------------------

    def preview_compensation(self, scope: str, key_or_id: str) -> list[str]:
        """Why the batch cannot be taken back (empty when it can)."""
        with open_uow(self._db, readonly=True) as uow:
            run = self._find(uow.conn(), scope, key_or_id)
            return self._problems(uow.conn(), run)

    def compensate(
        self, scope: str, key_or_id: str, *, actor: str, reason: str
    ) -> CompensationOutcome:
        """End the records this run created, all or nothing, by the ids the run recorded."""
        why = reason.strip()
        if not why:
            raise LoadRefusedError("a reason is required")
        with open_uow(self._db, readonly=True) as uow:
            run = self._find(uow.conn(), scope, key_or_id)
            _require(run, "compensate", LOADED, RECONCILED)
            loader = _loader(run.loader)
        correlation = f"{CORRELATION_PREFIX}{new_ulid()}"
        with open_uow(self._db) as uow:
            problems = self._problems(uow.conn(), run)
            if problems:
                raise CompensationRefusedError(
                    f"{run.key} cannot be taken back: " + "; ".join(problems[:5]), problems
                )
            cmd = self._command(run.scope, loader, actor, correlation)
            done = target_for(loader.target).reverse(
                uow,
                run.scope,
                run.record_ids,
                actor=actor,
                source=f"compensation:{run.id}",
                correlation_id=correlation,
                reason=f"compensation of {run.correlation_id}: {why}"[:MAX_REASON],
            )
            append(
                uow,
                cmd,
                run.id,
                LOAD_RUN,
                [
                    NewEvent(
                        event_type=RUN_COMPENSATED,
                        payload={"reversed": done, "correlation_id": correlation},
                    )
                ],
            )
            transition(uow, cmd, run.id, "compensate", reason=why[:MAX_REASON])
        return CompensationOutcome(reversed=done, correlation_id=correlation)

    def void(self, scope: str, key_or_id: str, *, actor: str, reason: str) -> RunRow:
        why = reason.strip()
        if not why:
            raise LoadRefusedError("a reason is required")
        with open_uow(self._db) as uow:
            run = self._find(uow.conn(), scope, key_or_id)
            _require(run, "void", OPENED, EXTRACTED, PROFILED, PLANNED)
            cmd = self._command(run.scope, _loader(run.loader), actor, new_ulid())
            append(
                uow,
                cmd,
                run.id,
                LOAD_RUN,
                [NewEvent(event_type=RUN_VOIDED, payload={"reason": why[:MAX_REASON]})],
            )
            transition(uow, cmd, run.id, "void", reason=why[:MAX_REASON])
        return self.get(scope, run.id)

    # --- internals --------------------------------------------------------------------------

    @staticmethod
    def _command(scope: str, loader: LoaderDef, actor: str, correlation: str) -> Command:
        return Command(
            actor=actor,
            source=f"{SOURCE_PREFIX}{loader.system}",
            scope=scope,
            correlation_id=correlation,
        )

    def _grid(self, uow: UnitOfWork, run: RunRow) -> Grid:
        if run.extracted_file_id is None or run.extracted_sha256 is None:
            raise LoadRunStateError(f"{run.key} has not been extracted")
        return self._store.read_grid(uow, run.scope, run.extracted_file_id, run.extracted_sha256)

    @staticmethod
    def _find(conn: Connection, scope: str, key_or_id: str) -> RunRow:
        run = registry.find_run(conn, scope, key_or_id) or registry.get_run(conn, key_or_id)
        if run is None or run.scope != scope:
            raise LoadRunNotFoundError(f"no load run {key_or_id!r} in {scope}")
        return run

    def _problems(self, conn: Connection, run: RunRow) -> list[str]:
        if not run.record_ids or run.correlation_id is None:
            return ["the run recorded no records"]
        items = target_for(_loader(run.loader).target).reversals(
            conn, run.scope, run.record_ids, run.correlation_id
        )
        return [
            f"{item.key or item.record_id}: {item.problem}" for item in items if not item.reversible
        ]

    def _fail(self, run: RunRow, stage: str, code: str, message: str, actor: str) -> None:
        try:
            with open_uow(self._db) as uow:
                append(
                    uow,
                    Command(actor=actor, source=f"{SOURCE_PREFIX}{run.system}", scope=run.scope),
                    run.id,
                    LOAD_RUN,
                    [_failure(stage, code, message)],
                )
        except LegacyError:
            pass


def _loader(name: str) -> LoaderDef:
    found = load_loaders().get(name)
    if found is None:
        known = ", ".join(sorted(load_loaders())) or "none installed"
        raise UnknownLoaderError(f"no loader {name!r} (installed: {known})")
    return found


def _require(run: RunRow, stage: str, *states: str) -> None:
    if run.state not in states:
        raise LoadRunStateError(f"{run.key} is {run.state}: {stage} needs {' or '.join(states)}")


def _current(conn: Connection, record_id: str, slot: str) -> tuple[str, str]:
    row = conn.execute(
        text(
            "SELECT file_id, sha256 FROM cur_files WHERE record_id = :r AND slot = :s "
            "AND status <> 'rejected' AND superseded_by IS NULL ORDER BY revision DESC LIMIT 1"
        ),
        {"r": record_id, "s": slot},
    ).first()
    if row is None:
        raise SourceFileError(f"the run has no file in the slot {slot}")
    return str(row.file_id), str(row.sha256)


def _source_name(conn: Connection, file_id: str) -> str:
    found = conn.execute(
        text("SELECT filename FROM cur_files WHERE file_id = :f"), {"f": file_id}
    ).scalar_one()
    return str(found)


def _keys_of(conn: Connection, record_ids: list[str]) -> set[str]:
    keys: set[str] = set()
    statement = text("SELECT key FROM cur_core_record WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    for start in range(0, len(record_ids), 400):
        keys.update(
            str(k)
            for k in conn.execute(statement, {"ids": record_ids[start : start + 400]}).scalars()
        )
    return keys
