"""Acceptance for P2-I5-S3: progress rollup on read and the progress CSV export.

SQLite, dialect-neutral. One ``PASS <check>`` line each, then ``S3 ok``.
Run: ``uv run python dev/accept/P2-I5/S3.py``.
"""

from __future__ import annotations

import csv
import io
import sys
import tempfile
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "packages/tl-modules/awp/tests"))
from progress_world import build_roll  # noqa: E402
from sqlalchemy import text  # noqa: E402
from tl_adapters.db import open_uow  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_mod_awp.names import CWP  # noqa: E402
from tl_mod_awp.progress.export import ExportError  # noqa: E402


def check(name: str, ok: bool) -> None:
    if not ok:
        sys.exit(f"FAIL {name}")
    print(f"PASS {name}")


def rows_of(data: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(data)))


def main() -> None:
    rr = build_roll(Path(tempfile.mkdtemp()) / "s3.db")
    w = rr.w
    ids = rr.ids
    found = rr.read()
    cwp = next(c for c in found.cwps if c.cwp_id == ids["a"])
    check(
        "3 IWPs of 10, 10, 20 h at 50, 100, 25 give 20.0 of 40.0",
        (cwp.earned_hours, cwp.hours) == (D("20.0"), D("40.0")),
    )
    nodes = {n.node_id: n for n in found.nodes}
    parts = sorted(nodes[w.id_of(c)].earned_hours for c in ("1.2.1", "1.2.2", "1.2.3"))
    check(
        "33/33/34 of 10.0 gives 3.3/3.3/3.4 summing to the total",
        parts == [D("3.3"), D("3.3"), D("3.4")]
        and nodes[w.id_of("1.2")].earned_hours == sum(parts),
    )
    check("a node with descendants includes them", nodes[w.id_of("1.1")].earned_hours == D("30.0"))
    check(
        "the cost code lines sum to the node total",
        sum(ln.earned_hours for ln in found.lines) == nodes[w.id_of("1")].earned_hours
        and found.lines[-1].code == "Unallocated",
    )
    check(
        "a null hour weighs the mean",
        next(c for c in found.cwps if c.cwp_id == ids["c"]).earned_hours == D("10.0"),
    )
    w.set_status(ids["a3"], "Cancelled")
    cancelled = next(c for c in rr.read().cwps if c.cwp_id == ids["a"])
    check("a Cancelled IWP is out", (cancelled.iwps, cancelled.earned_hours) == (2, D("15.0")))
    w.set_status(ids["a3"], "Draft")
    lowest = cf.Viewer()
    with rr.hidden(ids["b"], record_type=CWP):
        seen = rr.read(viewer=lowest)
        check(
            "a hidden CWP is absent and leaves no note",
            ids["b"] not in {c.cwp_id for c in seen.cwps} and seen.notes == [],
        )
        check(
            "the figure of what remains is unchanged",
            next(c for c in seen.cwps if c.cwp_id == ids["a"])
            == next(c for c in found.cwps if c.cwp_id == ids["a"]),
        )
    check(
        "without the filter the figure is unfiltered",
        rr.read() == rr.read() and ids["b"] in {c.cwp_id for c in rr.read().cwps},
    )

    data = rr.export()
    r = rows_of(data)
    check(
        "a node without a stored budget exports an empty cell and the note",
        all(x[4] == "" for x in r[1:]) and "no budget rollup yet" in found.notes,
    )
    for title, old in (("=cmd|' /C calc'!A0", "4210-PIP-WLD"), ("+1", "4210-PIP-ERC")):
        with open_uow(w.db) as uow:
            uow.conn().execute(
                text("UPDATE cur_cost_costcode SET code = :c WHERE code = :o"),
                {"c": title, "o": old},
            )
    cells = [x[2] for x in rows_of(rr.export())]
    check(
        "= and + cells read back with a leading apostrophe",
        "'=cmd|' /C calc'!A0" in cells and "'+1" in cells,
    )
    for title, old in (("-1", "+1"), ("@SUM(A1)", "=cmd|' /C calc'!A0")):
        with open_uow(w.db) as uow:
            uow.conn().execute(
                text("UPDATE cur_cost_costcode SET code = :c WHERE code = :o"),
                {"c": title, "o": old},
            )
    cells = [x[2] for x in rows_of(rr.export())]
    check(
        "- and @ cells read back with a leading apostrophe", "'-1" in cells and "'@SUM(A1)" in cells
    )
    try:
        rr.export("2026-W54")
    except ExportError as exc:
        check(
            "a bad period is refused with the fixed text", str(exc) == "period: expected YYYY-Www"
        )
    else:
        check("a bad period is refused with the fixed text", False)
    rr.run_rollup()
    before = rr.counts()
    rr.export()
    check(
        "an export changes no cur_cost row, no stored figure and not the ledger head",
        rr.counts() == before,
    )


if __name__ == "__main__":
    main()
    print("S3 ok")
