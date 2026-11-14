"""Export the run's status as plain CSV and JSONL (owner, 2026-11-14: reports are simple exports).

    uv run python dev/tools/export_reports.py [--out docs/reports/export]

Reads only files in the repository and `git log`; writes:

    status.csv      every row of docs/reports/STATUS.md (one per increment)
    deferred.csv    every row of every table in docs/build-spec/DEFERRED.md, with its section
    roadmap.csv     the order-of-work table of docs/build-spec/roadmap-2026-11-07.md
    extensions.csv  the increment table of docs/build-spec/12-extension-plan.md §0
    boards.jsonl    one line per BOARD row of every docs/tickets/<INC>/STATE.md
    merges.csv      merge commits on the current branch: sha, date, subject
    tour.csv        every screenshot under docs/reports/tour: tour, file
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def md_tables(path: Path) -> list[list[list[str]]]:
    """Every pipe table in ``path`` as rows of cells (header first, the --- line dropped)."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                current.append(cells)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def write_csv(path: Path, rows: list[list[str]]) -> int:
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    return max(len(rows) - 1, 0)


def first_table(path: Path, header_start: str) -> list[list[str]]:
    for table in md_tables(path):
        if table and table[0] and table[0][0].startswith(header_start):
            return table
    return []


def deferred() -> list[list[str]]:
    """All DEFERRED tables in one sheet; the first column names the ## section each row is under."""
    rows: list[list[str]] = [["section", "item", "why", "when"]]
    section = ""
    for line in (REPO / "docs/build-spec/DEFERRED.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif line.startswith("|") and not line.startswith(("| Item", "|---")):
            rows.append([section, *[c.strip() for c in line.strip().strip("|").split("|")]])
    return rows


def boards() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for state in sorted(REPO.glob("docs/tickets/*/STATE.md")):
        inc = state.parent.name
        in_board = False
        for line in state.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                in_board = line.startswith("## BOARD")
                continue
            parts = line.split(None, 5)
            if in_board and len(parts) >= 3:
                keys = ("id", "kind", "state", "review", "sha", "note")
                row = dict(zip(keys, parts, strict=False))
                out.append({"increment": inc, **row})
    return out


def merges() -> list[list[str]]:
    log = subprocess.run(
        ["git", "log", "--merges", "--first-parent", "--format=%h\t%ad\t%s", "--date=short"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [["sha", "date", "subject"]] + [ln.split("\t", 2) for ln in log.splitlines() if ln]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the run status as CSV and JSONL.")
    parser.add_argument("--out", default=str(REPO / "docs/reports/export"))
    out = Path(parser.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    counts = {
        "status.csv": write_csv(
            out / "status.csv", first_table(REPO / "docs/reports/STATUS.md", "Time")
        ),
        "deferred.csv": write_csv(out / "deferred.csv", deferred()),
        "roadmap.csv": write_csv(
            out / "roadmap.csv", first_table(REPO / "docs/build-spec/roadmap-2026-11-07.md", "#")
        ),
        "extensions.csv": write_csv(
            out / "extensions.csv",
            first_table(REPO / "docs/build-spec/12-extension-plan.md", "Inc"),
        ),
        "merges.csv": write_csv(out / "merges.csv", merges()),
    }
    rows = boards()
    (out / "boards.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    counts["boards.jsonl"] = len(rows)
    shots = [["tour", "file"]] + [
        [p.parent.relative_to(REPO / "docs/reports/tour").as_posix(), p.name]
        for p in sorted((REPO / "docs/reports/tour").rglob("*.svg"))
    ]
    counts["tour.csv"] = write_csv(out / "tour.csv", shots)
    for name, n in counts.items():
        print(f"{name}: {n} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
