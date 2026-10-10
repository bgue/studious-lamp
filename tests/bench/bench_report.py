"""Results files in, the markdown tables of ``docs/reports/P0-I8-perf.md`` out.

bench_report.py FILE [FILE ...]
bench_report.py --compare BEFORE AFTER

The first form prints one table per brief section 15 target for one or more runs (oldest first; a
later run replaces the series it shares with an earlier one). The second prints the p95 of every
series both runs have, before and after, with the ratio after/before.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

#: (target, heading, p95 target in ms; None: no hard target)
GROUPS: list[tuple[str, str, int | None]] = [
    ("grid_scroll", "Grid scroll (p95 target 150 ms)", 150),
    ("grid_sort", "Grid sort (p95 target 150 ms)", 150),
    ("grid_filter", "Grid filter (p95 target 150 ms)", 150),
    ("grid_render", "Grid render in the headless pilot (p95 target 150 ms)", 150),
    ("realtime", "Realtime (p95 target 2000 ms)", 2000),
    ("rebuild", "Rebuild (no hard target: hours, not days)", None),
]

TABLE_HEADER = "| dialect | scenario | median ms | p95 ms | target ms | met |"
TABLE_SEPARATOR = "| --- | --- | ---: | ---: | ---: | --- |"
COMPARE_HEADER = "| dialect | scenario | before p95 ms | after p95 ms | change |"
COMPARE_SEPARATOR = "| --- | --- | ---: | ---: | ---: |"
USAGE = "usage: bench_report.py FILE [FILE ...] | bench_report.py --compare BEFORE AFTER"
REQUIRED_KEYS = ("target", "scenario", "dialect", "median_ms", "p95_ms", "informational")

SeriesKey = tuple[str, str, str]  # (dialect, target, scenario)


def load(paths: list[str]) -> list[dict[str, Any]]:
    """Parse each results file as JSON, oldest first; raises ValueError naming the bad file."""
    return [load_one(Path(raw)) for raw in paths]


def load_one(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
        raise ValueError(f"cannot read {path}: {reason}") from exc
    try:
        body = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"{path}: not valid JSON ({exc})") from exc
    if not isinstance(body, dict) or not isinstance(body.get("series"), list):
        raise ValueError(f"{path}: not a bench results file (no series list)")
    for entry in body["series"]:
        if not isinstance(entry, dict) or any(key not in entry for key in REQUIRED_KEYS):
            raise ValueError(f"{path}: a series entry lacks one of {', '.join(REQUIRED_KEYS)}")
    return body


def series_key(entry: dict[str, Any]) -> SeriesKey:
    return (str(entry["dialect"]), str(entry["target"]), str(entry["scenario"]))


def merged_series(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The series of all runs; a later series replaces an earlier one with the same key in place."""
    merged: dict[SeriesKey, dict[str, Any]] = {}
    for run in runs:
        for entry in run["series"]:
            merged[series_key(entry)] = entry
    return list(merged.values())


def dialect_order(series: list[dict[str, Any]]) -> list[str]:
    """``sqlite``, then ``postgres``, then any other dialect in the order it first appears."""
    seen: list[str] = []
    for entry in series:
        dialect = str(entry["dialect"])
        if dialect not in seen:
            seen.append(dialect)
    rank = {"sqlite": 0, "postgres": 1}
    return sorted(seen, key=lambda dialect: rank.get(dialect, 2))  # sorted() is stable


def table_row(entry: dict[str, Any], limit: int | None) -> str:
    if limit is None:
        target, met = "-", "n/a"
    elif entry["informational"]:
        target, met = "-", "info"
    else:
        target = str(limit)
        met = "yes" if float(entry["p95_ms"]) < limit else "NO"
    return (
        f"| {entry['dialect']} | {entry['scenario']} | {float(entry['median_ms']):.1f} "
        f"| {float(entry['p95_ms']):.1f} | {target} | {met} |"
    )


def verdict_line(dialect: str, judged: list[dict[str, Any]], limit: int) -> str | None:
    """The verdict for one dialect of one group, over its non-informational rows."""
    rows = [entry for entry in judged if entry["dialect"] == dialect and not entry["informational"]]
    if not rows:
        return None
    worst = max(rows, key=lambda entry: float(entry["p95_ms"]))
    worst_p95 = float(worst["p95_ms"])
    if worst_p95 < limit:
        return f"Verdict {dialect}: met (worst p95 {worst_p95:.1f} ms)"
    return f"Verdict {dialect}: NOT MET (worst p95 {worst_p95:.1f} ms in {worst['scenario']})"


def render_targets(runs: list[dict[str, Any]]) -> str:
    series = merged_series(runs)
    dialects = dialect_order(series)
    blocks: list[str] = []
    for target, heading, limit in GROUPS:
        in_group = [entry for entry in series if entry["target"] == target]
        if not in_group:
            continue
        lines = [f"## {heading}", "", TABLE_HEADER, TABLE_SEPARATOR]
        for dialect in dialects:
            for entry in in_group:
                if entry["dialect"] == dialect:
                    lines.append(table_row(entry, limit))
        if limit is not None:
            for dialect in dialects:
                verdict = verdict_line(dialect, in_group, limit)
                if verdict is not None:
                    lines.extend(["", verdict])
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n" if blocks else ""


def render_compare(before: dict[str, Any], after: dict[str, Any]) -> str:
    old = {series_key(entry): entry for entry in before["series"]}
    lines = [COMPARE_HEADER, COMPARE_SEPARATOR]
    for entry in merged_series([after]):
        earlier = old.get(series_key(entry))
        if earlier is None:
            continue
        before_p95 = float(earlier["p95_ms"])
        after_p95 = float(entry["p95_ms"])
        change = f"x{after_p95 / before_p95:.2f}" if before_p95 else "-"
        lines.append(
            f"| {entry['dialect']} | {entry['scenario']} | {before_p95:.1f} "
            f"| {after_p95:.1f} | {change} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    compare = bool(args) and args[0] == "--compare"
    paths = args[1:] if compare else args
    if not paths or any(arg.startswith("-") for arg in paths):
        print(USAGE, file=sys.stderr)
        return 2
    if compare and len(paths) != 2:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        runs = load(paths)
        text = render_compare(runs[0], runs[1]) if compare else render_targets(runs)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
