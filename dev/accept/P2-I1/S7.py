"""Acceptance for P2-I1-S7: reload after a compensated load reinstates the 12 WBS nodes (SQLite).

Run: ``uv run python dev/accept/P2-I1/S7.py``. Prints ``PASS <check>`` per check, then ``S7 ok``.
"""

from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path
from typing import Any

import tl_mod_awp
from tl_adapters.db import as_target, create_schema, open_uow
from tl_core.services.errors import RecordNotFoundError
from tl_core.util import new_ulid
from tl_mod_awp.errors import InUseError, WbsRuleError
from tl_mod_awp.targets import wbs_target
from tl_mod_legacy.model import Grid, LoaderDef

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages/tl-modules/awp/tests"))
from awp_world import SCOPE, World, hidden_record, refuses  # noqa: E402

LD, WHO = LoaderDef("l", "acc", "t", "x", "d", ""), {"actor": "user:sue", "source": "legacy:acc"}
SAMPLE = Path(tl_mod_awp.__file__).parent / "samples" / "wbs-sample.csv"
TREE = "SELECT code, parent_id, position, depth, retired FROM cur_awp_wbs_node ORDER BY code"
LINES = "SELECT node_id, cost_code_id, percent FROM cur_awp_wbs_allocation ORDER BY 1, 2"


def ok(good: bool, what: str) -> None:
    assert good, what
    print("PASS", what)


def main(work: Path) -> None:
    w = World(as_target(str(work / "t.db")))
    create_schema(w.db)
    w.people()
    w.editions()
    w.cost_codes(("WLD", "Weld"), ("ERC", "Erect"), ("TST", "Test"))
    got = list(csv.reader(SAMPLE.open()))
    grid = Grid(got[0], [list(r) for r in got[1:]])

    def run(fn: Any) -> Any:
        with open_uow(w.db) as u:
            return fn(u)

    def load(cid: str) -> list[Any]:
        t = wbs_target()

        def go(u: Any) -> Any:
            return t.apply(
                u,
                SCOPE,
                LD,
                t.plan(u.conn(), SCOPE, LD, grid),
                correlation_id=cid,
                confidentiality=None,
                **WHO,
            )

        return run(go)

    def undo(ids: list[str], cid: str) -> int:
        return int(
            run(
                lambda u: wbs_target().reverse(u, SCOPE, ids, correlation_id=cid, reason="r", **WHO)
            )
        )

    ids = [c.record_id for c in load("load:1")]
    first, lines, recs = (
        w.rows(TREE),
        w.rows(LINES),
        w.scalar("SELECT COUNT(*) FROM cur_core_record"),
    )
    ok(len(ids) == 12 and undo(ids, "comp:1") == 12, "12 nodes load, compensate retires 12")
    ok(all(r["retired"] for r in w.rows(TREE)), "all 12 retired")
    plan = run(lambda u: wbs_target().plan(u.conn(), SCOPE, LD, grid))
    ok((len(plan.rows), len(plan.existing)) == (12, 0), "reload plans new 12")
    ok(sorted(c.record_id for c in load("load:2")) == sorted(ids), "reload keeps the stream ids")
    n = w.scalar("SELECT COUNT(*) FROM events WHERE event_type = 'WBSNode.Reinstated'")
    ok(
        n == 12 and w.scalar("SELECT COUNT(*) FROM cur_core_record") == recs,
        "12 Reinstated, no new records",
    )
    ok(w.rows(TREE) == first and w.rows(LINES) == lines, "tree equals the first load")
    ok(
        undo(ids, "comp:2") == 12 and all(r["retired"] for r in w.rows(TREE)),
        "compensate again retires 12",
    )
    load("load:3")
    w.areas_and_path(("A1",))
    cwp = w.new_cwp("PIP", "Rack", "A1")
    w.call(
        "uma", "AllocateCwpToWbs", cwp=cwp, allocations=[{"wbs_code": "1.1.1", "percent": "100.00"}]
    )
    ok(True, "a CWP allocates to a reinstated leaf")
    refuses(InUseError, lambda: undo(ids, "comp:x"))
    ok(True, "a package allocation blocks the retire")
    leaf = w.id_of("1.1.2")
    refuses(WbsRuleError, lambda: w.call("sue", "ReinstateWbsNode", node=leaf, reason="x"))
    ok(True, "reinstate of an active node refused")
    hid, gone = hidden_record(w), new_ulid()
    a = refuses(
        RecordNotFoundError, lambda: w.call("sue", "ReinstateWbsNode", node=hid, reason="x")
    )
    b = refuses(
        RecordNotFoundError, lambda: w.call("sue", "ReinstateWbsNode", node=gone, reason="x")
    )
    ok(
        str(a).replace(hid, "ID") == str(b).replace(gone, "ID"),
        "a hidden id answers as a missing one",
    )
    print("S7 ok")


with tempfile.TemporaryDirectory() as tmp:
    main(Path(tmp))
