"""schedule section of P200: the main schedule and four weekly snapshots, built through the real
path (P2-SEED-T07).

One ``DefineSchedule`` (code ``MAIN``), then four snapshots, one per week. Each snapshot is opened,
its XER file is attached through the file service, queued, built by the worker and published, all
on the day the snapshot falls (``world.on``). The files are the first four weeks of a synthetic
P6 series (``tl_xer.synth.series``), pure bytes with no clock. When the awp section ran, 8 to 10 of
its CWPs are linked to activities of the last snapshot, the choices drawn from the section's own
``rng``. Everything runs as ``mokafor`` (the administrator); nothing writes SQL directly.
"""

from __future__ import annotations

import random
from datetime import date

from tl_adapters.db import open_uow
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
    handle_open_schedule_snapshot,
    handle_start_schedule_snapshot,
)
from tl_mod_schedule.names import SLOT_XER
from tl_mod_schedule.worker import build_worker
from tl_xer.synth import make_xer, series

from dev.seed.demo_project.core import ADMIN
from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import PROJECT, TODAY, World

SCHEDULE_CODE = "MAIN"
SCHEDULE_NAME = "Main schedule"
SERIES_SEED = 2026  # the synthetic P6 series is a fixed history; the seed is not a random draw
WEEKS = 4
#: The day each snapshot is opened, built and published (the fourth is the fixed "today").
SNAPSHOT_DAYS: tuple[date, ...] = (date(2026, 10, 19), date(2026, 10, 26), date(2026, 11, 2), TODAY)
LINKS = (8, 10)  # the number of CWPs linked to activities, drawn from this range
XER_CONTENT_TYPE = "application/octet-stream"


def _ids(world: World, record_type: str) -> list[str]:
    """The ids of every record of ``record_type`` in the project, in key order."""
    return [
        str(r["id"])
        for r in world.rows(
            "SELECT id FROM cur_core_record WHERE scope = :s AND type = :t ORDER BY key",
            s=PROJECT,
            t=record_type,
        )
    ]


def _work(world: World) -> None:
    """Run the worker until the queue is empty (the same calls as ``ScheduleWorld.work``)."""
    with build_worker(world.target, world.files, worker_id="seed") as worker:
        worker.runner.run_until_idle()


def _build_snapshot(world: World, schedule_id: str, index: int, day: date, xer: bytes) -> str:
    """Open, attach, queue, build and publish one snapshot on ``day``; its id."""
    with world.on(day):
        opened = world.run(
            handle_open_schedule_snapshot,
            OpenScheduleSnapshot,
            by=ADMIN,
            schedule_id=schedule_id,
        )
        snapshot_id = str(opened.stream_id)
        world.upload(
            snapshot_id,
            slot=SLOT_XER,
            filename=f"schedule-week-{index + 1}.xer",
            data=xer,
            by=ADMIN,
            content_type=XER_CONTENT_TYPE,
        )
        world.run(
            handle_start_schedule_snapshot,
            StartScheduleSnapshot,
            by=ADMIN,
            snapshot_id=snapshot_id,
        )
        _work(world)
        world.run(
            handle_publish_schedule_snapshot,
            PublishScheduleSnapshot,
            by=ADMIN,
            snapshot_id=snapshot_id,
        )
        _work(world)
    return snapshot_id


def _link_cwps(world: World, rng: random.Random, schedule_id: str, snapshot_id: str) -> None:
    """Link 8 to 10 CWPs to activities of the last snapshot, or say so in one line."""
    cwps = _ids(world, "awp.CWP")
    if not cwps:
        print("schedule: links skipped, the awp section is absent (no CWPs to link)")
        return
    with open_uow(world.target, readonly=True) as uow:
        activities = registry.activities(uow.conn(), snapshot_id)
    count = min(rng.randint(*LINKS), len(cwps), len(activities))
    chosen_cwps = rng.sample(cwps, count)
    chosen_activities = rng.sample(activities, count)
    with world.on(TODAY):
        for cwp, activity in zip(chosen_cwps, chosen_activities, strict=True):
            world.run(
                handle_link_activity,
                LinkActivity,
                by=ADMIN,
                from_id=cwp,
                schedule_id=schedule_id,
                activity_id=activity.activity_id,
            )


def build(world: World, rng: random.Random) -> None:
    with world.on(SNAPSHOT_DAYS[0]):
        defined = world.run(
            handle_define_schedule,
            DefineSchedule,
            by=ADMIN,
            code=SCHEDULE_CODE,
            name=SCHEDULE_NAME,
            schedule_type="current",
        )
    schedule_id = str(defined.stream_id)
    snapshot_id = ""
    weeks = series(SERIES_SEED, WEEKS)
    for index, (scenario, day) in enumerate(zip(weeks, SNAPSHOT_DAYS, strict=True)):
        snapshot_id = _build_snapshot(world, schedule_id, index, day, make_xer(scenario))
    _link_cwps(world, rng, schedule_id, snapshot_id)


register("schedule", build, needs=("schedule.Schedule",))
