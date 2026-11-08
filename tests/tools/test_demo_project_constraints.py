"""The constraints section of the demo project generator (P2-SEED-T06): counts, every state,
readiness that differs across IWPs, and the same constraint keys on two runs.

Each run builds a fresh SQLite ledger in a child process (``--sections core,engineering,awp,
constraints``), as ``test_demo_project_awp.py`` does.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core.constraints.commands import CATEGORIES

ROOT = Path(__file__).resolve().parents[2]
TODAY = "2026-11-06"
OPEN = "coalesce(r.status, 'Open') IN ('Open', 'Assigned')"
JOIN = "FROM cur_core_constraint c JOIN cur_core_record r ON r.id = c.id"


def generate(db: Path, objects: Path) -> subprocess.CompletedProcess[str]:
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
            "core,engineering,awp,constraints",
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


def constraint_keys(db: Path) -> str:
    keys = sorted(
        str(r["key"])
        for r in rows(db, "SELECT key FROM cur_core_record WHERE type = 'core.Constraint'")
    )
    return hashlib.sha256("\n".join(keys).encode()).hexdigest()


def on_type(db: Path, record_type: str) -> int:
    return count(
        db,
        f"SELECT COUNT(DISTINCT c.subject_id) {JOIN} JOIN cur_core_record s ON s.id = c.subject_id "
        f"WHERE s.type = '{record_type}'",
    )


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    base = tmp_path_factory.mktemp("demo-project-constraints")
    first = generate(base / "a.db", base / "objects-a")
    second = generate(base / "b.db", base / "objects-b")
    assert first.returncode == 0, first.stderr[-2000:]
    assert second.returncode == 0, second.stderr[-2000:]
    assert "constraints:" in first.stdout and "skipped" not in first.stdout
    return base / "a.db", base / "b.db"


def test_counts_in_range(runs: tuple[Path, Path]) -> None:
    db = runs[0]
    assert 36 <= count(db, "SELECT COUNT(*) FROM cur_core_constraint") <= 50
    assert on_type(db, "awp.IWP") >= 15
    assert on_type(db, "awp.CWP") >= 10


def test_categories_are_real_and_mixed(runs: tuple[Path, Path]) -> None:
    found = {
        str(r["category"])
        for r in rows(runs[0], "SELECT DISTINCT category FROM cur_core_constraint")
    }
    assert found <= set(CATEGORIES)
    assert len(found) >= 6


def test_every_state_is_present(runs: tuple[Path, Path]) -> None:
    db = runs[0]
    states = {
        str(r["state"]): int(r["n"])  # type: ignore[call-overload]
        for r in rows(
            db, f"SELECT coalesce(r.status, 'Open') AS state, COUNT(*) AS n {JOIN} GROUP BY 1"
        )
    }
    for state in ("Open", "Assigned", "Cleared", "Withdrawn"):
        assert states.get(state, 0) >= 1, states
    overdue = count(db, f"SELECT COUNT(*) {JOIN} WHERE {OPEN} AND c.due_at < '{TODAY}'")
    assert overdue >= 3
    # a check-raised constraint, cleared by a person
    assert (
        count(db, f"SELECT COUNT(*) {JOIN} WHERE c.source = 'check' AND r.status = 'Cleared'") >= 1
    )


def test_envelope_time_is_never_a_constraint_date(runs: tuple[Path, Path]) -> None:
    assert (
        count(runs[0], "SELECT COUNT(*) FROM cur_core_constraint WHERE effective_at IS NOT NULL")
        == 0
    )


def test_blocking_constraints_split_readiness(runs: tuple[Path, Path]) -> None:
    db = runs[0]
    not_ready = count(
        db,
        "SELECT COUNT(*) FROM cur_awp_readiness g WHERE g.ready = 0 AND EXISTS ("
        f"SELECT 1 {JOIN} WHERE c.subject_id = g.iwp_id AND c.phase = 'ready' "
        f"AND c.severity = 'blocking' AND {OPEN})",
    )
    ready = count(db, "SELECT COUNT(*) FROM cur_awp_readiness WHERE ready = 1")
    assert not_ready >= 3
    assert ready >= 3
    # every not-ready IWP is not ready because of a blocking constraint, none for another reason
    assert not_ready == count(db, "SELECT COUNT(*) FROM cur_awp_readiness WHERE ready = 0")


def test_same_seed_same_constraint_keys(runs: tuple[Path, Path]) -> None:
    first, second = runs
    assert count(first, "SELECT COUNT(*) FROM cur_core_constraint") == count(
        second, "SELECT COUNT(*) FROM cur_core_constraint"
    )
    assert constraint_keys(first) == constraint_keys(second)
