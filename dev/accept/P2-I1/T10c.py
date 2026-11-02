"""Acceptance for P2-I1-T10c: the view fields the logs show (allocated, package title and CWPs,
WBS CWP count, leaf CWP list).

Run: ``uv run python dev/accept/P2-I1/T10c.py --db PATH`` (PATH is the seed from ``S4.py --keep``).
The seed stays untouched: the script copies it, records one EWP and links it from two CWPs on the
copy, retracts one link, then reads the views. Prints ``PASS <check>`` per check, then ``T10c ok``;
exits 1 on the first failure.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, text
from tl_adapters.db import as_target, open_uow
from tl_core.auth.module_roles import require_command_access
from tl_core.services.links import AddLink, RetractLink, handle_add_link, handle_retract_link
from tl_mod_awp import views
from tl_mod_awp.commands import AWP_COMMANDS

SCOPE = "project:P123"
PACKAGE_NO = "EWP-0901"
SPEC = {c.model.__name__: c for c in AWP_COMMANDS}


class Failed(Exception):
    pass


def need(ok: bool, what: str) -> None:
    if not ok:
        raise Failed(what)


def passed(check: str) -> None:
    print(f"PASS {check}")


def record_package(target: Any, number: str) -> None:
    """Record an EWP as Uma does: the access word is checked, then the handler runs."""
    spec = SPEC["RecordExternalPackage"]
    fields: dict[str, Any] = {
        "package_type": "ewp",
        "package_no": number,
        "title": f"Package {number}",
        "constraint_source": False,
    }
    cmd = spec.model(actor="user:uma", source="accept", scope=SCOPE, **fields)
    with open_uow(target) as uow:
        require_command_access(uow.conn(), cmd)
        spec.handler(uow, cmd)


def prepare(target: Any) -> None:
    """Shape the copy so both cases exist. The seed has six CWPs, each allocated to one leaf, so
    the copy gets one CWP with no allocation (``CreateCwp``) and one allocated CWP split 50/50
    over two leaves (``AllocateCwpToWbs``), so a CWP on two leaves is counted once."""
    with open_uow(target, readonly=True) as uow:
        conn = uow.conn()
        tree = views.wbs_tree(conn, SCOPE)
        victim = next(r for r in views.cwp_list(conn, SCOPE) if r.allocated)
        current = allocations_of(conn, victim.number)[0].wbs_code
        others = [r.code for r in leaves_of(tree) if not r.retired and r.code != current]
    need(bool(others), "the seed has no second leaf to allocate to")
    fields: dict[str, Any] = {"discipline": "PIP", "title": "Unallocated T10c", "cwa_code": "A1"}
    created = SPEC["CreateCwp"].model(actor="user:uma", source="accept", scope=SCOPE, **fields)
    with open_uow(target) as uow:
        require_command_access(uow.conn(), created)
        SPEC["CreateCwp"].handler(uow, created)
    split: dict[str, Any] = {
        "cwp": victim.id,
        "allocations": [
            {"wbs_code": current, "percent": "50.00"},
            {"wbs_code": others[0], "percent": "50.00"},
        ],
    }
    moved = SPEC["AllocateCwpToWbs"].model(actor="user:uma", source="accept", scope=SCOPE, **split)
    with open_uow(target) as uow:
        require_command_access(uow.conn(), moved)
        SPEC["AllocateCwpToWbs"].handler(uow, moved)


def package_id(conn: Connection, number: str) -> str:
    return str(
        conn.execute(
            text("SELECT id FROM cur_core_record WHERE scope = :s AND key = :k"),
            {"s": SCOPE, "k": f"awp.ewp@{number}"},
        ).scalar_one()
    )


def link_requires(target: Any, cwp_id: str, package: str) -> None:
    with open_uow(target) as uow:
        handle_add_link(
            uow,
            AddLink(
                actor="user:uma",
                source="accept",
                scope=SCOPE,
                from_id=cwp_id,
                to_id=package,
                relation="requires",
            ),
        )


def retract_link(target: Any, cwp_id: str, package: str) -> None:
    with open_uow(target, readonly=True) as uow:
        link_id = str(
            uow.conn()
            .execute(
                text(
                    "SELECT link_id FROM cur_links WHERE from_id = :c AND to_id = :p "
                    "AND relation = 'requires' AND status <> 'retracted'"
                ),
                {"c": cwp_id, "p": package},
            )
            .scalar_one()
        )
    with open_uow(target) as uow:
        handle_retract_link(
            uow,
            RetractLink(
                actor="user:uma", source="accept", scope=SCOPE, link_id=link_id, reason="test"
            ),
        )


def hours_of(budget: Decimal | None, percent: Decimal) -> Decimal | None:
    if budget is None:
        return None
    return (budget * percent / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def subtree_codes(tree: list[views.WbsRow], index: int) -> list[str]:
    """The codes of the node at ``index`` and of its descendants (the tree is depth-first)."""
    depth = tree[index].depth
    codes = [tree[index].code]
    for row in tree[index + 1 :]:
        if row.depth <= depth:
            break
        codes.append(row.code)
    return codes


def allocations_of(conn: Connection, number: str) -> list[views.CwpAllocation]:
    detail = views.cwp_detail(conn, SCOPE, number)
    need(detail is not None, f"{number} is listed but has no detail")
    return [] if detail is None else detail.allocations


def allocation_map(conn: Connection) -> dict[str, set[str]]:
    """WBS code to the CWP numbers allocated to it, read through ``cwp_detail``."""
    by_code: dict[str, set[str]] = {}
    for row in views.cwp_list(conn, SCOPE):
        for alloc in allocations_of(conn, row.number):
            by_code.setdefault(alloc.wbs_code, set()).add(row.number)
    return by_code


def leaves_of(tree: list[views.WbsRow]) -> list[views.WbsRow]:
    parents = {r.parent_code for r in tree if r.parent_code is not None}
    return [r for r in tree if r.code not in parents]


def check(db: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "t10c-seed.db"
        shutil.copyfile(db, copy)
        target = as_target(str(copy))
        prepare(target)

        # (1) allocated agrees with cwp_detail on the seed
        with open_uow(target, readonly=True) as uow:
            conn = uow.conn()
            rows = views.cwp_list(conn, SCOPE)
            need(len(rows) >= 2, "the seed has fewer than two CWPs")
            flags = [r.allocated for r in rows]
            need(any(flags) and not all(flags), f"seed allocated flags are {flags}")
            for row in rows:
                need(
                    row.allocated == bool(allocations_of(conn, row.number)),
                    f"{row.number}: allocated {row.allocated} disagrees with cwp_detail",
                )
            allocated_before = sum(flags)
        passed("cwp_list allocated equals bool(cwp_detail allocations) for every CWP")

        # (2) one EWP linked from two CWPs: title and cwps; each CWP detail agrees
        with open_uow(target, readonly=True) as uow:
            rows = views.cwp_list(uow.conn(), SCOPE)
        first = next(r for r in rows if r.allocated)
        second = next(r for r in rows if r.number != first.number)
        numbers = sorted([first.number, second.number])
        record_package(target, PACKAGE_NO)
        with open_uow(target, readonly=True) as uow:
            pkg_id = package_id(uow.conn(), PACKAGE_NO)
        link_requires(target, first.id, pkg_id)
        link_requires(target, second.id, pkg_id)

        with open_uow(target, readonly=True) as uow:
            conn = uow.conn()
            found = [p for p in views.package_list(conn, SCOPE) if p.id == pkg_id]
            need(len(found) == 1, "the recorded EWP is not in package_list")
            pkg = found[0]
            need(pkg.title == f"Package {PACKAGE_NO}", f"title is {pkg.title!r}")
            need(pkg.cwps == numbers, f"package cwps {pkg.cwps} != {numbers}")
            for number in numbers:
                detail = views.cwp_detail(conn, SCOPE, number)
                need(detail is not None, f"{number} has no detail")
                assert detail is not None
                mine = [p for p in detail.packages if p.id == pkg_id]
                need(len(mine) == 1, f"{number} detail does not name the package")
                need(
                    mine[0].title == pkg.title and mine[0].cwps == pkg.cwps,
                    f"{number} detail package differs from package_list",
                )
        passed("package_list title and cwps (sorted) agree with cwp_detail.packages")

        # (3) retracting one link leaves one CWP, and that CWP's detail no longer names it
        retract_link(target, second.id, pkg_id)
        with open_uow(target, readonly=True) as uow:
            conn = uow.conn()
            pkg = next(p for p in views.package_list(conn, SCOPE) if p.id == pkg_id)
            need(pkg.cwps == [first.number], f"after retract cwps are {pkg.cwps}")
            gone = views.cwp_detail(conn, SCOPE, second.number)
            need(gone is not None, f"{second.number} has no detail")
            assert gone is not None
            need(
                all(p.id != pkg_id for p in gone.packages),
                f"{second.number} still names the package after the retract",
            )
        passed("after retracting one link the package names one CWP")

        # (4) a leaf's cwps are the CWPs whose detail allocates to it, with percent and hours
        with open_uow(target, readonly=True) as uow:
            conn = uow.conn()
            tree = views.wbs_tree(conn, SCOPE)
            by_code = allocation_map(conn)
            leaves = leaves_of(tree)
            leaf_codes = {r.code for r in leaves}
            need(any(by_code.get(code) for code in leaf_codes), "no leaf has a CWP allocation")
            for leaf in leaves:
                detail = views.wbs_detail(conn, SCOPE, leaf.code)
                need(detail is not None, f"leaf {leaf.code} has no detail")
                assert detail is not None
                expected = sorted(
                    (a.wbs_code, n, a.percent)
                    for n in by_code.get(leaf.code, set())
                    for a in allocations_of(conn, n)
                    if a.wbs_code == leaf.code
                )
                got = sorted((leaf.code, w.number, w.percent) for w in detail.cwps)
                need(got == expected, f"leaf {leaf.code}: cwps {got} != {expected}")
                for w in detail.cwps:
                    cwp = views.cwp_detail(conn, SCOPE, w.number)
                    need(cwp is not None, f"{w.number} has no detail")
                    assert cwp is not None
                    need(
                        w.hours == hours_of(cwp.budget_hours, w.percent),
                        f"leaf {leaf.code}: {w.number} hours {w.hours}",
                    )
            for row in tree:
                if row.code not in leaf_codes:
                    detail = views.wbs_detail(conn, SCOPE, row.code)
                    need(detail is not None and detail.cwps == [], f"{row.code} lists cwps")
        passed("a leaf's cwps equal its allocations with percent and hours; a parent lists none")

        # (5) a parent's cwp_count is the distinct CWPs over its subtree; depth=1 and detail agree
        with open_uow(target, readonly=True) as uow:
            conn = uow.conn()
            tree = views.wbs_tree(conn, SCOPE)
            by_code = allocation_map(conn)
            for index, row in enumerate(tree):
                expected_set: set[str] = set()
                for code in subtree_codes(tree, index):
                    expected_set |= by_code.get(code, set())
                need(
                    row.cwp_count == len(expected_set),
                    f"{row.code}: cwp_count {row.cwp_count} != {len(expected_set)}",
                )
                detail = views.wbs_detail(conn, SCOPE, row.code)
                need(detail is not None, f"{row.code} has no detail")
                assert detail is not None
                need(detail.cwp_count == row.cwp_count, f"{row.code}: detail count differs")
            top = views.wbs_tree(conn, SCOPE, depth=1)
            need(len(top) == 1, "depth=1 keeps the top node alone")
            need(
                top[0].cwp_count == tree[0].cwp_count,
                "depth=1 count differs from the full tree",
            )
            need(any(r.cwp_count > 0 for r in tree), "no node has a CWP in its subtree")
        passed("a parent's cwp_count is the distinct CWPs over its subtree; depth=1 agrees")

        # (6) with _hidden hiding one allocated CWP it vanishes from the counts and the names
        with open_uow(target, readonly=True) as uow:
            conn = uow.conn()
            victim = next(r for r in views.cwp_list(conn, SCOPE) if r.allocated)
            victim_codes = {a.wbs_code for a in allocations_of(conn, victim.number)}
            tree_before = views.wbs_tree(conn, SCOPE)
            count_before = {r.code: r.cwp_count for r in tree_before}
            pkg_before = next(p for p in views.package_list(conn, SCOPE) if p.id == pkg_id)
            real_hidden = views._hidden

            def hiding(conn_: Connection, ids: set[str]) -> set[str]:
                return set(real_hidden(conn_, ids)) | {victim.id}

            views._hidden = hiding
            try:
                rows_after = views.cwp_list(conn, SCOPE)
                need(
                    all(r.number != victim.number for r in rows_after),
                    "the hidden CWP is still listed",
                )
                need(
                    sum(r.allocated for r in rows_after) == allocated_before - 1,
                    "allocated count did not drop by the hidden CWP",
                )
                pkg_after = next(p for p in views.package_list(conn, SCOPE) if p.id == pkg_id)
                need(
                    victim.number not in pkg_after.cwps,
                    f"hidden CWP still named by the package: {pkg_after.cwps}",
                )
                need(
                    pkg_after.cwps == [n for n in pkg_before.cwps if n != victim.number],
                    "package cwps changed by more than the hidden CWP",
                )
                tree_after = views.wbs_tree(conn, SCOPE)
                for index, row in enumerate(tree_after):
                    removed = 1 if victim_codes & set(subtree_codes(tree_after, index)) else 0
                    need(
                        row.cwp_count == count_before[row.code] - removed,
                        f"{row.code}: cwp_count {row.cwp_count} after hiding",
                    )
                for row in leaves_of(tree_after):
                    detail = views.wbs_detail(conn, SCOPE, row.code)
                    need(detail is not None, f"{row.code} has no detail")
                    assert detail is not None
                    need(
                        all(w.number != victim.number for w in detail.cwps),
                        f"{row.code} still names the hidden CWP",
                    )
            finally:
                views._hidden = real_hidden
        passed("with a CWP hidden it vanishes from allocated, cwps and cwp_count")

    print("T10c ok")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="the seed ledger (S4.py --keep)")
    args = parser.parse_args()
    try:
        check(args.db)
    except Failed as exc:
        print(f"FAIL {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
