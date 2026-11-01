"""Acceptance for P2-I3-T01b: the three materials loaders run on the T01a sample files.

Runs the stages of ``tl load`` (open, extract, profile, bronze, plan, load, reconcile) through
``LoadService`` on a temp SQLite ledger and a temp lake. Prints ``PASS <check>`` for each check and
exits 0; on the first failure prints ``FAIL <check>: <detail>`` and exits 1. Run from any directory:

    uv run python dev/accept/P2-I3/T01b.py
"""

import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from tl_adapters.db import as_target, create_schema
from tl_lake import LakeConfig
from tl_mod_legacy.errors import LoadRefusedError
from tl_mod_legacy.model import load_loaders
from tl_mod_legacy.testing import ADMIN, PROJECT, LegacyWorld

ROOT = Path(__file__).resolve().parents[3]
SAMPLES = ROOT / "packages/tl-modules/materials/src/tl_mod_materials/samples"
COMPANY = "company"
TARGETS = {
    "mat-items": "materials_item_master",
    "mat-locations": "materials_location",
    "mat-po-lines": "materials_po_line",
}


class Failure(Exception):
    """One failed check; the message is printed after ``FAIL <check>:``."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def sample(name: str) -> bytes:
    return (SAMPLES / name).read_bytes()


def to_plan(w: LegacyWorld, scope: str, loader: str, name: str, data: bytes):
    """The CLI stages open, extract, profile, bronze and plan; returns (run, plan)."""
    run = w.service.open(scope, loader, name, data, actor=ADMIN)
    w.service.extract(scope, run.id, actor=ADMIN)
    w.service.profile(scope, run.id, actor=ADMIN)
    w.service.bronze(scope, run.id, actor=ADMIN, include_confidential=True)
    return w.service.plan(scope, run.id, actor=ADMIN)


def check_loaders_found(w: LegacyWorld, state: dict) -> None:
    found = load_loaders()
    for name, target in TARGETS.items():
        expect(name in found, f"loader {name} is not found by load_loaders()")
        expect(found[name].target == target, f"{name} targets {found[name].target}")


def check_items_plan(w: LegacyWorld, state: dict) -> None:
    run, plan = to_plan(w, COMPANY, "mat-items", "items.csv", sample("items.csv"))
    counts = plan.counts()
    expect(counts == {"new": 50, "existing": 0, "invalid": 0}, f"plan counts are {counts}")
    state["items_run"] = run.id


def check_items_load(w: LegacyWorld, state: dict) -> None:
    outcome = w.service.load(COMPANY, state["items_run"], actor=ADMIN)
    expect(outcome.created == 50, f"load created {outcome.created}, want 50")
    count = w.scalar(
        "SELECT COUNT(*) FROM cur_core_record WHERE type = 'materials.ItemMaster' AND scope = :s",
        s=COMPANY,
    )
    expect(int(count) == 50, f"{count} materials.ItemMaster records, want 50")


def check_items_reconcile(w: LegacyWorld, state: dict) -> None:
    _, report = w.service.reconcile(COMPANY, state["items_run"], actor=ADMIN)
    expect(report["mismatches"] == 0, f"reconcile reports {report['mismatches']} mismatches")


def check_items_second_run(w: LegacyWorld, state: dict) -> None:
    _, plan = to_plan(w, COMPANY, "mat-items", "items.csv", sample("items.csv"))
    counts = plan.counts()
    expect(counts == {"new": 0, "existing": 50, "invalid": 0}, f"second plan is {counts}")


def check_locations_load(w: LegacyWorld, state: dict) -> None:
    run, plan = to_plan(w, PROJECT, "mat-locations", "locations.csv", sample("locations.csv"))
    expect(plan.counts()["invalid"] == 0, f"location plan is {plan.counts()}")
    outcome = w.service.load(PROJECT, run.id, actor=ADMIN)
    expect(outcome.created == 9, f"locations: load created {outcome.created}, want 9")


def check_po_lines_load(w: LegacyWorld, state: dict) -> None:
    run, plan = to_plan(w, PROJECT, "mat-po-lines", "po_lines.csv", sample("po_lines.csv"))
    expect(plan.counts()["invalid"] == 0, f"PO line plan is {plan.counts()}")
    outcome = w.service.load(PROJECT, run.id, actor=ADMIN)
    expect(outcome.created == 15, f"PO lines: load created {outcome.created}, want 15")


def check_items_refused_in_project(w: LegacyWorld, state: dict) -> None:
    try:
        w.service.open(PROJECT, "mat-items", "items.csv", sample("items.csv"), actor=ADMIN)
    except LoadRefusedError:
        return
    raise Failure("mat-items opened with a project scope was not refused")


CHECKS: list[tuple[str, Callable[[LegacyWorld, dict], None]]] = [
    ("the three loaders are found with their targets", check_loaders_found),
    ("mat-items run 1 (company): open to plan gives 50 new", check_items_plan),
    ("mat-items load creates 50 materials.ItemMaster records", check_items_load),
    ("mat-items reconcile: 0 mismatches", check_items_reconcile),
    ("mat-items second run of the same file plans 0 new and 50 existing", check_items_second_run),
    ("mat-locations run 2 (project) loads 9", check_locations_load),
    ("mat-po-lines run 3 (project) loads 15", check_po_lines_load),
    ("mat-items opening with a project scope is refused", check_items_refused_in_project),
]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        target = as_target(base / "ledger.db")
        create_schema(target)
        world = LegacyWorld(target, base / "objects", lake=LakeConfig.at(base / "lake"))
        state: dict = {}
        for name, check in CHECKS:
            try:
                check(world, state)
            except Failure as error:
                print(f"FAIL {name}: {error}")
                return 1
            except Exception as error:  # an unexpected failure is a failure, with its type
                print(f"FAIL {name}: {type(error).__name__}: {error}")
                return 1
            print(f"PASS {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
