"""The schedule section of the demo project (P2-SEED-T07): one main schedule and four published
snapshots built through the real path, with CWP links to the last snapshot's activities.

Each run builds a fresh SQLite ledger in a child process (``python -m dev.seed.demo_project``; the
generator sets ``TL_SCHEMA_DIR`` for its own process, so it must not run inside the test session).
The runs are: ``core,awp,schedule`` (the section with the awp CWPs), the same again (one seed, one
project), and the same without ``schedule`` (the other types must not move).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import open_uow

ROOT = Path(__file__).resolve().parents[2]
SECTIONS_WITH = "core,engineering,awp,schedule"
SECTIONS_WITHOUT = "core,engineering,awp"
SCHEDULE_TYPES = ("schedule.Schedule", "schedule.ScheduleSnapshot", "schedule.ActivityRef")


@dataclass(frozen=True)
class Run:
    db: Path
    stdout: str
    returncode: int


def generate(db: Path, objects: Path, sections: str) -> Run:
    env = {**os.environ, "TL_ENV": "dev", "PYTHONPATH": str(ROOT)}
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "dev.seed.demo_project",
            "--db",
            str(db),
            "--objects",
            str(objects),
            "--sections",
            sections,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    return Run(db, done.stdout, done.returncode)


def rows(db: Path, sql: str) -> list[dict[str, object]]:
    with open_uow(db, readonly=True) as uow:
        return [dict(r) for r in uow.conn().execute(text(sql)).mappings()]


def count(db: Path, sql: str) -> int:
    return int(next(iter(rows(db, sql)[0].values())))  # type: ignore[arg-type]


def per_type(db: Path) -> dict[str, int]:
    found = rows(db, "SELECT type, COUNT(*) AS n FROM cur_core_record GROUP BY type")
    return {str(r["type"]): int(str(r["n"])) for r in found}


def key_hash(db: Path, record_type: str) -> str:
    found = rows(
        db,
        f"SELECT key FROM cur_core_record WHERE type = '{record_type}' ORDER BY key",
    )
    return hashlib.sha256("\n".join(str(r["key"]) for r in found).encode()).hexdigest()


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Run]:
    base = tmp_path_factory.mktemp("demo-project-schedule")
    made = {
        "main": generate(base / "main.db", base / "objects-main", SECTIONS_WITH),
        "again": generate(base / "again.db", base / "objects-again", SECTIONS_WITH),
        "without": generate(base / "without.db", base / "objects-without", SECTIONS_WITHOUT),
    }
    for name, run in made.items():
        assert run.returncode == 0, f"{name} failed"
    return made


def test_one_schedule_and_four_published_snapshots(runs: dict[str, Run]) -> None:
    db = runs["main"].db
    assert count(db, "SELECT COUNT(*) FROM cur_core_record WHERE type = 'schedule.Schedule'") == 1
    snapshots = rows(
        db,
        "SELECT r.key AS key, r.status AS status FROM cur_schedule_schedule_snapshot s "
        "JOIN cur_core_record r ON r.id = s.id ORDER BY r.key",
    )
    assert len(snapshots) == 4
    # every snapshot was published; the earlier three are Superseded by the later ones
    statuses = [str(s["status"]) for s in snapshots]
    assert all(status in ("Published", "Superseded") for status in statuses), statuses
    assert statuses.count("Published") == 1


def test_activity_refs_exist_for_the_last_snapshot(runs: dict[str, Run]) -> None:
    db = runs["main"].db
    last = rows(
        db,
        "SELECT s.id AS id FROM cur_schedule_schedule_snapshot s "
        "JOIN cur_core_record r ON r.id = s.id WHERE r.status = 'Published'",
    )
    assert len(last) == 1
    activities = {
        str(r["activity_id"])
        for r in rows(
            db,
            f"SELECT activity_id FROM sched_activity WHERE snapshot_id = '{last[0]['id']}'",
        )
    }
    refs = rows(db, "SELECT activity_id FROM cur_schedule_activity_ref")
    assert refs, "no activity refs were made"
    assert all(str(r["activity_id"]) in activities for r in refs)


def test_eight_or_more_links_when_awp_ran(runs: dict[str, Run]) -> None:
    db = runs["main"].db
    links = count(
        db,
        "SELECT COUNT(*) FROM cur_links l JOIN cur_schedule_activity_ref a ON a.id = l.to_id",
    )
    assert 8 <= links <= 10
    assert "schedule: links skipped" not in runs["main"].stdout


def test_two_runs_with_one_seed_give_the_same_counts_and_keys(runs: dict[str, Run]) -> None:
    main, again = runs["main"].db, runs["again"].db
    assert per_type(main) == per_type(again)
    for record_type in SCHEDULE_TYPES:
        assert key_hash(main, record_type) == key_hash(again, record_type), record_type
    assert count(main, "SELECT COUNT(*) FROM cur_links") == count(
        again, "SELECT COUNT(*) FROM cur_links"
    )


def test_without_schedule_the_other_types_do_not_move(runs: dict[str, Run]) -> None:
    with_schedule = per_type(runs["main"].db)
    without = per_type(runs["without"].db)
    assert with_schedule["schedule.Schedule"] == 1
    assert with_schedule["schedule.ScheduleSnapshot"] == 4
    assert "schedule.Schedule" not in without
    for record_type in SCHEDULE_TYPES:
        with_schedule.pop(record_type, None)
    assert with_schedule == without
