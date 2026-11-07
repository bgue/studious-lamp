"""The demo project generator (P2-SEED-S1): two runs with one seed give one project.

Each run builds a fresh SQLite ledger in a child process (``python -m dev.seed.demo_project``; the
generator sets ``TL_SCHEMA_DIR`` for its own process, so it must not run inside the test session).
The runs must agree on the keys of every record type, and the counts must reach the minimums the
P2-SEED README sets for the sections built so far.
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
TODAY = "2026-11-06"


def generate(db: Path, objects: Path, *extra: str) -> subprocess.CompletedProcess[str]:
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
            *extra,
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


def key_hashes(db: Path) -> dict[str, str]:
    """A hash of the sorted record keys, per record type."""
    keys: dict[str, list[str]] = {}
    for row in rows(db, "SELECT type, key FROM cur_core_record"):
        keys.setdefault(str(row["type"]), []).append(str(row["key"]))
    return {
        kind: hashlib.sha256("\n".join(sorted(found)).encode()).hexdigest()
        for kind, found in sorted(keys.items())
    }


def count(db: Path, sql: str) -> int:
    return int(next(iter(rows(db, sql)[0].values())))  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def runs(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path, subprocess.CompletedProcess[str]]:
    base = tmp_path_factory.mktemp("demo-project")
    first = generate(base / "a.db", base / "objects-a")
    second = generate(base / "b.db", base / "objects-b")
    assert first.returncode == 0, first.stderr[-2000:]
    assert second.returncode == 0, second.stderr[-2000:]
    return base / "a.db", base / "b.db", first


def test_same_seed_gives_the_same_keys(
    runs: tuple[Path, Path, subprocess.CompletedProcess[str]],
) -> None:
    a, b, _ = runs
    assert key_hashes(a) == key_hashes(b)
    assert count(a, "SELECT COUNT(*) FROM cur_core_record") == count(
        b, "SELECT COUNT(*) FROM cur_core_record"
    )


def test_volumes_reach_the_readme_minimums(
    runs: tuple[Path, Path, subprocess.CompletedProcess[str]],
) -> None:
    a, _, _ = runs
    tags = count(a, "SELECT COUNT(*) FROM cur_core_record WHERE type = 'engineering.Tag'")
    documents = count(a, "SELECT COUNT(*) FROM cur_core_record WHERE type = 'documents.Document'")
    revisions = count(a, "SELECT COUNT(*) FROM cur_core_record WHERE type = 'documents.Revision'")
    superseded = count(
        a,
        "SELECT COUNT(*) FROM cur_core_record WHERE type = 'documents.Document' "
        "AND status = 'Superseded'",
    )
    items = count(
        a,
        "SELECT COUNT(*) FROM cur_core_record WHERE type IN "
        "('correspondence.Correspondence', 'correspondence.TechnicalItem')",
    )
    people = count(a, "SELECT COUNT(*) FROM cur_account")
    assert tags >= 300
    assert documents >= 80
    assert revisions > documents
    assert superseded >= 1
    assert items >= 30
    assert people == 9


def test_some_correspondence_is_overdue_on_the_fixed_today(
    runs: tuple[Path, Path, subprocess.CompletedProcess[str]],
) -> None:
    a, _, _ = runs
    overdue = count(
        a,
        "SELECT COUNT(*) FROM cur_correspondence_response_clock "
        f"WHERE state = 'expired' AND due_on < '{TODAY}'",
    )
    assert overdue >= 1


def test_the_summary_names_every_section(
    runs: tuple[Path, Path, subprocess.CompletedProcess[str]],
) -> None:
    _, _, first = runs
    for name in (
        "core",
        "engineering",
        "documents",
        "correspondence",
        "awp",
        "materials",
        "quality",
    ):
        assert f"\n{name} " in first.stdout
    assert "total" in first.stdout


def test_a_ledger_that_holds_p200_is_refused(
    runs: tuple[Path, Path, subprocess.CompletedProcess[str]], tmp_path: Path
) -> None:
    a, _, _ = runs
    again = generate(a, tmp_path / "objects")
    assert again.returncode == 1
    assert "already holds project P200" in again.stderr


def test_an_unknown_section_is_refused(tmp_path: Path) -> None:
    refused = generate(tmp_path / "x.db", tmp_path / "objects", "--sections", "plumbing")
    assert refused.returncode == 1
    assert "unknown section plumbing" in refused.stderr
