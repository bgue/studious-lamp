"""Acceptance for P2-I1-T10: the awp read views on the seed ledger.

Run: ``uv run python dev/accept/P2-I1/T10.py --db PATH`` (PATH is the seed from ``S4.py --keep``).
Prints ``PASS <view> <n> rows`` per view, then ``T10 ok``. Read-only. The hidden-CWP check is not
here: awp records carry no confidentiality class, so it moves to T11 (tests, with a fixture).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tl_adapters.db import as_target, open_uow
from tl_mod_awp import views

SCOPE = "project:P123"


class Failed(Exception):
    pass


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def passed(view: str, n: int) -> None:
    print(f"PASS {view} {n} rows")


def check(db: Path) -> None:
    with open_uow(as_target(str(db)), readonly=True) as uow:
        conn = uow.conn()

        cwps = views.cwp_list(conn, SCOPE)
        need(len(cwps) == 6, f"6 CWPs, got {len(cwps)}")
        need([c.number for c in cwps] == sorted(c.number for c in cwps), "CWPs by number")
        by_state = {}
        for c in cwps:
            by_state[c.state] = by_state.get(c.state, 0) + 1
        need(
            by_state == {"Planned": 2, "In development": 2, "Released for IWP development": 2},
            f"states {by_state}",
        )
        need(len(views.cwp_list(conn, SCOPE, state="Planned")) == 2, "Planned filter")
        need(len(views.cwp_list(conn, SCOPE, discipline="PIP")) == 4, "discipline filter")
        need(len(views.cwp_list(conn, SCOPE, cwa="A1")) == 2, "cwa filter")
        need(views.cwp_list(conn, SCOPE, cwa="NOPE") == [], "unknown cwa answers []")
        passed("cwp_list", len(cwps))

        details = [views.cwp_detail(conn, SCOPE, c.number) for c in cwps]
        need(all(d is not None for d in details), "every CWP has a detail")
        first = views.cwp_detail(conn, SCOPE, "P123-CWP-PIP-0001")
        need(
            first is not None and [a.wbs_code for a in first.allocations] == ["1.1.1"],
            "allocation of PIP-0001",
        )
        need(views.cwp_detail(conn, SCOPE, "NO-SUCH") is None, "unknown CWP is None")
        passed("cwp_detail", len(details))

        cwas = views.cwa_list(conn, SCOPE)
        need([a.code for a in cwas] == ["A1", "A2", "A3", "A4"], "CWAs by code")
        passed("cwa_list", len(cwas))

        tree = views.wbs_tree(conn, SCOPE)
        need(len(tree) == 9, f"9 WBS nodes, got {len(tree)}")
        need([n.code for n in tree][:3] == ["1", "1.1", "1.1.1"], "depth-first order")
        need([n.code for n in views.wbs_tree(conn, SCOPE, depth=1)] == ["1"], "depth=1")
        need(all(n.total_hours is None for n in tree), "no rollup rows on the seed")
        leaf = views.wbs_detail(conn, SCOPE, "1.1.1")
        need(leaf is not None and leaf.parent_code == "1.1", "wbs_detail parent")
        need(views.wbs_detail(conn, SCOPE, "9.9") is None, "unknown node is None")
        passed("wbs_tree", len(tree))
        passed("wbs_detail", 1 if leaf is not None else 0)

        current = views.path(conn, SCOPE)
        need(current is not None and current.version == 1, "path v1")
        need(views.path(conn, SCOPE, version=9) is None, "unknown version is None")
        need(
            [s.position for s in current.steps] == sorted(s.position for s in current.steps),
            "steps in position order",
        )
        passed("path", 1 if current is not None else 0)

        versions = views.path_versions(conn, SCOPE)
        need([v.version for v in versions] == [1] and versions[0].is_current, "version 1")
        passed("path_versions", len(versions))

        packages = views.package_list(conn, SCOPE)
        need(packages == [], "no packages on the seed")
        passed("package_list", len(packages))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="the seed ledger (S4.py --keep)")
    args = parser.parse_args()
    try:
        check(args.db)
    except Failed as exc:
        print(f"FAIL {exc}")
        sys.exit(1)
    print("T10 ok")


if __name__ == "__main__":
    main()
