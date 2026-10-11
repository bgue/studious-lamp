"""The measurement method: repeated rounds, median and p95, machine details, a results file.

Method (docs/runbooks/performance-benches.md):

* a scenario is a function of the sample number, so each call can use a different page, filter
  value or record and the database cache cannot answer them all from one hot row;
* it runs ``warmup`` untimed calls, then ``rounds`` rounds of ``samples`` timed calls;
* the reported median and p95 are over all timed calls of all rounds, and the p95 of each round is
  kept too, so a round hit by another process on this shared container shows as a spread;
* the load average is read before every round, and the machine details are stored with the run.
"""

from __future__ import annotations

import json
import math
import os
import platform
import sqlite3
import statistics
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO / "dev" / "data" / "bench" / "results"

#: §15 targets, in milliseconds (rebuild has no hard number: "hours, not days").
TARGET_GRID_MS = 150.0
TARGET_REALTIME_MS = 2000.0


def percentile(values: list[float], fraction: float) -> float:
    """The nearest-rank percentile of ``values`` (``fraction`` 0.95 is the p95)."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("no samples")
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


@dataclass
class Series:
    """The timed calls of one scenario, grouped by round (milliseconds)."""

    target: str  # grid_scroll | grid_filter | grid_sort | grid_render | realtime | rebuild
    scenario: str
    dialect: str
    records: int
    rounds: list[list[float]] = field(default_factory=list[list[float]])
    loads: list[float] = field(default_factory=list[float])
    note: str = ""
    informational: bool = False  # reported, but not part of the target verdict

    @property
    def samples(self) -> list[float]:
        return [ms for round_ in self.rounds for ms in round_]

    def summary(self) -> dict[str, Any]:
        samples = self.samples
        return {
            "target": self.target,
            "scenario": self.scenario,
            "dialect": self.dialect,
            "records": self.records,
            "n": len(samples),
            "median_ms": round(statistics.median(samples), 2),
            "p95_ms": round(percentile(samples, 0.95), 2),
            "max_ms": round(max(samples), 2),
            "round_p95_ms": [round(percentile(r, 0.95), 2) for r in self.rounds],
            "round_median_ms": [round(statistics.median(r), 2) for r in self.rounds],
            "load_before_round": self.loads,
            "note": self.note,
            "informational": self.informational,
        }


def measure(
    call: Callable[[int], object],
    *,
    target: str,
    scenario: str,
    dialect: str,
    records: int,
    warmup: int = 3,
    rounds: int = 3,
    samples: int = 20,
    note: str = "",
    informational: bool = False,
) -> Series:
    """Time ``call(i)`` for ``rounds`` rounds of ``samples`` calls after ``warmup`` untimed ones."""
    series = Series(target, scenario, dialect, records, note=note, informational=informational)
    for i in range(warmup):
        call(-1 - i)
    index = 0
    for _ in range(rounds):
        series.loads.append(round(os.getloadavg()[0], 2))
        timed: list[float] = []
        for _ in range(samples):
            started = time.perf_counter()
            call(index)
            timed.append((time.perf_counter() - started) * 1000.0)
            index += 1
        series.rounds.append(timed)
    return series


def series_from_flat(
    flat: list[float],
    *,
    rounds: int,
    target: str,
    scenario: str,
    dialect: str,
    records: int,
    loads: list[float] | None = None,
    note: str = "",
    informational: bool = False,
) -> Series:
    """A :class:`Series` from timed calls in one list, cut into ``rounds`` equal rounds."""
    size = max(1, len(flat) // rounds)
    series = Series(target, scenario, dialect, records, note=note, informational=informational)
    series.rounds = [flat[r * size : (r + 1) * size] for r in range(rounds)]
    series.loads = loads if loads is not None else [round(os.getloadavg()[0], 2)] * rounds
    return series


def machine_info() -> dict[str, Any]:
    """What the numbers were measured on."""
    model = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    memory = ""
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal"):
                memory = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "nproc": os.cpu_count(),
        "cpu": model,
        "memory": memory,
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "kernel": platform.release(),
        "load_average_at_start": [round(x, 2) for x in os.getloadavg()],
    }


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


@dataclass
class Recorder:
    """Collects the series of one pytest session and writes them as one JSON file."""

    label: str
    series: list[Series] = field(default_factory=list[Series])
    extras: dict[str, Any] = field(default_factory=dict[str, Any])
    started: float = field(default_factory=time.time)
    machine: dict[str, Any] = field(default_factory=machine_info)

    def add(self, series: Series) -> Series:
        self.series.append(series)
        return series

    def write(self) -> Path | None:
        if not self.series and not self.extras:
            return None
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.fromtimestamp(self.started, UTC).strftime("%Y%m%dT%H%M%SZ")
        body = {
            "label": self.label,
            "git": git_sha(),
            "started_at": stamp,
            "finished_load_average": [round(x, 2) for x in os.getloadavg()],
            "machine": self.machine,
            "series": [s.summary() for s in self.series],
            "extras": self.extras,
        }
        path = RESULTS_DIR / f"{stamp}-{self.label}.json"
        path.write_text(json.dumps(body, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return path
