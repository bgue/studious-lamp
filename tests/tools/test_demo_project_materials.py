"""The materials section of the demo project (P2-SEED-T02): the volumes the README sets, and that
two runs with one seed give one project.

The generator runs in a child process on fresh SQLite ledgers with ``--sections
core,engineering,awp,materials`` (the take-off lines go to the awp section's CWPs and IWPs).
The counts are the minimums of the P2-SEED README and the ticket.
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
SECTIONS = "core,engineering,awp,materials"
# documents.ProcessingJob keys are machine ids (``JOB-<ulid>``, new per extraction job), so they
# differ between two runs by design; every other record type must match.
RANDOM_KEY_TYPES = ("documents.ProcessingJob",)


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
            SECTIONS,
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


def key_hashes(db: Path) -> dict[str, str]:
    """A hash of the sorted record keys, per record type (not the machine-id types)."""
    keys: dict[str, list[str]] = {}
    for row in rows(db, "SELECT type, key FROM cur_core_record"):
        if row["type"] in RANDOM_KEY_TYPES:
            continue
        keys.setdefault(str(row["type"]), []).append(str(row["key"]))
    return {
        kind: hashlib.sha256("\n".join(sorted(found)).encode()).hexdigest()
        for kind, found in sorted(keys.items())
    }


def movement_hash(db: Path) -> str:
    """A hash of what every movement moved: kind, quantity, unit, direction and reason."""
    found = rows(
        db,
        "SELECT seq, kind, qty, uom, direction, reason FROM cur_materials_movement ORDER BY seq",
    )
    lines = [f"{r['kind']}|{r['qty']}|{r['uom']}|{r['direction']}|{r['reason']}" for r in found]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


@pytest.fixture(scope="module")
def runs(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path, subprocess.CompletedProcess[str]]:
    base = tmp_path_factory.mktemp("demo-project-materials")
    first = generate(base / "a.db", base / "objects-a")
    second = generate(base / "b.db", base / "objects-b")
    assert first.returncode == 0, first.stderr[-2000:]
    assert second.returncode == 0, second.stderr[-2000:]
    return base / "a.db", base / "b.db", first


def test_the_library_and_the_tree(
    runs: tuple[Path, Path, subprocess.CompletedProcess[str]],
) -> None:
    a, _, _ = runs
    items = count(a, "SELECT COUNT(*) FROM cur_core_record WHERE type = 'materials.ItemMaster'")
    adopted = count(a, "SELECT COUNT(*) FROM cur_core_record WHERE type = 'materials.ProjectItem'")
    locations = count(
        a, "SELECT COUNT(*) FROM cur_core_record WHERE type = 'materials.InventoryLocation'"
    )
    assert items >= 150
    assert 100 <= adopted < items  # the project adopts most of the library
    assert locations == 10  # project, L1-L3, WH1, TC1, GB1-GB4: five levels deep
    cost_codes = count(a, "SELECT COUNT(*) FROM cur_core_record WHERE type = 'cost.CostCode'")
    assert cost_codes >= 8


def test_receipts_lots_and_missing_mtrs(
    runs: tuple[Path, Path, subprocess.CompletedProcess[str]],
) -> None:
    a, _, _ = runs
    receipts = count(a, "SELECT COUNT(*) FROM cur_materials_receipt")
    assert 40 <= receipts <= 60
    not_accepted = count(
        a,
        "SELECT COUNT(*) FROM cur_core_record WHERE type = 'materials.Receipt' "
        "AND (status IS NULL OR status IN ('Received', 'Inspected'))",
    )
    # some receipts lack an MTR: Accept refused for them, so they stay Received or Inspected
    assert 8 <= not_accepted <= 12
    accepted = count(
        a,
        "SELECT COUNT(*) FROM cur_core_record WHERE type = 'materials.Receipt' "
        "AND status = 'Accepted'",
    )
    assert accepted == receipts - not_accepted
    lots = count(a, "SELECT COUNT(*) FROM cur_materials_lot")
    assert 150 <= lots <= 250
    places = count(a, "SELECT COUNT(DISTINCT location_id) FROM cur_materials_stock")
    assert places >= 4  # the lots are spread over several locations


def test_movements_of_every_kind_and_stock_never_negative(
    runs: tuple[Path, Path, subprocess.CompletedProcess[str]],
) -> None:
    a, _, _ = runs
    moved = count(a, "SELECT COUNT(*) FROM cur_materials_movement WHERE kind <> 'receive'")
    assert moved >= 300
    kinds = {str(r["kind"]) for r in rows(a, "SELECT DISTINCT kind FROM cur_materials_movement")}
    assert {"issue", "transfer", "return", "adjust", "scrap", "reserve"} <= kinds
    assert (
        count(
            a,
            "SELECT COUNT(*) FROM cur_materials_movement WHERE kind = 'issue' "
            "AND cost_code_id IS NOT NULL",
        )
        >= 50
    )
    assert (
        count(a, "SELECT COUNT(*) FROM cur_materials_stock WHERE on_hand < 0 OR available < 0") == 0
    )


def test_the_take_off_has_real_shortages(
    runs: tuple[Path, Path, subprocess.CompletedProcess[str]],
) -> None:
    a, _, _ = runs
    lines = count(a, "SELECT COUNT(*) FROM cur_materials_mto_line")
    assert lines == 150
    short = count(a, "SELECT COUNT(*) FROM cur_materials_mto_line WHERE qty > reserved_qty")
    assert short >= 20
    reserved = count(a, "SELECT COUNT(*) FROM cur_materials_mto_line WHERE reserved_qty > 0")
    assert reserved >= 1
    assigned = count(
        a, "SELECT COUNT(*) FROM cur_materials_mto_line WHERE work_package_id IS NOT NULL"
    )
    assert assigned >= 100  # most lines go to a CWP or IWP the awp section made


def test_same_seed_gives_the_same_project(
    runs: tuple[Path, Path, subprocess.CompletedProcess[str]],
) -> None:
    a, b, _ = runs
    assert key_hashes(a) == key_hashes(b)
    assert movement_hash(a) == movement_hash(b)
    assert count(a, "SELECT COUNT(*) FROM events") == count(b, "SELECT COUNT(*) FROM events")


def test_the_summary_has_a_materials_line(
    runs: tuple[Path, Path, subprocess.CompletedProcess[str]],
) -> None:
    _, _, first = runs
    assert "\nmaterials " in first.stdout
