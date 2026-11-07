"""The awp section of the demo project generator (P2-SEED-T01): the counts the README sets, and the
same CWP keys on two runs.

Each run builds a fresh SQLite ledger in a child process (``python -m dev.seed.demo_project`` with
``--sections core,engineering,awp``), as ``test_demo_project.py`` does.
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

ROOT = Path(__file__).resolve().parents[2]


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
            "core,engineering,awp",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def rows(db: Path, sql: str) -> list[dict[str, object]]:
    with open_uow(db, readonly=True) as uow:
        return [dict(r) for r in uow.conn().execute(text(sql)).mappings()]


def count(db: Path, sql: str) -> int:
    return int(next(iter(rows(db, sql)[0].values())))  # type: ignore[arg-type]


def cwp_keys(db: Path) -> str:
    """A hash of the sorted CWP keys of one run."""
    keys = sorted(
        str(r["key"]) for r in rows(db, "SELECT key FROM cur_core_record WHERE type = 'awp.CWP'")
    )
    return hashlib.sha256("\n".join(keys).encode()).hexdigest()


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    base = tmp_path_factory.mktemp("demo-project-awp")
    first = generate(base / "a.db", base / "objects-a")
    second = generate(base / "b.db", base / "objects-b")
    assert first.returncode == 0, first.stderr[-2000:]
    assert second.returncode == 0, second.stderr[-2000:]
    assert "awp:" in first.stdout
    return base / "a.db", base / "b.db"


def test_two_runs_give_the_same_cwp_keys(runs: tuple[Path, Path]) -> None:
    a, b = runs
    keys = count(a, "SELECT COUNT(*) FROM cur_core_record WHERE type = 'awp.CWP'")
    assert keys > 0
    assert cwp_keys(a) == cwp_keys(b)


def test_wbs_has_about_a_hundred_nodes_over_five_levels(runs: tuple[Path, Path]) -> None:
    a, _ = runs
    nodes = count(a, "SELECT COUNT(*) FROM cur_awp_wbs_node WHERE retired = 0")
    levels = count(a, "SELECT MAX(depth) + 1 FROM cur_awp_wbs_node WHERE retired = 0")
    assert 90 <= nodes <= 115, nodes
    assert levels == 5, levels


def test_cost_codes_sit_on_leaf_nodes_only(runs: tuple[Path, Path]) -> None:
    a, _ = runs
    parents = count(
        a,
        "SELECT COUNT(*) FROM cur_awp_wbs_node n WHERE EXISTS "
        "(SELECT 1 FROM cur_awp_wbs_node c WHERE c.parent_id = n.id)",
    )
    leaves = count(
        a,
        "SELECT COUNT(*) FROM cur_awp_wbs_node n WHERE NOT EXISTS "
        "(SELECT 1 FROM cur_awp_wbs_node c WHERE c.parent_id = n.id)",
    )
    coded = count(
        a,
        "SELECT COUNT(DISTINCT node_id) FROM cur_awp_wbs_allocation",
    )
    off_leaf = count(
        a,
        "SELECT COUNT(*) FROM cur_awp_wbs_allocation al WHERE EXISTS "
        "(SELECT 1 FROM cur_awp_wbs_node c WHERE c.parent_id = al.node_id)",
    )
    assert parents > 0 and leaves > parents
    assert coded == leaves
    assert off_leaf == 0


def test_twelve_areas_and_a_path_at_version_two(runs: tuple[Path, Path]) -> None:
    a, _ = runs
    assert count(a, "SELECT COUNT(*) FROM cur_awp_cwa WHERE retired = 0") == 12
    assert count(a, "SELECT current_version FROM cur_awp_path") == 2
    moved = count(
        a,
        "SELECT COUNT(*) FROM cur_awp_path_step WHERE version = 2 AND reason_code = 'Procurement'",
    )
    assert moved == 1


def test_work_packages_are_in_mixed_states_and_allocated_to_100_percent(
    runs: tuple[Path, Path],
) -> None:
    a, _ = runs
    total = count(a, "SELECT COUNT(*) FROM cur_core_record WHERE type = 'awp.CWP'")
    assert 40 <= total <= 60, total
    planned = count(
        a,
        "SELECT COUNT(*) FROM cur_core_record WHERE type = 'awp.CWP' AND status IS NULL",
    )
    released = count(
        a,
        "SELECT COUNT(*) FROM cur_core_record WHERE type = 'awp.CWP' "
        "AND status = 'Released for IWP development'",
    )
    closed = count(
        a, "SELECT COUNT(*) FROM cur_core_record WHERE type = 'awp.CWP' AND status = 'Closed'"
    )
    assert planned >= 1 and released >= 10 and closed >= 1
    assert released > planned and released > closed
    off_100 = count(
        a,
        "SELECT COUNT(*) FROM (SELECT cwp_id FROM cur_awp_cwp_allocation "
        "GROUP BY cwp_id HAVING ABS(SUM(CAST(percent AS REAL)) - 100) > 0.001)",
    )
    assert off_100 == 0
    with_budget = count(a, "SELECT COUNT(*) FROM cur_awp_cwp WHERE budget_hours IS NOT NULL")
    assert with_budget == total


def test_packages_are_eight_to_twelve_with_two_constraint_sources(
    runs: tuple[Path, Path],
) -> None:
    a, _ = runs
    refs = count(a, "SELECT COUNT(*) FROM cur_awp_ewp_ref") + count(
        a, "SELECT COUNT(*) FROM cur_awp_pwp_ref"
    )
    assert 8 <= refs <= 12, refs
    sources = count(a, "SELECT COUNT(*) FROM cur_awp_ewp_ref WHERE constraint_source = 1") + count(
        a, "SELECT COUNT(*) FROM cur_awp_pwp_ref WHERE constraint_source = 1"
    )
    assert sources == 2
    linked = count(
        a,
        "SELECT COUNT(*) FROM cur_links WHERE relation = 'requires' AND status <> 'retracted'",
    )
    assert linked >= 2
