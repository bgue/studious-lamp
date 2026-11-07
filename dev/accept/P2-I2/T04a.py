"""Acceptance for P2-I2-T04a: IWP and scope read views (awp ``iwp_views``). SQLite temp ledger."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "packages/tl-modules/awp/tests"))
sys.path.insert(0, str(Path(__file__).parent))
import t04a_checks as t  # noqa: E402
from awp_world import SCOPE  # noqa: E402
from tl_adapters.db import open_uow  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_mod_awp import iwp_views as v  # noqa: E402

PIP1, PIP2, CIV1 = "P123-IWP-PIP-0001", "P123-IWP-PIP-0002", "P123-IWP-CIV-0001"


def ok(name: str, cond: bool = True) -> None:
    sys.exit(f"FAIL {name}") if not cond else print(f"PASS {name}")


def read(w, fn, *args, viewer=cf.LOWEST, **kw):  # type: ignore[no-untyped-def]
    with open_uow(w.db, readonly=True) as uow, cf.use_viewer(viewer):
        return fn(uow.conn(), SCOPE, *args, **kw)


def numbers(rows) -> list[str]:  # type: ignore[no-untyped-def]
    return [r.number for r in rows]


def main(path: Path) -> None:
    w, ctx = t.build(path)
    ids = t.seed(w, ctx)
    cwp_key = w.column("cur_core_record", "key", ids["cwp"])
    ok("list: the 3 seed IWPs by number", numbers(read(w, v.iwp_list)) == [CIV1, PIP1, PIP2])
    ok("filter state", numbers(read(w, v.iwp_list, state="In development")) == [PIP2])
    ok("filter discipline", numbers(read(w, v.iwp_list, discipline="CIV")) == [CIV1])
    ok("filter foreman", numbers(read(w, v.iwp_list, foreman="user:uma")) == [PIP1])
    ok("limit clamped to 1..500", len(read(w, v.iwp_list, limit=0)) == 1)
    d1 = read(w, v.iwp_detail, PIP1)
    ok("detail: scope_count 40 and pin_count 2", (d1.scope_count, d1.pin_count) == (40, 2))
    ok("detail: cwp number named", d1.cwp_number == cwp_key)
    open_now = [read(w, v.iwp_detail, n).open_constraints for n in (PIP1, PIP2, CIV1)]
    ok("detail: open constraints (Open, Assigned)", open_now == [1, 1, 0])
    ok("scope_by_type sums to scope_count", sum(d1.scope_by_type.values()) == d1.scope_count)
    scope = read(w, v.iwp_scope, PIP1)
    ok("scope lists the 40 items", scope is not None and len(scope) == 40)
    ok("unknown number gives None", read(w, v.iwp_detail, "P123-IWP-PIP-9999") is None)
    ok("unknown scope gives None", read(w, v.iwp_scope, "P123-IWP-PIP-9999") is None)
    t.classed(w, {ids["i3"], ids["cwp"]})
    ok("hidden: absent from list", numbers(read(w, v.iwp_list)) == [PIP1, PIP2])
    ok(
        "hidden: detail and scope None",
        read(w, v.iwp_detail, CIV1) is None and read(w, v.iwp_scope, CIV1) is None,
    )
    ok("hidden equals never-existed", read(w, v.iwp_detail, CIV1) == read(w, v.iwp_detail, "X-9"))
    ok("hidden CWP gives cwp_number None", read(w, v.iwp_detail, PIP1).cwp_number is None)
    ok(
        "restricted viewer reads all three",
        len(read(w, v.iwp_list, viewer=t.RESTRICTED_VIEWER)) == 3,
    )
    ok(
        "restricted viewer names the CWP",
        read(w, v.iwp_detail, PIP1, viewer=t.RESTRICTED_VIEWER).cwp_number == cwp_key,
    )
    few = t.statements(w, lambda c: v.iwp_list(c, SCOPE))
    for _ in range(27):
        w.iwp()
    many = t.statements(w, lambda c: v.iwp_list(c, SCOPE))
    ok("list statement count flat for 3 and 30 IWPs", few == many)
    print("T04a ok")


if __name__ == "__main__":
    main(Path(tempfile.mkdtemp()) / "t04a.db")
