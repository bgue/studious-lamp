"""Test support other packages share: a ledger, an object store and the schedule commands.

``ScheduleWorld`` wraps a ledger target, a file store and the file service, and offers one call per
thing a test does: define a schedule, upload an XER file (open, attach, queue, build), publish,
link a record to an activity. Every call opens its own unit of work, like a real command. It is
not registered anywhere and never runs in production.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import replace
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_adapters.objectstore.fs import FsObjectStore
from tl_core.files.service import CompleteUpload, FileResult, FileService, RegisterUpload
from tl_core.services.commands import CommandResult, CreateRecord
from tl_core.services.records import handle_create_record
from tl_xer.synth import Scenario, make_xer, week_pair

from tl_mod_schedule import registry
from tl_mod_schedule.handlers.activity import LinkActivity, handle_link_activity
from tl_mod_schedule.handlers.publish import (
    PublishScheduleSnapshot,
    handle_publish_schedule_snapshot,
)
from tl_mod_schedule.handlers.schedules import DefineSchedule, handle_define_schedule
from tl_mod_schedule.handlers.snapshots import (
    OpenScheduleSnapshot,
    StartScheduleSnapshot,
    VoidScheduleSnapshot,
    handle_open_schedule_snapshot,
    handle_start_schedule_snapshot,
    handle_void_schedule_snapshot,
)
from tl_mod_schedule.registry import ActivityRow, RelationshipRow
from tl_mod_schedule.worker import build_worker

PROJECT = "project:P123"
BASE: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": PROJECT}
XER_TYPE = "application/octet-stream"


class ScheduleWorld:
    def __init__(self, db: DbTarget, objects: Path) -> None:
        self.db = db
        self.store = FsObjectStore(objects, secret=b"s")
        self.files = FileService(self.store, secret=b"s")
        self._records = 0

    # --- reads -----------------------------------------------------------------------------

    def scalar(self, sql: str, **params: Any) -> Any:
        with open_uow(self.db, readonly=True) as uow:
            return uow.conn().execute(text(sql), params).scalar_one()

    def rows(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with open_uow(self.db, readonly=True) as uow:
            return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]

    def schedule(self, code: str = "MAIN") -> registry.ScheduleRow:
        with open_uow(self.db, readonly=True) as uow:
            found = registry.find_schedule(uow.conn(), PROJECT, code)
        assert found is not None
        return found

    def snapshot(self, snapshot_id: str) -> registry.SnapshotRow:
        with open_uow(self.db, readonly=True) as uow:
            found = registry.get_snapshot(uow.conn(), snapshot_id)
        assert found is not None
        return found

    def snapshots(self, code: str = "MAIN") -> list[registry.SnapshotRow]:
        schedule = self.schedule(code)
        with open_uow(self.db, readonly=True) as uow:
            return registry.list_snapshots(uow.conn(), schedule.id)

    def activities(self, snapshot_id: str) -> list[registry.ActivityRow]:
        with open_uow(self.db, readonly=True) as uow:
            return registry.activities(uow.conn(), snapshot_id)

    def ref(self, code: str, activity_id: str) -> registry.ActivityRefRow | None:
        schedule = self.schedule(code)
        with open_uow(self.db, readonly=True) as uow:
            return registry.find_ref(uow.conn(), schedule.id, activity_id)

    # --- writes ----------------------------------------------------------------------------

    def define(self, code: str = "MAIN", **more: Any) -> CommandResult:
        fields: dict[str, Any] = {"code": code, "name": "Main schedule", "schedule_type": "current"}
        fields.update(more)
        with open_uow(self.db) as uow:
            return handle_define_schedule(uow, DefineSchedule(**{**BASE, **fields}))

    def open_snapshot(self, code: str = "MAIN", **more: Any) -> CommandResult:
        schedule = self.schedule(code)
        with open_uow(self.db) as uow:
            return handle_open_schedule_snapshot(
                uow, OpenScheduleSnapshot(**{**BASE, "schedule_id": schedule.id, **more})
            )

    def attach_xer(
        self, snapshot_id: str, data: bytes, name: str = "export.xer", slot: str = "xer"
    ) -> FileResult:
        """Upload ``data`` into a slot of the snapshot through the file service (guards apply)."""
        declared = RegisterUpload(
            **BASE,
            record_id=snapshot_id,
            slot=slot,
            filename=name,
            content_type=XER_TYPE,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        with open_uow(self.db) as uow:
            ticket = self.files.register_upload(uow, declared)
        with open_uow(self.db) as uow:
            return self.files.complete_upload(
                uow, CompleteUpload(**BASE, upload_id=ticket.upload_id), io.BytesIO(data)
            )

    def start(self, snapshot_id: str) -> CommandResult:
        with open_uow(self.db) as uow:
            return handle_start_schedule_snapshot(
                uow, StartScheduleSnapshot(**BASE, snapshot_id=snapshot_id)
            )

    def work_once(self) -> Any:
        """One pass of the queue (one job); ``None`` when nothing is queued."""
        with build_worker(self.db, self.files, worker_id="test") as worker:
            return worker.runner.run_once()

    def work(self, **limits: Any) -> list[Any]:
        """Run the queue until it is empty (the snapshot builds); the results of each pass."""
        with build_worker(self.db, self.files, worker_id="test", **limits) as worker:
            return worker.runner.run_until_idle()

    def upload(self, data: bytes, code: str = "MAIN", name: str = "export.xer", **more: Any) -> str:
        """Open a snapshot, attach the file, queue and build it; the snapshot id."""
        snapshot_id = self.open_snapshot(code, **more).stream_id
        self.attach_xer(snapshot_id, data, name)
        self.start(snapshot_id)
        self.work()
        return snapshot_id

    def publish(self, snapshot_id: str, *, check: bool = True) -> CommandResult:
        """Publish, and (``check``) run the worker so the flagging job has finished, as a worker
        would a moment later. ``check=False`` leaves the window of ADR-0015 section 5 open."""
        with open_uow(self.db) as uow:
            made = handle_publish_schedule_snapshot(
                uow, PublishScheduleSnapshot(**BASE, snapshot_id=snapshot_id)
            )
        if check:
            self.work()
        return made

    def void(self, snapshot_id: str, reason: str = "wrong file") -> CommandResult:
        with open_uow(self.db) as uow:
            return handle_void_schedule_snapshot(
                uow, VoidScheduleSnapshot(**BASE, snapshot_id=snapshot_id, reason=reason)
            )

    def record(self, key: str | None = None) -> str:
        """A bare record to link from; returns its id. Without a key each call has its own."""
        self._records += 1
        key = key or f"R-{self._records}"
        with open_uow(self.db) as uow:
            made = handle_create_record(
                uow, CreateRecord(**BASE, record_type="core.Record", title=key, key=key)
            )
        return made.stream_id

    def link(
        self, from_id: str, activity_id: str, code: str = "MAIN", pin: int | None = None
    ) -> CommandResult:
        schedule = self.schedule(code)
        with open_uow(self.db) as uow:
            return handle_link_activity(
                uow,
                LinkActivity(
                    **BASE,
                    from_id=from_id,
                    schedule_id=schedule.id,
                    activity_id=activity_id,
                    pin=pin,
                ),
            )

    def link_row(self, link_id: str) -> dict[str, Any]:
        [found] = self.rows("SELECT * FROM cur_links WHERE link_id = :i", i=link_id)
        return found

    def two_weeks(self, code: str = "MAIN") -> tuple[str, str]:
        """The demo's two files, uploaded and built: the snapshot ids, oldest first."""
        first, second = week_pair()
        return self.upload(make_xer(first), code), self.upload(make_xer(second), code)

    def scenario_xer(self, scenario: Scenario) -> bytes:
        return make_xer(scenario)


