"""Acceptance for P2-I1-T10b: a WBS node's total_hours never reveals a hidden cost code.

Run: ``uv run python dev/accept/P2-I1/T10b.py --db PATH`` (PATH is the seed from ``S4.py --keep``).
The seed stays untouched: the script copies it, queues and runs the rollup on the copy, then reads
the views. Prints ``PASS <check>`` per check, then ``T10b ok``; exits 1 on the first failure.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Connection, text
from tl_adapters.db import as_target, open_uow
from tl_mod_awp import views
from tl_mod_awp.worker import build_worker, requeue_orphans

SCOPE = "project:P123"


class Failed(Exception):
    pass


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def passed(check: str) -> None:
    print(f"PASS {check}")


def unallocated_of(conn: Connection) -> dict[str, Decimal]:
    """The unallocated line of each node, the later row winning (a leaf with no cost codes)."""
    rows = conn.execute(
        text(
            f"SELECT subject_id, value FROM {views.ROLLUP_TABLE} "
            "WHERE scope = :scope AND measure = :measure AND line = :line ORDER BY as_of_seq"
        ),
        {"scope": SCOPE, "measure": views.ROLLUP_MEASURE, "line": views.ROLLUP_UNALLOCATED},
    )
    return {str(r[0]): Decimal(str(r[1])) for r in rows}


def cost_lines(conn: Connection) -> list[tuple[str, str]]:
    """(node id, cost code id) of every cost_code line of the rollup."""
    rows = conn.execute(
        text(
            f"SELECT DISTINCT subject_id, cost_code_id FROM {views.ROLLUP_TABLE} "
            "WHERE scope = :scope AND measure = :measure AND line = :line "
            "ORDER BY subject_id, cost_code_id"
        ),
        {"scope": SCOPE, "measure": views.ROLLUP_MEASURE, "line": views.ROLLUP_COST_CODE},
    )
    return [(str(r[0]), str(r[1])) for r in rows if r[1] is not None]


def cost_key(conn: Connection, cost_id: str) -> str:
    return str(
        conn.execute(
            text("SELECT key FROM cur_core_record WHERE id = :id"), {"id": cost_id}
        ).scalar_one()
    )


def cwp_codes(conn: Connection) -> set[str]:
    """The WBS codes a CWP is allocated to."""
    codes: set[str] = set()
    for cwp in views.cwp_list(conn, SCOPE):
        detail = views.cwp_detail(conn, SCOPE, cwp.number)
        if detail is not None:
            codes.update(a.wbs_code for a in detail.allocations)
    return codes


def check(db: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "t10b-seed.db"
        shutil.copyfile(db, copy)
        target = as_target(str(copy))
        requeue_orphans(target)
        with build_worker(target) as worker:
            worker.runner.run_until_idle()

        with open_uow(target, readonly=True) as uow:
            conn = uow.conn()
            tree = views.wbs_tree(conn, SCOPE)
            codes = cwp_codes(conn)
            unalloc = unallocated_of(conn)
            pairs = [(s, c) for s, c in cost_lines(conn) if s in {r.id for r in tree}]
            leaves = [r for r in tree if r.code in codes and r.by_cost_code]
            if not leaves or not pairs:
                print(f"BLOCKED no leaf with cost codes and a CWP allocation: {sorted(codes)}")
                sys.exit(1)

            # (a) every leaf with a CWP has a total, and the total is its lines (nothing hidden)
            for row in tree:
                if row.code in codes:
                    need(row.total_hours is not None, f"{row.code} has no total_hours")
                    lines = sum(row.by_cost_code.values(), Decimal(0))
                    need(
                        row.total_hours == lines + unalloc.get(row.id, Decimal(0)),
                        f"{row.code} total is not the sum of its lines",
                    )
            passed("unfiltered totals")

            # (b) hide one cost code that has a line; its nodes lose it from the total
            _, code_id = pairs[0]
            hidden_key = cost_key(conn, code_id)
            with_code = {s for s, c in pairs if c == code_id}
            need(
                any(r.id in with_code and hidden_key in r.by_cost_code for r in tree),
                "the hidden cost code has a visible line",
            )
            real_hidden = views._hidden

            def hiding(conn_: Connection, ids: set[str]) -> set[str]:
                return set(real_hidden(conn_, ids)) | {code_id}

            views._hidden = hiding
            try:
                patched = views.wbs_tree(conn, SCOPE)
            finally:
                views._hidden = real_hidden
            after_by_id = {r.id: r for r in patched}
            for row in tree:
                after = after_by_id[row.id]
                if row.id in with_code:
                    visible = sum(
                        (v for k, v in row.by_cost_code.items() if k != hidden_key), Decimal(0)
                    )
                    need(
                        after.total_hours == visible + unalloc.get(row.id, Decimal(0)),
                        f"{row.code} total is not the visible lines",
                    )
                    need(after.total_hours < row.total_hours, f"{row.code} total not lower")
                    need(hidden_key not in after.by_cost_code, f"{row.code} still lists the code")
                else:
                    need(after.total_hours == row.total_hours, f"{row.code} total changed")
            passed("hidden cost code total")

            # (c) the hidden code string appears in no row of the patched tree
            need(
                not any(hidden_key in r.model_dump_json() for r in patched),
                "the hidden code string is in a row",
            )
            passed("hidden code absent")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="the seed ledger (S4.py --keep)")
    args = parser.parse_args()
    try:
        check(args.db)
    except Failed as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
    print("T10b ok")


if __name__ == "__main__":
    main()
