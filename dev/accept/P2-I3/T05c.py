"""Acceptance for P2-I3-T05c: the `tl mat` write verbs on the S3 seed ledger.

Copies ``.accept/p2-i3.db`` (written by ``dev/accept/P2-I3/S3.py --keep``) to a temp directory and
drives ``tl_cli.mat.app`` with ``typer.testing.CliRunner``, the copy as the ``DbTarget``. Prints
``PASS <check>`` for each check and exits 0; on the first failure prints ``FAIL <check>: <detail>``
and exits 1. Run from any directory:

    uv run python dev/accept/P2-I3/T05c.py

The write verbs need a dev setting for the seed's actors: ``main`` sets ``TL_ENV`` to ``dev``
when it is unset, as the justfile does, so ``user:materials-super`` holds the ``user`` word on the
file ledger.
"""

import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from tl_adapters.db import DbTarget, as_target, open_uow
from tl_cli.mat import app as mat_app
from tl_core.ledger import NewEvent
from tl_core.util import new_ulid
from tl_mod_materials import views
from typer.testing import CliRunner, Result

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / ".accept" / "p2-i3.db"
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
SUPER = "user:materials-super"
PLAIN = "user:plain"
LOT1 = "P123-RCPT-0001@1"  # 12 flange at L2 (seed), heat H-7781
FLANGE = "FLG-WN-6-150-A105"
ELBOW = "ELB-LR-90-6-SCH40"
PIPE = "PIPE-CS-6-SCH40-A106"
LINE_FLANGE = "ISO-1234@A/MTO/001"  # 20 EA, reserved by nothing at the seed
LINE_ELBOW = "ISO-1234@A/MTO/002"
LINE_PIPE = "ISO-1234@A/MTO/003"
WP_SEED = "P123-CWP-PIP-0001"
WP_NEW = "P123-CWP-PIP-0002"  # made by this script in the copy: the seed has one work package
BAD_LINE = "X"

STOCK_ROW = re.compile(
    r"^(?P<lot>\S+)  (?P<heat>\S+)  (?P<item>\S+)  (?P<loc>\S+)  on hand (?P<on>\S+)  "
    r"reserved (?P<res>\S+)  available (?P<av>\S+)  "
)
LOT_QTY = re.compile(r"^qty (?P<loc>\S+)  on hand (?P<on>\S+)  reserved (?P<res>\S+)  ")


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
            "Traceback" not in result.output,
            f"tl mat {' '.join(args)} printed a traceback: {result.output[-200:]}",
        )
        expect(
            result.exit_code == code,
            f"tl mat {' '.join(args)} exits {result.exit_code}, want {code}: {result.output[:300]}",
        )
        return result

    def write(self, *args: str, code: int = 0, actor: str = SUPER) -> Result:
        """A write verb: the project and the actor are added."""
        return self.run(*args, "--project", PROJECT, "--actor", actor, code=code)

    def read(self, *args: str, code: int = 0) -> Result:
        return self.run(*args, "--project", PROJECT, code=code)


def lines_of(result: Result) -> list[str]:
    return result.stdout.splitlines()


def event_count(db: DbTarget) -> int:
    with open_uow(db, readonly=True) as uow:
        return int(uow.conn().execute(text("SELECT COUNT(*) FROM events")).scalar_one())


def dec(value: str) -> Decimal:
    return Decimal(value)


def on_hand(h: Harness, lot: str, location: str) -> Decimal:
    """The on-hand quantity of ``lot`` at ``location`` in the stock listing (0 when no row)."""
    for line in lines_of(h.read("stock", "--lot", lot)):
        match = STOCK_ROW.match(line)
        if match and match.group("loc") == location:
            return dec(match.group("on"))
    return Decimal(0)


def lot_reserved_at(h: Harness, lot: str, location: str) -> Decimal:
    """The reserved quantity of ``lot`` at ``location`` in the lot view (0 when no balance)."""
    for line in lines_of(h.read("lot", lot)):
        match = LOT_QTY.match(line)
        if match and match.group("loc") == location:
            return dec(match.group("res"))
    return Decimal(0)


def mto_line_id(db: DbTarget, key: str) -> str:
    with open_uow(db, readonly=True) as uow:
        for line in views.mto_lines(uow.conn(), SCOPE):
            if line.key == key:
                return line.id
    raise Failure(f"no take-off line {key} in {SCOPE}")