def make_activity(activity_id: str, **more: Any) -> ActivityRow:
    """An ``ActivityRow`` for a test that needs no database: a task from 2026-10-05, 40 h of float.

    Keyword arguments replace fields (``total_float_hr=0.0``, ``status="in_progress"``).
    """
    base = ActivityRow(
        snapshot_id="s",
        activity_id=activity_id,
        task_id=activity_id,
        name=f"Activity {activity_id}",
        wbs_id="1",
        wbs_path="P > W",
        task_type="task",
        status="not_started",
        calendar_id="1",
        original_duration_hr=80.0,
        remaining_duration_hr=80.0,
        early_start="2026-10-05T08:00",
        early_finish="2026-10-16T16:00",
        late_start="2026-10-12T08:00",
        late_finish="2026-10-23T16:00",
        actual_start=None,
        actual_finish=None,
        target_start="2026-10-05T08:00",
        target_finish="2026-10-16T16:00",
        total_float_hr=40.0,
        free_float_hr=40.0,
        percent_complete=0.0,
        percent_type="CP_Drtn",
        constraint_type=None,
        constraint_date=None,
        critical=False,
        longest_path=False,
        seq=1,
    )
    return replace(base, **more)


def make_relationship(
    pred: str, succ: str, kind: str = "FS", lag_hr: float = 0.0
) -> RelationshipRow:
    """A ``RelationshipRow`` for a test that needs no database."""
    return RelationshipRow("s", pred, succ, kind, lag_hr, 1)
