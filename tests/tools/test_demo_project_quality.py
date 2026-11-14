"""The quality section of the demo project (P2-PUNCH-T07): the punch list of P200 built through the
real punch commands.

Each run builds a fresh SQLite ledger in a child process (``python -m dev.seed.demo_project``; the
generator sets ``TL_SCHEMA_DIR`` for its own process, so it must not run inside the test session).
The runs are: the section on its own sources (no correspondence), the same again (one seed, one
project), the same without ``quality`` (the other types must not move), the section with the
correspondence section (restricted sources), and the section with no sources at all.
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
SOURCED = "core,engineering,awp,constraints"
NO_SOURCES_NOTE = "quality: no restricted correspondence sources"


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


#: The state of a punch item: its workflow status, where an Open item has none yet.
STATE = "COALESCE(r.status, 'Open')"
PUNCH = (
    "SELECT r.key AS key, {state} AS state, p.due_on AS due_on, p.reopen_count AS reopen_count, "
    "p.cleared_by AS cleared_by, p.verified_by AS verified_by, p.source_id AS source_id, "
    "s.key AS source_key, p.raised_by AS raised_by "
    "FROM cur_core_record r JOIN cur_quality_punch_item p ON p.id = r.id "
    "LEFT JOIN cur_core_record s ON s.id = p.source_id "
    "WHERE r.type = 'quality.PunchItem' ORDER BY r.key"
)


def punch(db: Path) -> list[dict[str, object]]:
    return rows(db, PUNCH.format(state=STATE))


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Run]:
    base = tmp_path_factory.mktemp("demo-project-quality")
    made = {
        "main": generate(base / "main.db", base / "objects-main", f"{SOURCED},quality"),
        "again": generate(base / "again.db", base / "objects-again", f"{SOURCED},quality"),
        "without": generate(base / "without.db", base / "objects-without", SOURCED),
        "correspondence": generate(
            base / "corr.db", base / "objects-corr", f"{SOURCED},correspondence,quality"
        ),
        "bare": generate(base / "bare.db", base / "objects-bare", "core,quality"),
    }
    for name, run in made.items():
        assert run.returncode == 0, f"{name} failed"
    return made


def test_the_counts_by_state(runs: dict[str, Run]) -> None:
    items = punch(runs["main"].db)
    states = [str(i["state"]) for i in items]
    assert len(items) == 29
    assert states.count("Open") == 12
    assert states.count("Cleared") == 8
    assert states.count("Verified") == 7
    assert states.count("Void") == 2


def test_every_item_has_a_key_and_there_is_no_gap(runs: dict[str, Run]) -> None:
    keys = [str(i["key"]) for i in punch(runs["main"].db)]
    assert keys == [f"P200-PUN-{n:04d}" for n in range(1, 30)]


def test_one_item_is_reopened_once(runs: dict[str, Run]) -> None:
    items = punch(runs["main"].db)
    reopened = [i for i in items if i["reopen_count"] != 0]
    assert len(reopened) == 1
    assert reopened[0]["reopen_count"] == 1
    assert reopened[0]["state"] == "Open"


def test_three_items_are_overdue(runs: dict[str, Run]) -> None:
    overdue = [
        i for i in punch(runs["main"].db) if i["state"] == "Open" and str(i["due_on"]) < TODAY
    ]
    assert len(overdue) == 3


def test_every_sourced_item_has_one_link_to_an_existing_record(runs: dict[str, Run]) -> None:
    db = runs["main"].db
    sourced = [i for i in punch(db) if i["source_id"] is not None]
    assert len(sourced) == 22  # 14 IWPs, 6 tags, 2 CWPs; the rest are free-standing
    for item in sourced:
        found = rows(
            db,
            "SELECT COUNT(*) AS n FROM cur_links l "
            "JOIN cur_core_record s ON s.id = l.to_id "
            "JOIN cur_core_record p ON p.id = l.from_id "
            f"WHERE l.relation = 'raised_against' AND p.key = '{item['key']}' "
            f"AND s.id = '{item['source_id']}'",
        )
        assert found[0]["n"] == 1, item["key"]


def test_a_verifier_is_not_the_clearer(runs: dict[str, Run]) -> None:
    verified = [i for i in punch(runs["main"].db) if i["state"] == "Verified"]
    assert len(verified) == 7
    for item in verified:
        assert item["verified_by"] is not None
        assert item["verified_by"] != item["cleared_by"], item["key"]


def test_two_runs_with_one_seed_give_the_same_items(runs: dict[str, Run]) -> None:
    def fingerprint(db: Path) -> str:
        lines = [
            f"{i['key']}|{i['state']}|{i['due_on']}|{i['reopen_count']}|{i['cleared_by']}|"
            f"{i['verified_by']}|{i['source_key']}|{i['raised_by']}"
            for i in punch(db)
        ]
        return hashlib.sha256("\n".join(lines).encode()).hexdigest()

    assert fingerprint(runs["main"].db) == fingerprint(runs["again"].db)


def test_without_quality_the_other_types_do_not_move(runs: dict[str, Run]) -> None:
    def per_type(db: Path) -> dict[str, int]:
        found = rows(db, "SELECT type, COUNT(*) AS n FROM cur_core_record GROUP BY type")
        counts = {str(r["type"]): int(str(r["n"])) for r in found}
        counts.pop("quality.PunchItem", None)
        return counts

    assert per_type(runs["main"].db) == per_type(runs["without"].db)
    assert len(punch(runs["without"].db)) == 0


def test_the_note_is_printed_when_there_is_no_correspondence(runs: dict[str, Run]) -> None:
    assert NO_SOURCES_NOTE in runs["main"].stdout
    assert "quality: 29 records" in runs["main"].stdout


def test_restricted_sources_come_from_the_correspondence_section(runs: dict[str, Run]) -> None:
    run = runs["correspondence"]
    assert NO_SOURCES_NOTE not in run.stdout
    restricted = rows(
        run.db,
        "SELECT r.key AS key FROM cur_correspondence_correspondence c "
        "JOIN cur_core_record r ON r.id = c.id WHERE c.confidentiality = 'restricted'",
    )
    assert len(restricted) == 2
    items = punch(run.db)
    raised_by_controller = [i for i in items if i["raised_by"] == "user:ipetrov"]
    assert len(raised_by_controller) == 2
    assert all(i["state"] == "Open" for i in raised_by_controller)
    assert sum(1 for i in items if i["source_id"] is not None) == 24


def test_with_no_sources_the_items_are_free_standing(runs: dict[str, Run]) -> None:
    run = runs["bare"]
    assert run.returncode == 0
    assert NO_SOURCES_NOTE in run.stdout
    items = punch(run.db)
    assert len(items) == 29
    assert all(i["source_id"] is None for i in items)