def make_work_package(db: DbTarget, number: str) -> None:
    """A second work package of the project, in the copy (the seed has only one)."""
    with open_uow(db) as uow:
        uow.append(
            stream_id=new_ulid(),
            stream_type="awp.CWP",
            scope=SCOPE,
            expected_version=0,
            events=[
                NewEvent(
                    event_type="Record.Created",
                    payload={
                        "record_type": "awp.CWP",
                        "key": number,
                        "title": "Piping package 2",
                        "description": None,
                        "psets": {},
                    },
                )
            ],
            actor=SUPER,
            source="cli",
            correlation_id=new_ulid(),
        )


# --- the checks: each one writes after the one before it --------------------------------------


def check_receive_inspect_accept(h: Harness) -> None:
    made = h.write(
        "receipt",
        "receive",
        "--location",
        "L3",
        "--received-on",
        "2026-11-03",
        "--line",
        f"{ELBOW}:6",
        "--line",
        f"{PIPE}:12.5:H-7791:good",
    )
    expect(lines_of(made) == ["received P123-RCPT-0002  2 lines"], f"receive says {made.output!r}")
    listed = lines_of(h.read("receipt", "list"))
    expect(
        any(line.startswith("P123-RCPT-0002  Received  ") for line in listed),
        "P123-RCPT-0002 is not listed as Received",
    )
    inspected = h.write("receipt", "inspect", "P123-RCPT-0002", "--notes", "counted")
    expect(lines_of(inspected) == ["P123-RCPT-0002 is Inspected"], inspected.output)
    accepted = h.write("receipt", "accept", "P123-RCPT-0002")
    expect(lines_of(accepted) == ["P123-RCPT-0002 is Accepted"], accepted.output)
    expect(on_hand(h, "P123-RCPT-0002@1", "L3") == dec("6"), "the new lot is not 6 at L3")


def check_reject_and_void(h: Harness) -> None:
    second = h.write(
        "receipt",
        "receive",
        "--location",
        "L3",
        "--received-on",
        "2026-11-03",
        "--line",
        f"{ELBOW}:1",
    )
    expect(lines_of(second) == ["received P123-RCPT-0003  1 lines"], second.output)
    rejected = h.write("receipt", "reject", "P123-RCPT-0003", "--reason", "wrong heat")
    expect(lines_of(rejected) == ["P123-RCPT-0003 is Rejected"], rejected.output)
    third = h.write(
        "receipt",
        "receive",
        "--location",
        "L3",
        "--received-on",
        "2026-11-03",
        "--line",
        f"{ELBOW}:1",
    )
    expect(lines_of(third) == ["received P123-RCPT-0004  1 lines"], third.output)
    voided = h.write("receipt", "void", "P123-RCPT-0004", "--reason", "booked in error")
    expect(lines_of(voided) == ["P123-RCPT-0004 is Void"], voided.output)


def check_transfer_and_issue_refused(h: Harness) -> None:
    before_l2 = on_hand(h, LOT1, "L2")
    before_l3 = on_hand(h, LOT1, "L3")
    moved = h.write(
        "move",
        "transfer",
        "--lot",
        LOT1,
        "--qty",
        "2.000",
        "--uom",
        "EA",
        "--from",
        "L2",
        "--to",
        "L3",
    )
    expect(lines_of(moved) == [f"transfer 2.000 EA lot {LOT1}"], f"transfer says {moved.output!r}")
    expect(on_hand(h, LOT1, "L2") == before_l2 - 2, "L2 did not give 2")
    expect(on_hand(h, LOT1, "L3") == before_l3 + 2, "L3 did not take 2")
    refused = h.write(
        "move", "issue", "--lot", LOT1, "--qty", "1000", "--uom", "EA", "--from", "L2", code=1
    )
    expect("error:" in refused.stderr, f"stderr is {refused.stderr[:200]!r}")


