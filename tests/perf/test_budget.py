"""V3-P1: the speed budget: each module list view answers in under 1 s on the full demo ledger.

The ledger is the whole demo project (``python -m dev.seed.demo_project``, all sections, about four
minutes), built once and cached under ``.gate/demo-full/<hash of dev/seed/** and schema/**>.db``:
built beside the cache under a file lock, then renamed into place, so two runs never build
twice and a half-built ledger is never read. Each list view is timed as the lowest viewer
(``user:treyes``, no clearance) and as a full viewer (``user:mokafor``, the administrator),
median of five calls. Run it by path (``just gate tests/perf``); the whole-suite gate leaves it out.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_tui.embedded import EmbeddedClient

pytestmark = pytest.mark.perf  # skipped unless named by path or TL_PERF=1 (conftest.py)

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "P200"
LOW = "user:treyes"
FULL = "user:mokafor"
BUDGET_SECONDS = 1.0
REPEATS = 5
SCHEMA_DIR = ROOT / "dev" / "data" / "demo-project-schema"
TOP = 5

# name -> call: the list view of each module, as the embedded client serves it.
Call = Callable[[EmbeddedClient], Any]
VIEWS: dict[str, Call] = {
    "records": lambda c: c.list_records(f"project:{PROJECT}"),
    "tags": lambda c: c.list_tags(PROJECT),
    "documents": lambda c: c.list_documents(PROJECT),
    "transmittals": lambda c: c.list_transmittals(PROJECT),
    "correspondence": lambda c: c.list_correspondence(PROJECT),
    "rfis": lambda c: c.list_rfis(PROJECT),
    "commercial": lambda c: c.list_commercial(PROJECT),
    "threads": lambda c: c.list_threads(PROJECT),
    "clocks": lambda c: c.list_clocks(PROJECT),
    "punch": lambda c: c.list_punch_items(PROJECT),
    "inspections": lambda c: c.list_inspections(PROJECT),
    "checklists": lambda c: c.list_checklists(PROJECT),
    "scaffolds": lambda c: c.list_scaffolds(PROJECT),
    "permits": lambda c: c.list_permits(PROJECT),
    "isolations": lambda c: c.list_isolations(PROJECT),
    "cwas": lambda c: c.list_cwas(PROJECT),
    "cwps": lambda c: c.list_cwps(PROJECT),
    "iwps": lambda c: c.list_iwps(PROJECT),
    "constraints": lambda c: c.list_constraints(PROJECT),
    "requisitions": lambda c: c.list_requisitions(PROJECT),
    "work_orders": lambda c: c.list_work_orders(PROJECT),
    "materials_stock": lambda c: c.list_materials_stock(PROJECT),
    "materials_items": lambda c: c.list_materials_items(project=PROJECT),
    "weekly_plans": lambda c: c.list_weekly_plans(PROJECT),
}


def ledger_key() -> str:
    """A hash of the generator, the schema and the package sources (``packages/*/src``, which the
    generator runs): a change to any of them builds a new ledger."""
    digest = hashlib.sha256()
    tops = [ROOT / "dev/seed", ROOT / "schema", ROOT / "dev/data/demo-project-schema"]
    tops += sorted(ROOT.glob("packages/*/src")) + sorted(ROOT.glob("packages/tl-modules/*/src"))
    for top in tops:
        for path in sorted(top.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                digest.update(str(path.relative_to(ROOT)).encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def build_cached_ledger(cache_dir: Path, key: str) -> Path:
    """The cached full ledger for ``key``; built under a file lock and renamed into place."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    final = cache_dir / f"{key}.db"
    if final.exists():
        return final
    with open(cache_dir / f"{key}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if final.exists():  # another run built it while this one waited
            return final
        partial = cache_dir / f"{key}.{os.getpid()}.partial"
        for old in cache_dir.glob(f"{key}.*.partial*"):
            old.unlink(missing_ok=True)
        env = {**os.environ, "TL_SCHEMA_DIR": str(SCHEMA_DIR)}
        done = subprocess.run(
            [sys.executable, "-m", "dev.seed.demo_project", "--db", str(partial)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode != 0:
            partial.unlink(missing_ok=True)
            raise RuntimeError(
                f"demo project build failed:\n{done.stdout[-800:]}{done.stderr[-800:]}"
            )
        conn = sqlite3.connect(partial)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        for side in ("-wal", "-shm"):
            Path(f"{partial}{side}").unlink(missing_ok=True)
        os.replace(partial, final)  # atomic: a reader sees the whole ledger or none
    return final


@pytest.fixture(scope="session")
def ledger(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """A private copy of the cached ledger (a read opens WAL side files; the cache stays clean)."""
    cached = build_cached_ledger(ROOT / ".gate" / "demo-full", ledger_key())
    mine = tmp_path_factory.mktemp("perf") / "demo-full.db"
    shutil.copyfile(cached, mine)
    old = os.environ.get("TL_SCHEMA_DIR")
    os.environ["TL_SCHEMA_DIR"] = str(SCHEMA_DIR)
    try:
        yield mine
    finally:
        if old is None:
            os.environ.pop("TL_SCHEMA_DIR", None)
        else:
            os.environ["TL_SCHEMA_DIR"] = old


def median_seconds(call: Call, client: EmbeddedClient) -> float:
    took: list[float] = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        call(client)
        took.append(time.perf_counter() - start)
    return statistics.median(took)


def test_every_list_view_is_under_a_second(ledger: Path, pytestconfig: pytest.Config) -> None:
    factory = SqliteUowFactory(str(ledger))
    clients = {who: EmbeddedClient(factory, actor=who) for who in (LOW, FULL)}
    results: list[tuple[float, str, str]] = []
    slow: list[str] = []
    for who, client in clients.items():
        for name, call in VIEWS.items():
            seconds = median_seconds(call, client)
            if seconds > BUDGET_SECONDS:  # a busy box can slow one run: measure once more
                again = median_seconds(call, client)
                if again > BUDGET_SECONDS:
                    slow.append(f"{name} as {who}: {seconds:.2f} s, then {again:.2f} s")
                else:
                    print(f"{name} as {who}: {seconds:.2f} s, then {again:.2f} s (passes)")
                seconds = min(seconds, again)
            results.append((seconds, name, who))
    results.sort(reverse=True)
    lines = [f"  {seconds:6.3f} s  {name}  {who}" for seconds, name, who in results[:TOP]]
    report = (
        f"slowest {TOP} of {len(results)} list views (budget {BUDGET_SECONDS} s):\n"
        + "\n".join(lines)
    )
    terminal = pytestconfig.pluginmanager.get_plugin("terminalreporter")
    if terminal is not None:
        terminal.write_line("")
        terminal.write_line(report)
    (ROOT / ".gate").mkdir(exist_ok=True)
    (ROOT / ".gate" / "perf-top5.txt").write_text(report + "\n")
    assert not slow, "over the 1 s budget twice:\n" + "\n".join(slow) + "\n" + report
