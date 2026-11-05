"""Acceptance for P2-I3-T05b: the `tl mat` read verbs and `tl mat report` on the S3 seed ledger.

Copies ``.accept/p2-i3.db`` (written by ``dev/accept/P2-I3/S3.py --keep``) to a temp directory and
drives ``tl_cli.mat.app`` with ``typer.testing.CliRunner``, the copy as the ``DbTarget``. Prints
``PASS <check>`` for each check and exits 0; on the first failure prints ``FAIL <check>: <detail>``
and exits 1. Run from any directory:

    uv run python dev/accept/P2-I3/T05b.py
"""
# ruff: noqa
# pyright: basic, reportOptionalCall=false, reportArgumentType=false, reportAssignmentType=false
# pyright: reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportCallIssue=false

import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import text
from tl_adapters.db import DbTarget, as_target, open_uow
from tl_cli.mat import app as mat_app
from typer.testing import CliRunner, Result

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / ".accept" / "p2-i3.db"
PROJECT = "P123"
RECEIPT = "P123-RCPT-0001"
LOT = "P123-RCPT-0001@1"
WORK_PACKAGE = "P123-CWP-PIP-0001"
HEAT = "H-7781"
REPORT_CSV_HEADER = "Work package,Line,Item,UOM,Required,Reserved,Issued,Short"