def check_reserve_then_unreserve(h: Harness) -> None:
    line_id = mto_line_id(h.target, LINE_FLANGE)
    before = lot_reserved_at(h, LOT1, "L2")
    reserved = h.write(
        "move",
        "reserve",
        "--lot",
        LOT1,
        "--qty",
        "4",
        "--uom",
        "EA",
        "--from",
        "L2",
        "--for-line",
        line_id,
    )
    expect(lines_of(reserved) == [f"reserve 4 EA lot {LOT1}"], reserved.output)
    expect(lot_reserved_at(h, LOT1, "L2") == before + 4, "the reserve did not show in lot")
    freed = h.write(
        "move",
        "unreserve",
        "--lot",
        LOT1,
        "--qty",
        "4",
        "--uom",
        "EA",
        "--from",
        "L2",
        "--for-line",
        line_id,
    )
    expect(lines_of(freed) == [f"unreserve 4 EA lot {LOT1}"], freed.output)
    expect(lot_reserved_at(h, LOT1, "L2") == before, "the unreserve did not show in lot")


def check_mto_assign(h: Harness) -> None:
    line_id = mto_line_id(h.target, LINE_FLANGE)
    held = h.write(
        "move",
        "reserve",
        "--lot",
        LOT1,
        "--qty",
        "1",
        "--uom",
        "EA",
        "--from",
        "L2",
        "--for-line",
        line_id,
    )
    expect(lines_of(held) == [f"reserve 1 EA lot {LOT1}"], held.output)
    refused = h.write("mto", "assign", LINE_FLANGE, "--work-package", WP_NEW, code=1)
    expect("error:" in refused.stderr, f"stderr is {refused.stderr[:200]!r}")
    done = h.write("mto", "assign", LINE_PIPE, "--work-package", WP_NEW)
    expect(lines_of(done) == [f"assigned 1 lines to {WP_NEW}"], done.output)
    listed = lines_of(h.read("mto", "list", "--work-package", WP_NEW))
    expect(
        any(line.startswith(f"{LINE_PIPE}  ") for line in listed), f"pipe line not listed: {listed}"
    )


def check_bad_line_writes_nothing(h: Harness) -> None:
    before = event_count(h.target)
    bad = h.write(
        "receipt",
        "receive",
        "--location",
        "L3",
        "--received-on",
        "2026-11-03",
        "--line",
        BAD_LINE,
        code=1,
    )
    expect("error:" in bad.stderr, f"stderr is {bad.stderr[:200]!r}")
    after = event_count(h.target)
    expect(after == before, f"events went from {before} to {after}")


def check_plain_user_refused(h: Harness) -> None:
    refused = h.run(
        "receipt",
        "receive",
        "--location",
        "L3",
        "--received-on",
        "2026-11-03",
        "--line",
        f"{ELBOW}:1",
        "--project",
        PROJECT,
        "--actor",
        PLAIN,
        code=1,
    )
    expect("forbidden" in refused.stderr, f"stderr is {refused.stderr[:200]!r}")


CHECKS: list[tuple[str, Callable[[Harness], None]]] = [
    (
        "receipt receive two lines, list Received, inspect and accept, stock shows the lot",
        check_receive_inspect_accept,
    ),
    (
        "a receipt rejected with --reason ends Rejected; a third voided ends Void",
        check_reject_and_void,
    ),
    (
        "move transfer moves 2 EA from L2 to L3; move issue over on-hand exits 1 with error:",
        check_transfer_and_issue_refused,
    ),
    (
        "reserve then unreserve of a take-off line changes the lot view",
        check_reserve_then_unreserve,
    ),
    (
        "mto assign: a reserved line exits 1, a line with no stock goes to the work package",
        check_mto_assign,
    ),
    ("a bad --line exits 1 and the event count is unchanged", check_bad_line_writes_nothing),
    ("the plain user is refused on receipt receive (materials.receive)", check_plain_user_refused),
]


def main() -> int:
    os.environ.setdefault("TL_ENV", "dev")
    if not LEDGER.exists():
        print(f"FAIL ledger: {LEDGER} is missing (run dev/accept/P2-I3/S3.py --keep first)")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "tl.db"
        for src in LEDGER.parent.glob(LEDGER.name + "*"):  # the ledger and any WAL sidecars
            shutil.copy(src, root / ("tl.db" + src.name[len(LEDGER.name) :]))
        target = as_target(db)
        make_work_package(target, WP_NEW)
        harness = Harness(target, CliRunner())
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
