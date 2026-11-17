"""The scaffold section of the demo project (P2-I4B-T11a): scaffolds built through the real
scaffold commands from the approved scaffold requisitions of P200.

Each run builds a fresh SQLite ledger in a child process (the generator sets ``TL_SCHEMA_DIR`` for
its own process). Runs: the section after requisitions, the same again, the same without
``scaffold`` and the section with no requisitions at all.
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
BASE = "core,engineering,awp,constraints,requisitions"
NOTE = "scaffold: no approved scaffold requisitions"


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


SCAFFOLDS = (
    "SELECT r.key AS key, r.status AS state, s.tag AS tag, s.request_id AS request_id "
    "FROM cur_core_record r JOIN cur_scaffold_scaffold s ON s.id = r.id "
    "WHERE r.type = 'scaffold.Scaffold' ORDER BY r.key"
)
APPROVED = (
    "SELECT COUNT(*) AS n FROM cur_core_record WHERE type = 'requisitions.ScaffoldRequest' "
    "AND status IN ('Approved', 'Scheduled', 'In progress', 'Done', 'Closed')"
)
ORDER = ("Designed", "Erecting", "In Use", "Modify")


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Run]:
    base = tmp_path_factory.mktemp("demo-project-scaffold")
    made = {
        "main": generate(base / "main.db", base / "o-main", f"{BASE},scaffold"),
        "again": generate(base / "again.db", base / "o-again", f"{BASE},scaffold"),
        "without": generate(base / "without.db", base / "o-without", BASE),
        "bare": generate(base / "bare.db", base / "o-bare", "core,scaffold"),
    }
    for name, run in made.items():
        assert run.returncode == 0, f"{name} failed: {run.stdout[-500:]}"
    return made


def test_one_scaffold_per_approved_request_in_state_order(runs: dict[str, Run]) -> None:
    db = runs["main"].db
    found = rows(db, SCAFFOLDS)
    approved = int(str(rows(db, APPROVED)[0]["n"]))
    assert approved >= 1
    assert len(found) == min(approved, 4)
    assert [str(s["state"]) for s in found] == list(ORDER[: len(found)])
    assert len({s["request_id"] for s in found}) == len(found)
    print("scaffold states:", [str(s["state"]) for s in found])


def test_tags_follow_the_states(runs: dict[str, Run]) -> None:
    for s in rows(runs["main"].db, SCAFFOLDS):
        expected = {"In Use": "green", "Modify": "red"}.get(str(s["state"]))
        assert s["tag"] == expected, s["key"]


def test_the_same_seed_gives_the_same_ledger_hash(runs: dict[str, Run]) -> None:
    def fingerprint(db: Path) -> str:
        found = rows(
            db,
            "SELECT stream_version, event_type, actor, recorded_at FROM events "
            "WHERE stream_type LIKE 'scaffold.%' ORDER BY seq",
        )
        assert found
        return hashlib.sha256(repr(found).encode()).hexdigest()

    assert fingerprint(runs["main"].db) == fingerprint(runs["again"].db)


def test_without_scaffold_the_other_types_do_not_move(runs: dict[str, Run]) -> None:
    def per_type(db: Path) -> dict[str, int]:
        found = rows(db, "SELECT type, COUNT(*) AS n FROM cur_core_record GROUP BY type")
        counts = {str(r["type"]): int(str(r["n"])) for r in found}
        counts.pop("scaffold.Scaffold", None)
        return counts

    assert per_type(runs["main"].db) == per_type(runs["without"].db)
    assert rows(runs["without"].db, SCAFFOLDS) == []


def test_without_requisitions_the_section_says_so(runs: dict[str, Run]) -> None:
    assert NOTE in runs["bare"].stdout
    assert rows(runs["bare"].db, SCAFFOLDS) == []
