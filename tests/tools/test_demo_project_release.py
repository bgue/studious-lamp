"""The release section of the demo project generator (P2-SEED-T09): issued and started IWPs, the
constraint counts of the constraints section still holding, the same result on two runs, and a run
without the section leaving the other record types unchanged.

Each run builds a fresh SQLite ledger in a child process, as ``test_demo_project_constraints.py``
does.
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
BASE_SECTIONS = "core,engineering,awp,constraints"
RELEASE_SECTIONS = f"{BASE_SECTIONS},release"
ISSUED_STATES = ("Issued", "In progress")


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


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    base = tmp_path_factory.mktemp("demo-project-release")
    made = {
        "first": base / "a.db",
        "second": base / "b.db",
        "plain": base / "c.db",
    }
    first = generate(made["first"], base / "objects-a", RELEASE_SECTIONS)
    second = generate(made["second"], base / "objects-b", RELEASE_SECTIONS)
    plain = generate(made["plain"], base / "objects-c", BASE_SECTIONS)
    for result in (first, second, plain):
        assert result.returncode == 0, result.stderr[-2000:]
    assert "release:" in first.stdout and "skipped" not in first.stdout
    return made


def test_issued_and_in_progress_counts(runs: dict[str, Path]) -> None:
    states = iwp_states(runs["first"])
    issued = [k for k, s in states.items() if s in ISSUED_STATES]
    started = [k for k, s in states.items() if s == "In progress"]
    assert 10 <= len(issued) <= 14, states
    assert len(started) >= 3, states
    assert len(issued) - len(started) >= 1  # some issued but not started
    not_ready = [k for k, s in states.items() if s not in (*ISSUED_STATES, "Ready")]
    assert len(not_ready) >= 4, states


def test_every_issued_iwp_has_two_signatures(runs: dict[str, Path]) -> None:
    issued = [k for k, s in iwp_states(runs["first"]).items() if s in ISSUED_STATES]
    signed = count(runs["first"], "SELECT COUNT(*) FROM events WHERE event_type = 'IWP.SignedOff'")
    assert signed >= 2 * len(issued)


def test_constraint_counts_still_hold(runs: dict[str, Path]) -> None:
    db = runs["first"]
    assert 36 <= count(db, "SELECT COUNT(*) FROM cur_core_constraint") <= 50
    assert count(db, "SELECT COUNT(*) FROM cur_core_constraint WHERE effective_at IS NOT NULL") == 0
    assert count(db, "SELECT COUNT(*) FROM cur_core_constraint") == count(
        runs["plain"], "SELECT COUNT(*) FROM cur_core_constraint"
    )


def test_same_seed_same_issued_iwps(runs: dict[str, Path]) -> None:
    def issued(db: Path) -> list[str]:
        return sorted(k for k, s in iwp_states(db).items() if s in ISSUED_STATES)

    assert issued(runs["first"]) == issued(runs["second"])
    assert iwp_states(runs["first"]) == iwp_states(runs["second"])


def test_without_the_section_other_types_are_unchanged(runs: dict[str, Path]) -> None:
    with_release = type_counts(runs["first"])
    without = type_counts(runs["plain"])
    for record_type, n in without.items():
        if record_type == "awp.IWP":
            continue
        assert with_release.get(record_type) == n, record_type
    assert with_release.get("awp.IWP") == without.get("awp.IWP")
