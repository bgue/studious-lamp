"""The checklists and inspections of the quality section of the demo project (P2-INSP-T03).

Each run builds a fresh SQLite ledger in a child process (``python -m dev.seed.demo_project``), as
``test_demo_project_quality.py`` does. The generator is SQLite only (its ``--db`` is a file path),
so these tests do not run on Postgres (L-P2-WEB1-3).
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import open_uow

ROOT = Path(__file__).resolve().parents[2]
SECTIONS = "core,engineering,awp,constraints,quality"
SOURCED = "core,engineering,awp,constraints"


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


INSPECTIONS = (
    "SELECT r.id AS id, r.key AS key, COALESCE(r.status, 'Planned') AS state, i.point AS point, "
    "i.result AS result, i.recorded_by AS recorded_by, i.verified_by AS verified_by, "
    "i.reinspection_of_id AS reinspection_of_id, i.planned_on AS planned_on, "
    "i.scheduled_for AS scheduled_for, i.checklist_id AS checklist_id, "
    "i.for_iwp_id AS for_iwp_id, i.subject_id AS subject_id, s.type AS subject_type "
    "FROM cur_core_record r JOIN cur_quality_inspection i ON i.id = r.id "
    "JOIN cur_core_record s ON s.id = i.subject_id "
    "WHERE r.type = 'quality.Inspection' ORDER BY r.key"
)
CHECKLISTS = (
    "SELECT r.key AS key, r.title AS title, COALESCE(r.status, 'Draft') AS state, "
    "c.checklist_version AS version FROM cur_core_record r "
    "JOIN cur_quality_checklist c ON c.id = r.id WHERE r.type = 'quality.Checklist' ORDER BY r.key"
)


def inspections(db: Path) -> list[dict[str, object]]:
    return rows(db, INSPECTIONS)


def counts(items: list[dict[str, object]], column: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for item in items:
        found[str(item[column])] = found.get(str(item[column]), 0) + 1
    return found


def inspection_punch(db: Path) -> list[dict[str, object]]:
    """The punch items an inspection raised: those with a ``raised_against`` link to one."""
    return rows(
        db,
        "SELECT p.key AS key, i.id AS inspection_id FROM cur_links l "
        "JOIN cur_core_record p ON p.id = l.from_id "
        "JOIN cur_core_record i ON i.id = l.to_id "
        "WHERE l.relation = 'raised_against' AND i.type = 'quality.Inspection' ORDER BY p.key",
    )


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Run]:
    base = tmp_path_factory.mktemp("demo-project-inspections")
    made = {
        "main": generate(base / "main.db", base / "objects-main", SECTIONS),
        "again": generate(base / "again.db", base / "objects-again", SECTIONS),
        "without": generate(base / "without.db", base / "objects-without", SOURCED),
        "bare": generate(base / "bare.db", base / "objects-bare", "core,quality"),
    }
    for name, run in made.items():
        assert run.returncode == 0, f"{name} failed"
    return made


def test_the_counts_by_state_and_by_point(runs: dict[str, Run]) -> None:
    items = inspections(runs["main"].db)
    assert len(items) == 18
    assert counts(items, "state") == {
        "Planned": 3,
        "Scheduled": 4,
        "Done": 3,
        "Verified": 6,
        "Cancelled": 2,
    }
    assert counts(items, "point") == {"hold": 5, "witness": 4, "review": 5, "surveillance": 4}


def test_keys_have_no_gap(runs: dict[str, Run]) -> None:
    db = runs["main"].db
    assert [str(i["key"]) for i in inspections(db)] == [f"P200-INS-{n:04d}" for n in range(1, 19)]
    assert [str(c["key"]) for c in rows(db, CHECKLISTS)] == [
        f"P200-CHK-{n:04d}" for n in range(1, 5)
    ]


def test_the_flange_checklist_has_a_published_and_a_retired_version(runs: dict[str, Run]) -> None:
    lists = rows(runs["main"].db, CHECKLISTS)
    flange = [c for c in lists if c["title"] == "Flange joint make-up"]
    assert sorted((int(str(c["version"])), str(c["state"])) for c in flange) == [
        (1, "Retired"),
        (2, "Published"),
    ]
    assert counts(lists, "state") == {"Published": 3, "Retired": 1}


def test_a_verifier_is_not_the_recorder(runs: dict[str, Run]) -> None:
    verified = [i for i in inspections(runs["main"].db) if i["state"] == "Verified"]
    assert len(verified) == 6
    for item in verified:
        assert item["verified_by"] is not None
        assert item["verified_by"] != item["recorded_by"], item["key"]


def test_two_inspections_repeat_a_rejected_or_conditional_one(runs: dict[str, Run]) -> None:
    items = inspections(runs["main"].db)
    by_id = {str(i["id"]): i for i in items}
    children = [i for i in items if i["reinspection_of_id"] is not None]
    assert len(children) == 2
    for child in children:
        parent = by_id[str(child["reinspection_of_id"])]
        assert parent["result"] in ("reject", "conditional")
        assert parent["state"] == "Verified"
        assert child["result"] == "accept"
        assert parent["subject_id"] == child["subject_id"]


def test_the_subjects(runs: dict[str, Run]) -> None:
    items = inspections(runs["main"].db)
    assert counts(items, "subject_type") == {"awp.IWP": 12, "awp.CWP": 6}
    for item in items:
        if item["subject_type"] == "awp.IWP":
            assert item["for_iwp_id"] == item["subject_id"]


def test_planned_have_no_checklist_and_a_future_day(runs: dict[str, Run]) -> None:
    items = inspections(runs["main"].db)
    planned = [i for i in items if i["state"] == "Planned"]
    assert all(i["checklist_id"] is None and str(i["planned_on"]) > "2026-11-06" for i in planned)
    scheduled = [i for i in items if i["state"] == "Scheduled"]
    assert all("2026-11-06" < str(i["scheduled_for"]) <= "2026-11-20" for i in scheduled)


def test_a_failed_result_has_punch_items_and_an_accept_has_none(runs: dict[str, Run]) -> None:
    db = runs["main"].db
    items = inspections(db)
    raised: dict[str, int] = {}
    for link in inspection_punch(db):
        raised[str(link["inspection_id"])] = raised.get(str(link["inspection_id"]), 0) + 1
    failed = [i for i in items if i["result"] in ("reject", "conditional")]
    assert len(failed) == 4
    for item in failed:
        assert raised.get(str(item["id"]), 0) >= 1, item["key"]
    for item in items:
        if item["result"] == "accept" or item["result"] is None:
            assert str(item["id"]) not in raised, item["key"]
    # 2 for each reject, 1 for each conditional (the handler's rule), read from the ledger
    assert sum(raised.values()) == 6
    assert len(inspection_punch(db)) == 6


def test_the_run_prints_its_record_count(runs: dict[str, Run]) -> None:
    line = re.search(r"quality: (\d+) records", runs["main"].stdout)
    assert line is not None
    # 29 punch items, 4 checklists, 18 inspections and the punch items the inspections raised
    assert int(line.group(1)) == 29 + 4 + 18 + len(inspection_punch(runs["main"].db))


def test_two_runs_with_one_seed_give_the_same_keys_and_states(runs: dict[str, Run]) -> None:
    def fingerprint(db: Path) -> str:
        lines = [
            f"{i['key']}|{i['state']}|{i['point']}|{i['result']}|{i['planned_on']}|"
            f"{i['scheduled_for']}|{i['recorded_by']}|{i['verified_by']}"
            for i in inspections(db)
        ] + [f"{c['key']}|{c['state']}|{c['version']}" for c in rows(db, CHECKLISTS)]
        return hashlib.sha256("\n".join(lines).encode()).hexdigest()

    assert fingerprint(runs["main"].db) == fingerprint(runs["again"].db)


def test_without_quality_the_other_types_do_not_move(runs: dict[str, Run]) -> None:
    def per_type(db: Path) -> dict[str, int]:
        found = rows(db, "SELECT type, COUNT(*) AS n FROM cur_core_record GROUP BY type")
        counts_ = {str(r["type"]): int(str(r["n"])) for r in found}
        for kind in ("quality.PunchItem", "quality.Inspection", "quality.Checklist"):
            counts_.pop(kind, None)
        return counts_

    assert per_type(runs["main"].db) == per_type(runs["without"].db)
    assert inspections(runs["without"].db) == []


def test_with_no_subjects_the_punch_list_and_checklists_are_built(runs: dict[str, Run]) -> None:
    run = runs["bare"]
    assert "quality: no subjects for inspections" in run.stdout
    assert inspections(run.db) == []
    assert len(rows(run.db, CHECKLISTS)) == 4
    punch = rows(run.db, "SELECT id FROM cur_quality_punch_item")
    assert len(punch) == 29
