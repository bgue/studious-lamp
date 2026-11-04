"""Acceptance for P2-I3-T08: `just demo P2-I3` on SQLite (``TL_DEMO_BACKENDS=sqlite``).

Runs ``dev/demos/P2-I3.sh`` and checks its output: one ``PASS clause N`` line for each of the
eleven clauses of section 10 (N = 1 .. 11, in order, each exactly once) and the final line
``P2-I3 demo OK on: sqlite``. Prints ``PASS <check>`` per check and exits 0; on the first failure
prints ``FAIL <check>: <detail>`` and exits 1. The Postgres run is ``just demo P2-I3`` itself.

Run from any directory:

    uv run python dev/accept/P2-I3/T08.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "dev" / "demos" / "P2-I3.sh"
CLAUSE = re.compile(r"PASS clause (\d+)")
FINAL = "P2-I3 demo OK on: sqlite"


def check(name: str, condition: bool, detail: str) -> int:
    if condition:
        print(f"PASS {name}")
        return 0
    print(f"FAIL {name}: {detail}")
    return 1


def main() -> int:
    env = {**os.environ, "TL_DEMO_BACKENDS": "sqlite"}
    run = subprocess.run(
        ["bash", str(DEMO)], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    lines = [line.strip() for line in run.stdout.splitlines()]
    numbers = [int(m.group(1)) for line in lines if (m := re.fullmatch(CLAUSE, line))]
    failed = 0
    failed += check(
        "the demo exits 0", run.returncode == 0, f"exit {run.returncode}: {run.stderr[-300:]}"
    )
    failed += check(
        "PASS clause 1 to PASS clause 11, each once and in order",
        numbers == list(range(1, 12)),
        f"the clause lines are {numbers}",
    )
    failed += check(
        f"the last line is {FINAL!r}",
        bool(lines) and lines[-1] == FINAL,
        f"the last line is {lines[-1] if lines else ''!r}",
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
