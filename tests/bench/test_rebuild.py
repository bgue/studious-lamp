"""Projection rebuild time (brief §15 "Rebuild", risk R1).

``rebuild_projections`` resets the projectors and replays the whole ledger into them in one
transaction. A rebuild is idempotent, so it runs on the cached seed itself; each test checks that
the tables hold the same number of rows afterwards.

* ``test_full_rebuild_small``: the full rebuild of the small dataset (``TL_BENCH_REBUILD_RECORDS``,
  default 10000 records) repeated for every round, with the seconds spent in each projector;
* ``test_per_projector_rebuild_small``: each projector rebuilt alone from the same ledger, once;
* ``test_full_rebuild_large``: the full rebuild of the 100k dataset, once. It takes tens of minutes
  on Postgres, so it runs only with ``TL_BENCH_FULL_REBUILD=1`` (``just bench-rebuild``).
"""

from __future__ import annotations

import os
import time

import pytest
from bench_data import Dataset
from bench_env import ROUNDS
from bench_rebuild import TimedRegistry, fingerprint
from bench_stats import Recorder, Series
from tl_adapters import db as adapter_db
from tl_core.projection.defaults import default_registry


def _one(dataset: Dataset, scenario: str, seconds: list[float], note: str) -> Series:
    series = Series("rebuild", scenario, dataset.dialect, dataset.records, note=note)
    series.rounds = [[s * 1000.0] for s in seconds]
    series.loads = [round(os.getloadavg()[0], 2)] * len(seconds)
    return series


def _full(dataset: Dataset, recorder: Recorder, rounds: int, label: str) -> None:
    before = fingerprint(dataset.target)
    seconds: list[float] = []
    breakdown: dict[str, float] = {}
    applies: dict[str, int] = {}
    events = 0
    for index in range(rounds):
        registry = TimedRegistry()
        started = time.perf_counter()
        events = adapter_db.rebuild_projections(dataset.target, registry=registry)
        seconds.append(time.perf_counter() - started)
        if index == 0:
            breakdown = {k: round(v, 2) for k, v in sorted(registry.timings.items())}
            applies = dict(registry.applies)
    assert fingerprint(dataset.target) == before
    note = f"{events} events, {events / min(seconds):.0f} events/s at best"
    recorder.add(_one(dataset, f"full rebuild ({label})", seconds, note))
    recorder.extras[f"rebuild breakdown seconds {dataset.dialect} {dataset.records}"] = breakdown
    recorder.extras[f"rebuild applies {dataset.dialect} {dataset.records}"] = applies


def test_full_rebuild_small(small_dataset: Dataset, recorder: Recorder) -> None:
    _full(small_dataset, recorder, ROUNDS, f"{small_dataset.records} records")


def test_per_projector_rebuild_small(small_dataset: Dataset, recorder: Recorder) -> None:
    before = fingerprint(small_dataset.target)
    names = [p.name for p in default_registry().all()]
    for name in names:
        if name.startswith("webhook"):  # operational tables, never reset by a rebuild
            continue
        started = time.perf_counter()
        adapter_db.rebuild_projections(small_dataset.target, types=[name])
        seconds = time.perf_counter() - started
        recorder.add(
            _one(
                small_dataset,
                f"rebuild only {name} ({small_dataset.records} records)",
                [seconds],
                "",
            )
        )
    assert fingerprint(small_dataset.target) == before


def test_full_rebuild_large(dataset: Dataset, recorder: Recorder) -> None:
    if os.environ.get("TL_BENCH_FULL_REBUILD") != "1":
        pytest.skip("set TL_BENCH_FULL_REBUILD=1 (just bench-rebuild) for the 100k rebuild")
    _full(dataset, recorder, 1, f"{dataset.records} records")
