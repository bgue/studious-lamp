"""The seeded databases the benches reuse, and the command that builds them.

    uv run python tests/bench/bench_data.py seed --dialect both --records 100000
    uv run python tests/bench/bench_data.py status
    uv run python tests/bench/bench_data.py drop --dialect both --records 100000

A dataset is one SQLite file under ``dev/data/bench/`` (git-ignored) or one Postgres database named
``tl_test_bench_<records>`` on the server ``TL_PG_URL`` names (the ``tl_test`` prefix keeps it
inside the dev-data guard of the dev MCP server). Both carry a ``tl_bench_meta`` table written
last: a database without it is a half-built seed and is thrown away. Seeding takes minutes
(SQLite) to an hour (Postgres at 100k records), which is why the benches reuse the result.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bench_gen import GENERATOR_VERSION, META_TABLE, SeedSpec, partial_path, seed_database
from sqlalchemy import text
from sqlalchemy.engine import make_url
from tl_adapters import db as adapter_db
from tl_adapters.postgres import admin

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "dev" / "data" / "bench"
PG_PREFIX = "tl_test_bench_"
DIALECTS = ("sqlite", "postgres")


@dataclass(frozen=True)
class Dataset:
    """A seeded database: where it is and what the generator reported when it was built."""

    dialect: str
    target: adapter_db.DbTarget
    spec: SeedSpec
    facts: dict[str, Any]

    @property
    def records(self) -> int:
        return self.spec.records


def pg_server() -> str:
    return os.environ.get("TL_PG_URL", admin.DEFAULT_URL)


def sqlite_path(records: int) -> Path:
    return DATA_DIR / f"sqlite-{records}.db"


def pg_database(records: int) -> str:
    return f"{PG_PREFIX}{records}"


def pg_url_for(database: str) -> str:
    """URL of ``database`` on the server; TLS is off on a loopback link (it only costs time)."""
    url = admin.database_url(pg_server(), database)
    if make_url(url).host in ("localhost", "127.0.0.1", "::1", None):
        url += ("&" if "?" in url else "?") + "sslmode=disable"
    return url


def pg_url(records: int) -> str:
    """URL of the Postgres dataset of ``records`` records."""
    return pg_url_for(pg_database(records))


def pg_available() -> bool:
    return admin.reachable(pg_server())


def _read_meta(target: adapter_db.DbTarget) -> dict[str, Any] | None:
    engine = adapter_db.make_engine(target)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT value FROM {META_TABLE} WHERE key = 'seed'")  # noqa: S608
            ).first()
    except Exception:
        return None
    finally:
        engine.dispose()
    if row is None:
        return None
    loaded: dict[str, Any] = json.loads(row[0])
    return loaded


def _write_meta(target: adapter_db.DbTarget, meta: dict[str, Any]) -> None:
    engine = adapter_db.make_engine(target)
    try:
        with adapter_db.write_tx(engine) as conn:
            conn.exec_driver_sql(
                f"CREATE TABLE IF NOT EXISTS {META_TABLE} "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.execute(
                text(f"INSERT INTO {META_TABLE} (key, value) VALUES ('seed', :v)"),  # noqa: S608
                {"v": json.dumps(meta, sort_keys=True)},
            )
    finally:
        engine.dispose()


def _matches(meta: dict[str, Any] | None, spec: SeedSpec) -> bool:
    return meta is not None and meta.get("spec") == spec.describe()


def existing(dialect: str, spec: SeedSpec) -> Dataset | None:
    """The finished dataset for ``dialect`` and ``spec``, or ``None`` when there is none."""
    if dialect == "sqlite":
        path = sqlite_path(spec.records)
        if not path.exists():
            return None
        target: adapter_db.DbTarget = path
    else:
        if not pg_available() or pg_database(spec.records) not in _pg_databases():
            return None
        target = pg_url(spec.records)
    meta = _read_meta(target)
    if not _matches(meta, spec) or meta is None:
        return None
    return Dataset(dialect, target, spec, meta["facts"])


def _pg_databases() -> set[str]:
    from tl_adapters.postgres.engine import make_engine

    engine = make_engine(admin.database_url(pg_server(), "postgres"))
    try:
        with engine.connect() as conn:
            return {str(r[0]) for r in conn.exec_driver_sql("SELECT datname FROM pg_database")}
    finally:
        engine.dispose()


def drop(dialect: str, records: int) -> None:
    if dialect == "sqlite":
        for suffix in ("", "-wal", "-shm", ".partial", ".partial-wal", ".partial-shm"):
            path = sqlite_path(records)
            Path(str(path) + suffix).unlink(missing_ok=True)
    elif pg_available() and pg_database(records) in _pg_databases():
        admin.drop_database(pg_server(), pg_database(records))


def seed(dialect: str, spec: SeedSpec, *, force: bool = False, quiet: bool = False) -> Dataset:
    """Build the dataset unless a finished one exists. Returns it."""
    found = None if force else existing(dialect, spec)
    if found is not None:
        return found
    drop(dialect, spec.records)
    started = time.perf_counter()
    last = [started]

    def progress(done: int) -> None:
        now = time.perf_counter()
        if not quiet and now - last[0] >= 30:
            last[0] = now
            rate = done / (now - started)
            eta = (spec.records - done) / rate
            print(
                f"  {dialect}: {done}/{spec.records} records, {rate:.0f}/s, "
                f"~{eta / 60:.0f} min left"
            )

    if dialect == "sqlite":
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        building = partial_path(sqlite_path(spec.records))
        facts = seed_database(building, spec, on_progress=progress)
        _checkpoint(building)
        building.replace(sqlite_path(spec.records))
        target: adapter_db.DbTarget = sqlite_path(spec.records)
    else:
        if not pg_available():
            raise RuntimeError("Postgres is not reachable at TL_PG_URL")
        admin.create_database(pg_server(), pg_database(spec.records))
        target = pg_url(spec.records)
        facts = seed_database(target, spec, on_progress=progress)
    seconds = round(time.perf_counter() - started, 1)
    _write_meta(target, {"spec": spec.describe(), "facts": facts, "seed_seconds": seconds})
    return Dataset(dialect, target, spec, facts)


def _checkpoint(path: Path) -> None:
    engine = adapter_db.make_engine(path)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        engine.dispose()
    for suffix in ("-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and inspect the bench datasets.")
    parser.add_argument("action", choices=("seed", "status", "drop"))
    parser.add_argument(
        "--dialect",
        choices=(*DIALECTS, "both"),
        default=None,
        help="default: TL_BENCH_DIALECTS (a comma-separated list), else both",
    )
    parser.add_argument("--records", type=int, default=100_000)
    parser.add_argument("--force", action="store_true")
    ns = parser.parse_args(argv)
    spec = SeedSpec(records=ns.records)
    if ns.dialect is None:
        chosen = os.environ.get("TL_BENCH_DIALECTS", "")
        dialects = tuple(d.strip() for d in chosen.split(",") if d.strip()) or DIALECTS
    else:
        dialects = DIALECTS if ns.dialect == "both" else (ns.dialect,)
    for dialect in dialects:
        if ns.action == "status":
            found = existing(dialect, spec)
            print(f"{dialect:9} {ns.records:>8} records: {'ready' if found else 'missing'}")
            if found:
                print(f"          {found.facts}")
        elif ns.action == "drop":
            drop(dialect, ns.records)
            print(f"{dialect}: dropped")
        else:
            started = time.perf_counter()
            dataset = seed(dialect, spec, force=ns.force)
            print(
                f"{dialect}: {dataset.facts['events']} events, "
                f"generator v{GENERATOR_VERSION}, {time.perf_counter() - started:.0f}s"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
