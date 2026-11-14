"""The progress section of the demo project generator (P2-SEED-T11), with scope added inside the
constraints section: scope items on every released IWP, the released IWPs unchanged by the progress
section, earned progress that differs per started IWP, two field-completed packages, the same result
on two runs, and a run without the progress section leaving the other record types unchanged.

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
from tl_mod_awp.progress import engine

ROOT = Path(__file__).resolve().parents[2]
BASE_SECTIONS = "core,engineering,awp,constraints"
RELEASE_SECTIONS = f"{BASE_SECTIONS},release"
FULL_SECTIONS = f"{BASE_SECTIONS},release,progress"
RELEASED_STATES = ("Issued", "In progress", "Field complete")
PROJECT = "project:P200"


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


def iwp_states(db: Path) -> dict[str, str]:
    return {
        str(r["key"]): str(r["state"])
        for r in rows(
            db,
            "SELECT key, status AS state FROM cur_core_record WHERE type = 'awp.IWP'",
        )
    }


def type_counts(db: Path) -> dict[str, int]:
    return {
        str(r["type"]): int(r["n"])  # type: ignore[call-overload]
        for r in rows(db, "SELECT type, COUNT(*) AS n FROM cur_core_record GROUP BY type")
    }


def earned(db: Path) -> dict[str, str]:
    return {
        str(r["key"]): str(r["pct"])
        for r in rows(
            db,
            "SELECT r.key AS key, p.earned_pct AS pct FROM cur_awp_iwp_progress p "
            "JOIN cur_core_record r ON r.id = p.iwp_id ORDER BY r.key",
        )
    }


def scope_counts(db: Path) -> dict[str, int]:
    """The number of scope items of each IWP, by key (the engine's own reader)."""
    with open_uow(db, readonly=True) as uow:
        conn = uow.conn()
        return {
            str(r["key"]): len(engine.scope_items(conn, str(r["id"])))
            for r in rows(db, "SELECT id, key FROM cur_core_record WHERE type = 'awp.IWP'")
        }


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    base = tmp_path_factory.mktemp("demo-project-progress")
    made = {
        "first": base / "a.db",
        "second": base / "b.db",
        "plain": base / "c.db",
    }
    first = generate(made["first"], base / "objects-a", FULL_SECTIONS)
    second = generate(made["second"], base / "objects-b", FULL_SECTIONS)
    plain = generate(made["plain"], base / "objects-c", RELEASE_SECTIONS)
    for result in (first, second, plain):
        assert result.returncode == 0, result.stderr[-2000:]
    assert "progress:" in first.stdout
    return made


def test_every_released_iwp_has_scope_items(runs: dict[str, Path]) -> None:
    db = runs["first"]
    states = iwp_states(db)
    released = [k for k, s in states.items() if s in RELEASED_STATES]
    scoped = scope_counts(db)
    assert count(db, "SELECT COUNT(*) FROM cur_core_record WHERE type = 'awp.ScopeItem'") > 0
    for key in released:
        assert scoped[key] >= 3, (key, scoped[key])


def test_released_iwps_are_the_same_with_and_without_progress(
    runs: dict[str, Path],
) -> None:
    def released(db: Path) -> list[str]:
        return sorted(k for k, s in iwp_states(db).items() if s in RELEASED_STATES)

    with_sections = released(runs["first"])
    without = released(runs["plain"])
    assert with_sections == without
    assert 10 <= len(with_sections) <= 14
    field_complete = [k for k, s in iwp_states(runs["first"]).items() if s == "Field complete"]
    assert len(field_complete) == 2, field_complete
    assert count(runs["first"], "SELECT COUNT(*) FROM cur_core_constraint") == count(
        runs["plain"], "SELECT COUNT(*) FROM cur_core_constraint"
    )


def test_started_iwps_have_distinct_earned_progress(runs: dict[str, Path]) -> None:
    db = runs["first"]
    started = [k for k, s in iwp_states(db).items() if s in ("In progress", "Field complete")]
    progress = earned(db)
    values = {progress[k] for k in started if k in progress}
    assert len(started) >= 4, started
    assert len(values) >= 3, progress
    assert all(float(progress[k]) > 0 for k in started), progress


def test_same_seed_same_states_and_progress(runs: dict[str, Path]) -> None:
    assert iwp_states(runs["first"]) == iwp_states(runs["second"])
    assert earned(runs["first"]) == earned(runs["second"])


def test_without_the_sections_other_types_are_unchanged(runs: dict[str, Path]) -> None:
    with_sections = type_counts(runs["first"])
    without = type_counts(runs["plain"])
    for record_type, n in without.items():
        if record_type in ("awp.IWP", "awp.ScopeItem"):
            continue
        assert with_sections.get(record_type) == n, record_type
    assert with_sections.get("awp.IWP") == without.get("awp.IWP")
