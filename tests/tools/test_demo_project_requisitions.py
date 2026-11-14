"""The requisitions section of the demo project (P2-SEED-T08): 24 requisitions and work orders,
raised and driven through the real commands.

Each run builds a fresh SQLite ledger in a child process (``python -m dev.seed.demo_project``; the
generator sets ``TL_SCHEMA_DIR`` for its own process, so it must not run inside the test session).
The runs are: the section on its own sources, the same again (one seed, one project), and the same
without ``requisitions`` (the other types must not move).
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
TODAY = "2026-11-06"
SOURCES = "core,engineering,awp,materials"
SECTIONS = f"{SOURCES},requisitions"
NO_MATERIALS_NOTE = "requisitions: no materials section"


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
        timeout=1500,
    )
    return Run(db, done.stdout, done.returncode)


def rows(db: Path, sql: str) -> list[dict[str, object]]:
    with open_uow(db, readonly=True) as uow:
        return [dict(r) for r in uow.conn().execute(text(sql)).mappings()]


REQUISITIONS = (
    "SELECT r.key AS key, r.type AS type, COALESCE(r.status, 'Requested') AS state "
    "FROM cur_core_record r WHERE r.type LIKE 'requisitions.%' "
    "AND r.type <> 'requisitions.WorkOrder' ORDER BY r.key"
)
WORK_ORDERS = (
    "SELECT r.key AS key, COALESCE(r.status, 'Open') AS state, w.assigned_to AS assigned_to, "
    "w.hours_actual AS hours_actual, w.requisition_id AS requisition_id "
    "FROM cur_requisitions_work_order w JOIN cur_core_record r ON r.id = w.id ORDER BY r.key"
)
NEED_BY = (
    "SELECT need_by FROM cur_requisitions_labor_requisition "
    "UNION ALL SELECT need_by FROM cur_requisitions_material_requisition "
    "UNION ALL SELECT need_by FROM cur_requisitions_general_requisition "
    "UNION ALL SELECT need_by FROM cur_requisitions_scaffold_request"
)


def states(rows_: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in rows_:
        counts[str(item["state"])] = counts.get(str(item["state"]), 0) + 1
    return counts


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Run]:
    base = tmp_path_factory.mktemp("demo-project-requisitions")
    made = {
        "main": generate(base / "main.db", base / "objects-main", SECTIONS),
        "again": generate(base / "again.db", base / "objects-again", SECTIONS),
        "without": generate(base / "without.db", base / "objects-without", SOURCES),
    }
    for name, run in made.items():
        assert run.returncode == 0, f"{name} failed"
    return made


def test_counts_per_kind(runs: dict[str, Run]) -> None:
    by_type = {
        str(r["type"]): str(r["n"])
        for r in rows(
            runs["main"].db,
            "SELECT type, COUNT(*) AS n FROM cur_core_record "
            "WHERE type LIKE 'requisitions.%' AND type <> 'requisitions.WorkOrder' GROUP BY type",
        )
    }
    assert {k.split(".")[1]: int(v) for k, v in by_type.items()} == {
        "LaborRequisition": 7,
        "MaterialRequisition": 8,
        "GeneralRequisition": 5,
        "ScaffoldRequest": 4,
    }
    assert NO_MATERIALS_NOTE not in runs["main"].stdout


def test_requisitions_per_state(runs: dict[str, Run]) -> None:
    found = states(rows(runs["main"].db, REQUISITIONS))
    assert found == {
        "Requested": 7,
        "Approved": 5,
        "Scheduled": 2,
        "In progress": 1,
        "Done": 1,
        "Closed": 1,
        "Rejected": 4,
        "Cancelled": 3,
    }


def test_work_orders_per_state(runs: dict[str, Run]) -> None:
    work = rows(runs["main"].db, WORK_ORDERS)
    assert len(work) == 11  # one per approval (10 kept, 1 cancelled after approval)
    assert states(work) == {
        "Open": 5,
        "Scheduled": 2,
        "In progress": 1,
        "Done": 1,
        "Closed": 1,
        "Cancelled": 1,
    }


def test_two_open_work_orders_are_assigned_to_the_foremen(runs: dict[str, Run]) -> None:
    assigned = sorted(
        str(w["assigned_to"])
        for w in rows(runs["main"].db, WORK_ORDERS)
        if w["state"] == "Open" and w["assigned_to"] is not None
    )
    assert assigned == ["user:cbrooks", "user:pnair"]


def test_the_done_work_order_has_its_actual_hours(runs: dict[str, Run]) -> None:
    done = [w for w in rows(runs["main"].db, WORK_ORDERS) if w["state"] == "Done"]
    assert len(done) == 1
    assert str(done[0]["hours_actual"]) == "38.5"


def test_three_need_by_dates_are_overdue(runs: dict[str, Run]) -> None:
    dates = [str(r["need_by"]) for r in rows(runs["main"].db, NEED_BY)]
    assert len(dates) == 24
    assert sum(1 for d in dates if d < TODAY) == 3


def test_one_closed_work_order_closes_its_requisition(runs: dict[str, Run]) -> None:
    closed = [w for w in rows(runs["main"].db, WORK_ORDERS) if w["state"] == "Closed"]
    assert len(closed) == 1
    requisition = rows(
        runs["main"].db,
        "SELECT COALESCE(r.status, 'Requested') AS state FROM cur_core_record r "
        f"WHERE r.id = '{closed[0]['requisition_id']}'",
    )
    assert requisition[0]["state"] == "Closed"


def test_the_cancelled_requisition_was_approved_and_its_work_order_is_cancelled(
    runs: dict[str, Run],
) -> None:
    work = [w for w in rows(runs["main"].db, WORK_ORDERS) if w["state"] == "Cancelled"]
    assert len(work) == 1
    requisition = rows(
        runs["main"].db,
        "SELECT COALESCE(r.status, 'Requested') AS state FROM cur_core_record r "
        f"WHERE r.id = '{work[0]['requisition_id']}'",
    )
    assert requisition[0]["state"] == "Cancelled"


def test_one_seed_gives_the_same_counts_and_keys(runs: dict[str, Run]) -> None:
    def digest(db: Path) -> str:
        found = rows(db, REQUISITIONS) + rows(db, WORK_ORDERS)
        keys = "\n".join(f"{r['key']}|{r['state']}" for r in found)
        return hashlib.sha256(keys.encode()).hexdigest()

    main, again = runs["main"].db, runs["again"].db
    assert states(rows(main, REQUISITIONS)) == states(rows(again, REQUISITIONS))
    assert states(rows(main, WORK_ORDERS)) == states(rows(again, WORK_ORDERS))
    assert digest(main) == digest(again)


def test_without_the_section_the_other_types_do_not_move(runs: dict[str, Run]) -> None:
    def other_types(db: Path) -> dict[str, int]:
        return {
            str(r["type"]): int(str(r["n"]))
            for r in rows(
                db,
                "SELECT type, COUNT(*) AS n FROM cur_core_record "
                "WHERE type NOT LIKE 'requisitions.%' GROUP BY type",
            )
        }

    assert other_types(runs["main"].db) == other_types(runs["without"].db)
    assert rows(runs["without"].db, REQUISITIONS) == []
