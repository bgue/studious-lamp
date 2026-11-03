"""Acceptance for P2-I1-T04b: the three awp reports and `tl awp report`, on a copy of the S4 seed.

The seed is copied to a temporary file, queued and rolled up there (``requeue_orphans``, then the
worker's ``run_until_idle``, as S5 does), then each report is checked against the views.
Run: ``uv run python dev/accept/P2-I1/T04b.py --db .accept/p2-i1.db`` (the seed: ``S4.py --keep``).
One ``PASS`` per check, then ``T04b ok``.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import typer
from sqlalchemy import Connection
from tl_adapters.db import as_target, open_uow
from tl_cli import awp_report
from tl_mod_awp import reports, views
from tl_mod_awp.reports import CostFigure
from tl_mod_awp.worker import build_worker, requeue_orphans
from tl_mod_cost.views import cost_codes
from typer.testing import CliRunner

SCOPE = "project:P123"
PROJECT = "P123"
ZERO = Decimal("0")
CWP_COUNT = 6
UNALLOCATED = "Unallocated"


def check(ok: bool, what: str) -> None:
    if not ok:
        sys.exit(f"FAIL {what}")
    print(f"PASS {what}")


def cost_figures(conn: Connection) -> dict[str, CostFigure]:
    """The cost system's figures of the project, as the CLI loads them (latest snapshot)."""
    out: dict[str, CostFigure] = {}
    for view in cost_codes(conn, SCOPE, limit=20000):
        hours = view.figures.get("hours_budget")
        out[view.code] = CostFigure(
            title=view.title, hours_budget=None if hours is None else Decimal(str(hours))
        )
    return out


def check_cwp_status(conn: Connection) -> None:
    cwps = views.cwp_list(conn, SCOPE)
    status = reports.cwp_status(conn, SCOPE)
    body, total = status[:-1], status[-1]
    counts = sum(row.count for row in body)
    budgets = sum((row.budget_hours for row in body), ZERO)
    want = sum((c.budget_hours or ZERO for c in cwps), ZERO)
    check(
        counts == CWP_COUNT == len(cwps)
        and budgets == want
        and total.count == counts
        and total.budget_hours == budgets,
        "cwp_status",
    )


def check_wbs(conn: Connection) -> None:
    nodes = views.wbs_tree(conn, SCOPE)
    parent_codes = {n.parent_code for n in nodes if n.parent_code is not None}
    leaves = [n for n in nodes if n.code not in parent_codes]
    roots = [n for n in nodes if n.parent_code is None]
    leaf_sum: dict[str, Decimal] = defaultdict(lambda: ZERO)
    root_sum: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for node in leaves:
        for code, hours in node.by_cost_code.items():
            leaf_sum[code] += hours
    for node in roots:
        for code, hours in node.by_cost_code.items():
            root_sum[code] += hours
    check(
        dict(root_sum) == dict(leaf_sum),
        "parents' by_cost_code equal the leaves'",
    )
    rows = reports.wbs_vs_cost_code(conn, SCOPE, cost_figures(conn))
    body, unallocated = rows[:-1], rows[-1]
    per_code = all(r.awp_budget_hours == leaf_sum.get(r.code, ZERO) for r in body)
    listed = set(leaf_sum) <= {r.code for r in body}
    check(
        per_code
        and listed
        and unallocated.code == UNALLOCATED
        and unallocated.awp_budget_hours >= ZERO,
        "wbs_vs_cost_code",
    )


def check_sequence(conn: Connection) -> None:
    path = views.path(conn, SCOPE)
    rows = reports.cwa_sequence(conn, SCOPE)
    steps = [] if path is None else path.steps
    in_order = [r.position for r in rows] == [s.position for s in steps]
    same_areas = [r.cwa for r in rows] == [s.cwa for s in steps]
    check(len(rows) == 4 and in_order and same_areas, "cwa_sequence")


def check_csv(conn: Connection) -> None:
    sets = [
        reports.cwp_status(conn, SCOPE),
        reports.wbs_vs_cost_code(conn, SCOPE, cost_figures(conn)),
        reports.cwa_sequence(conn, SCOPE),
    ]
    ok = True
    for rows in sets:
        text = reports.to_csv(rows)
        lines = text.split("\n")
        header = ",".join(type(rows[0]).model_fields)
        ok = ok and lines[0] == header and len(lines) == len(rows) + 2 and lines[-1] == ""
        ok = ok and text.endswith("\n")
    check(ok, "csv")


def check_cli(db: Path) -> None:
    app = typer.Typer()
    awp_report.register(app)
    runner = CliRunner()
    good = runner.invoke(
        app, ["report", "cwp_status", "--csv", "--project", PROJECT, "--db", str(db)]
    )
    bad = runner.invoke(app, ["report", "no_such", "--project", PROJECT, "--db", str(db)])
    check(
        good.exit_code == 0
        and good.stdout.startswith("state,discipline,count,budget_hours\n")
        and bad.exit_code == 1,
        "cli",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="the S4 seed (SQLite file)")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "t04b.db"
        shutil.copyfile(args.db, copy)
        target = as_target(str(copy))
        requeue_orphans(target)
        with build_worker(target) as worker:
            worker.runner.run_until_idle()
        with open_uow(target, readonly=True) as uow:
            conn = uow.conn()
            check_cwp_status(conn)
            check_wbs(conn)
            check_sequence(conn)
            check_csv(conn)
        check_cli(copy)
    print("T04b ok")


if __name__ == "__main__":
    main()