class Failure(Exception):
    """One failed check; the message is printed after ``FAIL <check>:``."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


@dataclass
class Harness:
    target: DbTarget
    runner: CliRunner
    events_before: int = 0
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


def event_count(db: DbTarget) -> int:
    with open_uow(db, readonly=True) as uow:
        return int(uow.conn().execute(text("SELECT COUNT(*) FROM events")).scalar_one())


def check_stock_rows(h: Harness) -> None:
    result = h.run("stock", "--project", PROJECT)
    first = lines_of(result)[0]
    match = re.fullmatch(r"stock rows: (\d+)", first)
    expect(match is not None and int(match.group(1)) >= 2, f"stock header is {first!r}")
    expect(HEAT in result.stdout, f"heat {HEAT} does not appear in stock")


def check_stock_unknown_heat_zero(h: Harness) -> None:
    result = h.run("stock", "--project", PROJECT, "--heat", "H-0000")
    expect(lines_of(result)[0] == "stock rows: 0", f"first line {lines_of(result)[0]!r}")


def check_lot_shows_qty(h: Harness) -> None:
    result = h.run("lot", LOT, "--project", PROJECT)
    expect(any(line.startswith("qty ") for line in lines_of(result)), "no qty line for the lot")


def check_lot_unknown_is_error(h: Harness) -> None:
    result = h.run("lot", "P123-RCPT-9999@1", "--project", PROJECT, code=1)
    expect("error:" in result.stderr, f"stderr is {result.stderr[:200]!r}")


def check_movements_carry_date_and_kind(h: Harness) -> None:
    lines = lines_of(h.run("movements", "--project", PROJECT))
    expect(lines[0].startswith("movements: "), f"header is {lines[0]!r}")
    body = lines[1:]
    expect(len(body) > 0, "no movement lines")
    pattern = re.compile(r"\d{4}-\d{2}-\d{2}  [a-z]+  ")
    bad = [line for line in body if not pattern.match(line)]
    expect(not bad, f"movement line without <date>  <kind>: {bad[:1]}")


def check_receipt_list_has_receipt(h: Harness) -> None:
    lines = lines_of(h.run("receipt", "list", "--project", PROJECT))
    expect(any(line.startswith(f"{RECEIPT}  ") for line in lines), f"{RECEIPT} not listed")


def check_receipt_show_two_lines(h: Harness) -> None:
    lines = lines_of(h.run("receipt", "show", RECEIPT, "--project", PROJECT))
    count = sum(1 for line in lines if line.startswith("line "))
    expect(count == 2, f"receipt show has {count} line lines, want 2")


def check_loc_nine_lines(h: Harness) -> None:
    lines = lines_of(h.run("loc", "--project", PROJECT))
    expect(lines[0].startswith("locations: "), f"header is {lines[0]!r}")
    expect(len(lines) - 1 == 9, f"loc has {len(lines) - 1} lines under the header, want 9")


def check_po_fifteen(h: Harness) -> None:
    lines = lines_of(h.run("po", "--project", PROJECT))
    expect(len(lines) == 15, f"po has {len(lines)} lines, want 15")


def check_item_fifty_without_project(h: Harness) -> None:
    lines = lines_of(h.run("item"))
    expect(len(lines) == 50, f"item has {len(lines)} lines, want 50")


def check_mto_work_package_three(h: Harness) -> None:
    lines = lines_of(h.run("mto", "list", "--project", PROJECT, "--work-package", WORK_PACKAGE))
    expect(len(lines) == 3, f"mto list for {WORK_PACKAGE} has {len(lines)} lines, want 3")


def check_mto_short_only_positive(h: Harness) -> None:
    lines = lines_of(h.run("mto", "list", "--project", PROJECT, "--short-only"))
    expect(len(lines) > 0, "mto list --short-only has no lines")
    for line in lines:
        short = re.search(r"  short ([0-9.]+)  ", line)
        expect(short is not None and float(short.group(1)) > 0, f"not a short line: {line!r}")


def check_report_table_header(h: Harness) -> None:
    lines = lines_of(h.run("report", "stock_on_hand", "--project", PROJECT))
    expect(lines[0].split("  ")[0] == "Lot", f"table header is {lines[0]!r}")
    expect(lines[-1].startswith("rows: "), f"table does not end with rows: {lines[-1]!r}")


def check_report_shortages_csv_header(h: Harness) -> None:
    result = h.run("report", "shortages", "--project", PROJECT, "--format", "csv")
    expect(lines_of(result)[0] == REPORT_CSV_HEADER, f"csv first line is {lines_of(result)[0]!r}")


def check_report_heat_trace_needs_heat(h: Harness) -> None:
    h.run("report", "heat_trace", "--project", PROJECT, code=1)


def check_report_unknown_name(h: Harness) -> None:
    result = h.run("report", "nope", "--project", PROJECT, code=1)
    expect("error:" in result.stderr, f"stderr is {result.stderr[:200]!r}")


def check_no_none_in_output(h: Harness) -> None:
    for output in h.outputs:
        for line in output.splitlines():
            expect("None" not in line, f"output line contains None: {line!r}")


def check_no_verb_writes(h: Harness) -> None:
    after = event_count(h.target)
    expect(after == h.events_before, f"events went from {h.events_before} to {after}")


CHECKS: list[tuple[str, Callable[[Harness], None]]] = [
    ("stock header says 2 or more rows and H-7781 appears", check_stock_rows),
    ("stock --heat H-0000 prints stock rows: 0", check_stock_unknown_heat_zero),
    ("lot P123-RCPT-0001@1 shows a qty line and exits 0", check_lot_shows_qty),
    ("an unknown lot exits 1 with error:", check_lot_unknown_is_error),
    ("movements lines carry <date>  <kind>", check_movements_carry_date_and_kind),
    ("receipt list shows P123-RCPT-0001", check_receipt_list_has_receipt),
    ("receipt show P123-RCPT-0001 has 2 line lines", check_receipt_show_two_lines),
    ("loc has 9 lines under the header", check_loc_nine_lines),
    ("po has 15 lines", check_po_fifteen),
    ("item without --project has 50 lines", check_item_fifty_without_project),
    ("mto list for the work package has 3 lines", check_mto_work_package_three),
    ("mto list --short-only has only lines with short above 0", check_mto_short_only_positive),
    ("report stock_on_hand table starts with the Lot header", check_report_table_header),
    ("report shortages --format csv starts with the CSV header", check_report_shortages_csv_header),
    ("report heat_trace without --heat exits 1", check_report_heat_trace_needs_heat),
    ("report nope exits 1 with error:", check_report_unknown_name),
    ("no output line contains None", check_no_none_in_output),
    ("no verb writes: the event count is unchanged", check_no_verb_writes),
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
        harness.events_before = event_count(harness.target)
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
