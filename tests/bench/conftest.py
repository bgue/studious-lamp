"""Fixtures for the benches: the seeded datasets and the recorder that writes the results file.

Settings come from the environment, so ``just bench`` and ``just demo P0-I8-D`` share one code path:

* ``TL_BENCH_RECORDS`` (default 100000): records in the dataset;
* ``TL_BENCH_DIALECTS`` (default ``sqlite,postgres``);
* ``TL_BENCH_ROUNDS`` and ``TL_BENCH_SAMPLES``: rounds and timed calls per round (3 and 20);
* ``TL_BENCH_LABEL``: suffix of the results file name.

A dataset is built by ``tests/bench/bench_data.py seed`` (``just bench-seed``) and only reused here:
a bench that finds none fails and says so, instead of spending an hour seeding by surprise.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench_data import Dataset, SeedSpec, existing, pg_available  # noqa: E402
from bench_env import DIALECTS, LABEL, REBUILD_RECORDS, RECORDS  # noqa: E402
from bench_stats import Recorder  # noqa: E402


@pytest.fixture(scope="session")
def recorder() -> Iterator[Recorder]:
    rec = Recorder(label=f"{LABEL}-{RECORDS}")
    yield rec
    path = rec.write()
    if path is not None:
        print(f"\nbench results: {path}")


@pytest.fixture(scope="session", params=DIALECTS)
def dataset(request: pytest.FixtureRequest) -> Dataset:
    dialect: str = request.param
    if dialect == "postgres" and not pg_available():
        pytest.fail("Postgres is not reachable at TL_PG_URL; set TL_BENCH_DIALECTS=sqlite")
    found = existing(dialect, SeedSpec(records=RECORDS))
    if found is None:
        pytest.fail(
            f"no seeded {dialect} dataset of {RECORDS} records; "
            f"run `just bench-seed` (TL_BENCH_RECORDS={RECORDS})"
        )
    return found


@pytest.fixture(scope="session", params=DIALECTS)
def small_dataset(request: pytest.FixtureRequest) -> Dataset:
    """The smaller dataset the repeated rebuilds run on (``TL_BENCH_REBUILD_RECORDS``, 10000)."""
    dialect: str = request.param
    if dialect == "postgres" and not pg_available():
        pytest.fail("Postgres is not reachable at TL_PG_URL; set TL_BENCH_DIALECTS=sqlite")
    found = existing(dialect, SeedSpec(records=REBUILD_RECORDS))
    if found is None:
        pytest.fail(
            f"no seeded {dialect} dataset of {REBUILD_RECORDS} records; run `just bench-seed`"
        )
    return found
