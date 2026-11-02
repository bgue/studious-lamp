"""Acceptance for P2-I1-T04a: the `tl awp` read verbs on the seed ledger.

Run: ``uv run python dev/accept/P2-I1/T04a.py --db PATH`` (PATH is the seed from ``S4.py --keep``).
Each verb runs through ``typer.testing.CliRunner`` on ``tl_cli.main.app``. ``--db`` is the root
option, so it goes before the group (``tl --db PATH awp ...``); click does not take it after a
subcommand. Prints ``PASS <verb> <first line>`` per verb, then ``T04a ok``; exits 1 on the first
failure. Read-only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tl_cli.main import app
from typer.testing import CliRunner

PROJECT = "P123"
runner = CliRunner()


class Failed(Exception):
    pass


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def run(db: Path, verb: list[str], *, exit_code: int = 0) -> list[str]:
    """Invoke ``tl --db DB awp <verb> --project P123`` and return its output lines."""
    result = runner.invoke(app, ["--db", str(db), "awp", *verb, "--project", PROJECT])
    need(
        result.exit_code == exit_code,
        f"{' '.join(verb)}: exit {result.exit_code}, want {exit_code}: {result.output[:200]}",
    )
    lines = result.output.splitlines()
    need(bool(lines), f"{' '.join(verb)}: no output")
    return lines


def passed(verb: str, lines: list[str]) -> None:
    print(f"PASS {verb} {lines[0]}")


def check(db: Path) -> None:
    cwps = run(db, ["cwp", "ls"])
    need(cwps[0] == "cwps: 6", f"cwps: 6, got {cwps[0]}")
    passed("cwp ls", cwps)

    planned = run(db, ["cwp", "ls", "--state", "Planned"])
    need(planned[0] == "cwps: 2" and len(planned) == 3, f"--state Planned: {planned}")
    passed("cwp ls --state Planned", planned)

    shown = run(db, ["cwp", "show", "P123-CWP-PIP-0001"])
    need(shown[0] == "cwp P123-CWP-PIP-0001", f"cwp show header: {shown[0]}")
    passed("cwp show", shown)

    missing = run(db, ["cwp", "show", "NO-SUCH-CWP"], exit_code=1)
    need(missing[0] == "error: no CWP NO-SUCH-CWP", f"bad CWP message: {missing[0]}")
    passed("cwp show (unknown)", missing)

    cwas = run(db, ["cwa", "ls"])
    need(cwas[0] == "cwas: 4", f"cwas: 4, got {cwas[0]}")
    passed("cwa ls", cwas)

    tree = run(db, ["wbs", "tree"])
    need(tree[0] == "wbs nodes: 9", f"wbs nodes: 9, got {tree[0]}")
    passed("wbs tree", tree)

    node = run(db, ["wbs", "show", "1.1.1"])
    need(node[0] == "wbs 1.1.1", f"wbs show header: {node[0]}")
    passed("wbs show", node)

    path = run(db, ["path", "show"])
    need(path[0] == "path version 1 of 1", f"path version 1 of 1, got {path[0]}")
    passed("path show", path)

    versions = run(db, ["path", "versions"])
    need(versions[0].endswith("steps 4  current"), f"path versions: {versions[0]}")
    passed("path versions", versions)

    packages = run(db, ["package", "ls"])
    need(packages[0] == "packages: 0", f"packages: 0, got {packages[0]}")
    passed("package ls", packages)

    bad_kind = run(db, ["package", "ls", "--kind", "XYZ"], exit_code=1)
    passed("package ls --kind XYZ", bad_kind)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="the seed ledger (S4.py --keep)")
    args = parser.parse_args()
    try:
        check(args.db)
    except Failed as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
    print("T04a ok")


if __name__ == "__main__":
    main()
