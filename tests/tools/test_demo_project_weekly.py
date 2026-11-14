"""The weekly section of the demo project generator (P2-SEED-T10): five weekly plans with the
states, PPCs, outcomes and commitments the section promises, the same result on two runs, and a run
without the section leaving the other record types unchanged.

Each run builds a fresh SQLite ledger in a child process, as ``test_demo_project_release.py`` does.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import open_uow

ROOT = Path(__file__).resolve().parents[2]
BASE_SECTIONS = "core,engineering,awp,constraints,scope,release"
WEEKLY_SECTIONS = f"{BASE_SECTIONS},weekly"
PLAN_TYPE = "awp.WeeklyPlan"


def generate(db: Path, objects: Path, sections: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "TL_ENV": "dev", "PYTHONPATH": str(ROOT)}
    return subprocess.run(
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


def rows(db: Path, sql: str) -> list[dict[str, object]]:
    with open_uow(db, readonly=True) as uow:
        return [dict(r) for r in uow.conn().execute(text(sql)).mappings()]


def count(db: Path, sql: str) -> int:
    return int(next(iter(rows(db, sql)[0].values())))  # type: ignore[arg-type]


def type_counts(db: Path) -> dict[str, int]:
    return {
        str(r["type"]): int(r["n"])  # type: ignore[call-overload]
        for r in rows(db, "SELECT type, COUNT(*) AS n FROM cur_core_record GROUP BY type")
    }


def plans(db: Path) -> list[dict[str, object]]:
    return rows(
        db,
        "SELECT r.key AS key, coalesce(r.status, 'Draft') AS state, p.week_start AS week_start, "
        "p.ppc AS ppc "
        "FROM cur_core_record r JOIN cur_awp_weekly_plan p ON p.id = r.id "
        "WHERE r.type = 'awp.WeeklyPlan' ORDER BY r.key",
    )


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    base = tmp_path_factory.mktemp("demo-project-weekly")
    made = {
        "first": base / "a.db",
        "second": base / "b.db",
        "plain": base / "c.db",
    }
    first = generate(made["first"], base / "objects-a", WEEKLY_SECTIONS)
    second = generate(made["second"], base / "objects-b", WEEKLY_SECTIONS)
    plain = generate(made["plain"], base / "objects-c", BASE_SECTIONS)
    for result in (first, second, plain):
        assert result.returncode == 0, result.stderr[-2000:]
    assert "weekly:" in first.stdout and "skipped" not in first.stdout
    return made


def test_five_weekly_plans_in_three_states(runs: dict[str, Path]) -> None:
    found = plans(runs["first"])
    assert len(found) == 5, found
    states = sorted(str(p["state"]) for p in found)
    assert states == ["Closed", "Closed", "Closed", "Committed", "Draft"], states


def test_closed_weeks_carry_a_ppc_and_one_is_under_70(runs: dict[str, Path]) -> None:
    closed = [p for p in plans(runs["first"]) if p["state"] == "Closed"]
    assert len(closed) == 3
    values = [float(str(p["ppc"])) for p in closed]  # every closed week carries a PPC
    assert all(0.0 <= v <= 100.0 for v in values), values
    assert min(values) < 70.0, values


def test_week_four_is_committed_with_some_outcomes(runs: dict[str, Path]) -> None:
    week_four = [str(p["key"]) for p in plans(runs["first"]) if p["week_start"] == "2026-10-26"]
    assert len(week_four) == 1, week_four
    commitments = rows(
        runs["first"],
        "SELECT c.outcome AS outcome FROM cur_awp_week_commitment c "
        "JOIN cur_core_record r ON r.id = c.plan_id "
        f"WHERE r.key = '{week_four[0]}'",
    )
    judged = [c for c in commitments if c["outcome"] is not None]
    waiting = [c for c in commitments if c["outcome"] is None]
    assert judged, commitments
    assert waiting, commitments


def test_a_missed_outcome_has_a_reason(runs: dict[str, Path]) -> None:
    missed = count(
        runs["first"],
        "SELECT COUNT(*) FROM cur_awp_week_commitment "
        "WHERE outcome = 'missed' AND miss_reason IS NOT NULL",
    )
    assert missed >= 1


def test_same_seed_same_plans(runs: dict[str, Path]) -> None:
    def keys_and_states(db: Path) -> list[tuple[object, object]]:
        return [(p["key"], p["state"]) for p in plans(db)]

    assert keys_and_states(runs["first"]) == keys_and_states(runs["second"])


def test_without_the_section_other_types_are_unchanged(runs: dict[str, Path]) -> None:
    with_weekly = type_counts(runs["first"])
    without = type_counts(runs["plain"])
    assert without.get(PLAN_TYPE, 0) == 0
    assert with_weekly.get(PLAN_TYPE) == 5
    for record_type, n in without.items():
        assert with_weekly.get(record_type) == n, record_type
