"""Acceptance for P2-I3-T05d: `tl mat mto show` and `tl mat item-projects` on the S3 seed ledger.

Copies ``.accept/p2-i3.db`` (written by ``dev/accept/P2-I3/S3.py --keep``) to a temp directory and
drives ``tl_cli.mat.app`` with ``typer.testing.CliRunner``, the copy as the ``DbTarget``. Check 2
posts one reservation on the copy with ``handle_reserve_stock``, the way S3 does. Prints
``PASS <check>`` for each check and exits 0; on the first failure prints ``FAIL <check>: <detail>``
and exits 1. Run from any directory:

    uv run python dev/accept/P2-I3/T05d.py
"""

import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, as_target, open_uow
from tl_cli.mat import app as mat_app
from tl_mod_materials.handlers.movements import Movement, ReserveStock, handle_reserve_stock
from typer.testing import CliRunner, Result

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / ".accept" / "p2-i3.db"
PROJECT = "P123"
SCOPE = "project:P123"
LOT = "P123-RCPT-0001@1"
ACTOR = "user:accept"
SOURCE = "accept"


class Failure(Exception):
    """One failed check; the message is printed after ``FAIL <check>:``."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


@dataclass
class Harness:
    target: DbTarget
    runner: CliRunner
    outputs: list[str] = field(default_factory=list)

    def run(self, *args: str, code: int = 0) -> Result:
        result = self.runner.invoke(mat_app, list(args), obj=self.target)
        self.outputs.append(result.output)
        expect(
            result.exit_code == code,
            f"tl mat {' '.join(args)} exits {result.exit_code}, want {code}: {result.output[:200]}",
        )
        return result


def lines_of(result: Result) -> list[str]:
    return result.stdout.splitlines()


def query_one(target: DbTarget, sql: str, **params: Any) -> dict[str, Any]:
    """The one row of a read-only query on the copy, as a dict."""
    with open_uow(target, readonly=True) as uow:
        rows = [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]
    expect(len(rows) == 1, f"query found {len(rows)} rows, want 1: {sql[:80]}")
    return rows[0]


def first_line_key(h: Harness) -> str:
    """The key of the first take-off line `mto list` prints for the project."""
    lines = lines_of(h.run("mto", "list", "--project", PROJECT))
    expect(len(lines) > 0, "mto list has no lines")
    return lines[0].split("  ")[0]


def check_mto_show_no_reservation(h: Harness) -> None:
    key = first_line_key(h)
    lines = lines_of(h.run("mto", "show", key, "--project", PROJECT))
    expect(lines[0].startswith(f"{key}  "), f"head line is {lines[0]!r}")
    expect(lines[1] == "no reservations", f"second line is {lines[1]!r}")
    rest = lines[2:]
    expect(
        rest == ["no open receipts"]
        or (len(rest) > 0 and all(r.startswith("receipt ") for r in rest)),
        f"receipt lines are {rest!r}",
    )


def check_reserve_then_mto_show_reserved(h: Harness) -> None:
    line = query_one(
        h.target,
        "SELECT lr.id AS id, lr.key AS key FROM cur_materials_mto_line l "
        "JOIN cur_core_record lr ON lr.id = l.id "
        "JOIN cur_materials_lot lot ON lot.project_item_id = l.project_item_id "
        "JOIN cur_core_record lo ON lo.id = lot.id "
        "WHERE lo.key = :lot AND lr.scope = :scope",
        lot=LOT,
        scope=SCOPE,
    )
    lot = query_one(
        h.target,
        "SELECT lot.uom AS uom FROM cur_materials_lot lot "
        "JOIN cur_core_record lo ON lo.id = lot.id WHERE lo.key = :lot",
        lot=LOT,
    )
    where = query_one(
        h.target,
        "SELECT loc.key AS code FROM cur_materials_stock st "
        "JOIN cur_core_record loc ON loc.id = st.location_id "
        "JOIN cur_core_record lo ON lo.id = st.lot_id "
        "WHERE lo.key = :lot AND st.on_hand > 0",
        lot=LOT,
    )
    command = ReserveStock(
        actor=ACTOR,
        source=SOURCE,
        scope=SCOPE,
        movements=[
            Movement(
                lot_key=LOT,
                qty="2.000",
                uom=str(lot["uom"]),
                from_location=str(where["code"]),
                mto_line_id=str(line["id"]),
            )
        ],
    )
    with open_uow(h.target) as uow:
        handle_reserve_stock(uow, command)
    result = h.run("mto", "show", str(line["key"]), "--project", PROJECT)
    reserved = [x for x in lines_of(result) if x.startswith("reserved ")]
    expect(len(reserved) == 1, f"reserved lines are {reserved!r}, want one")
    expect(
        reserved[0].startswith(f"reserved {LOT}  {where['code']}  2"),
        f"reserved line is {reserved[0]!r}",
    )
    expect("no reservations" not in lines_of(result), "mto show still says no reservations")


def check_mto_show_unknown_key(h: Harness) -> None:
    result = h.run("mto", "show", "ISO-9999@A/MTO/999", "--project", PROJECT, code=1)
    expect("error:" in result.stderr, f"stderr is {result.stderr[:200]!r}")
    expect("Traceback" not in result.output, "a traceback was printed")


def check_item_projects_seed_item(h: Harness) -> None:
    code = query_one(
        h.target,
        "SELECT ir.key AS code FROM cur_materials_mto_line l "
        "JOIN cur_core_record lr ON lr.id = l.id "
        "JOIN cur_core_record ir ON ir.id = l.project_item_id "
        "WHERE lr.scope = :scope ORDER BY lr.key LIMIT 1",
        scope=SCOPE,
    )["code"]
    lines = lines_of(h.run("item-projects", str(code)))
    expect(lines[0] == f"item {code}  projects: 1", f"header is {lines[0]!r}")
    expect(
        len(lines) == 2 and lines[1].startswith(f"{PROJECT}  on hand "),
        f"project lines are {lines[1:]!r}",
    )


def check_item_projects_unknown_code(h: Harness) -> None:
    result = h.run("item-projects", "NOPE-0000")
    expect(
        lines_of(result) == ["no projects for item NOPE-0000"],
        f"output is {result.stdout[:200]!r}",
    )


def check_mto_ls_alias(h: Harness) -> None:
    h.run("mto", "ls", "--project", PROJECT)


def check_receipt_ls_alias(h: Harness) -> None:
    h.run("receipt", "ls", "--project", PROJECT)


CHECKS: list[tuple[str, Callable[[Harness], None]]] = [
    (
        "mto show of a seed line prints the head line, no reservations, then receipts",
        check_mto_show_no_reservation,
    ),
    (
        "a reservation posted by the handler shows as a reserved line",
        check_reserve_then_mto_show_reserved,
    ),
    ("an unknown take-off line exits 1 with error: and no traceback", check_mto_show_unknown_key),
    (
        "item-projects of a seed item prints projects: 1 and the P123 line",
        check_item_projects_seed_item,
    ),
    (
        "item-projects of an unknown code prints no projects for item, exit 0",
        check_item_projects_unknown_code,
    ),
    ("tl mat mto ls --project P123 exits 0", check_mto_ls_alias),
    ("tl mat receipt ls --project P123 exits 0", check_receipt_ls_alias),
]


def main() -> int:
    if not LEDGER.exists():
        print(f"FAIL ledger: {LEDGER} is missing (run dev/accept/P2-I3/S3.py --keep first)")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "tl.db"
        for src in LEDGER.parent.glob(LEDGER.name + "*"):  # the ledger and any WAL sidecars
            shutil.copy(src, root / ("tl.db" + src.name[len(LEDGER.name) :]))
        harness = Harness(as_target(db), CliRunner())
        for name, check in CHECKS:
            try:
                check(harness)
            except Failure as exc:
                print(f"FAIL {name}: {exc}")
                return 1
            except Exception as exc:  # an unexpected error is a failed check too
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
                return 1
            print(f"PASS {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
