# P0-I8-T60 — Bench report renderer: results files to markdown tables

Status: merged
Tier: haiku
Labels: tests, tooling
Depends on: P0-I8-S60 (merged into the base of this branch)
Branch: `p0/i8d-t60-bench-report-renderer`

## Goal
`tests/bench/bench_report.py` turns the results files that `just bench` writes (`dev/data/bench/results/*.json`) into the markdown tables of `docs/reports/P0-I8-perf.md`: one table per brief §15 target with the dialect, median, p95, target and a met/NO verdict, plus a before/after comparison of two runs. The provided test `tests/tools/test_bench_report.py` defines the exact output; make it pass.

## Brief references (pasted)
> **§15 targets used here.** TUI responsiveness: grid scroll/filter < 150 ms on projections up to 100k rows. Realtime latency: change visible to other clients < 2 s. Rebuild: full projection rebuild for a large project within a maintenance window (hours, not days); per-module rebuild supported.
>
> **Method (the report's reader needs it):** each number is the median or the 95th percentile (nearest rank) over all timed calls of three rounds. A series marked `informational` is shown but is not part of the verdict.

## Interfaces (verbatim from repo at the branch point)
The shape of one results file (written by `Recorder.write` in `tests/bench/bench_stats.py`; one `series` entry is what `Series.summary()` returns):
```python
body = {
    "label": str, "git": str, "started_at": str,
    "finished_load_average": [float, float, float],
    "machine": {"nproc": int, "cpu": str, "load_average_at_start": [float, float, float], ...},
    "series": [
        {
            "target": str,        # grid_scroll | grid_sort | grid_filter | grid_render | realtime | rebuild
            "scenario": str, "dialect": str,   # dialect: "sqlite" or "postgres"
            "records": int, "n": int,
            "median_ms": float, "p95_ms": float, "max_ms": float,
            "round_p95_ms": list[float], "round_median_ms": list[float],
            "load_before_round": list[float], "note": str,
            "informational": bool,
        },
    ],
    "extras": dict,
}
```
The functions the test calls (create them with exactly these names):
```python
def render_targets(runs: list[dict]) -> str: ...      # runs: parsed results files, oldest first
def render_compare(before: dict, after: dict) -> str: ...
def main(argv: list[str] | None = None) -> int: ...   # 0 ok, 2 for bad usage or an unreadable file
```
The table groups, in this order, with heading text and p95 target (None: no hard target):
```python
GROUPS = [
    ("grid_scroll", "Grid scroll (p95 target 150 ms)", 150),
    ("grid_sort", "Grid sort (p95 target 150 ms)", 150),
    ("grid_filter", "Grid filter (p95 target 150 ms)", 150),
    ("grid_render", "Grid render in the headless pilot (p95 target 150 ms)", 150),
    ("realtime", "Realtime (p95 target 2000 ms)", 2000),
    ("rebuild", "Rebuild (no hard target: hours, not days)", None),
]
```

## Context (read these, nothing else)
- `tests/tools/test_bench_report.py` (the spec: read every assertion)
- `tests/bench/bench_stats.py` (only `Series.summary` and `Recorder.write`, for the file shape)
may explore: (none)

## Allowed paths
- `tests/bench/bench_report.py` (create)

## Steps
1. Parse: `load(paths)` reads each path as JSON. `render_targets` merges the series of all runs; a series of a later run replaces one of an earlier run with the same `(dialect, target, scenario)`. Rows keep file order inside a dialect, and dialects come in the order `sqlite`, `postgres`, then any other.
2. For each group that has at least one series, print `## <heading>`, a blank line, the header `| dialect | scenario | median ms | p95 ms | target ms | met |`, the separator line `| --- | --- | ---: | ---: | ---: | --- |`, then one row per series. Numbers have one decimal. In a group with a target: a normal row shows the target as an integer and `yes` when `p95_ms` is below it, else `NO`; an informational row shows `-` and `info`. The rebuild group shows `-` and `n/a` for every row.
3. After the rows of a group that has a target, one line per dialect present in it: a blank line, then `Verdict <dialect>: met (worst p95 <x> ms)` or `Verdict <dialect>: NOT MET (worst p95 <x> ms in <scenario>)`, judged over the non-informational rows of that dialect only (skip the line when a dialect has none). Groups are separated by one blank line.
4. `render_compare(before, after)`: a table with the header `| dialect | scenario | before p95 ms | after p95 ms | change |` and separator `| --- | --- | ---: | ---: | ---: |`, one row per series of `after` that `before` also has (same dialect, target, scenario), in the order of `after`; `change` is `x` plus after/before to two decimals (`-` when before is 0).
5. `main`: `bench_report.py FILE [FILE ...]` prints `render_targets`; `bench_report.py --compare BEFORE AFTER` prints `render_compare` (exactly two files, else print a usage line to stderr and return 2). An unreadable or invalid file prints `error: <reason>` to stderr and returns 2. Add a module docstring with the two usage lines, and `if __name__ == "__main__": sys.exit(main())`.

## Acceptance
```
uv run pytest tests/tools/test_bench_report.py -q
just check
```
Expected: 10 passed; `just check` clean (ruff, format, pyright, drift, licences).

## Tests to add
None: the test file is provided and must not be edited.

## Report requirements
Standard report. Paste the pytest summary line.

## Escalation triggers
- Stop and report *Blocked* if a provided assertion contradicts the steps above, or the results-file shape differs from the interface.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
