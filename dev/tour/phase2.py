"""The Phase 2 tour: the wave 2 to 4 terminal screens on the full demo project P200.

    uv run python dev/tour/phase2.py [--out docs/reports/tour/phase-2]
    just tour phase2 [/tmp/phase2-tour]

Same method as `wave1.py` (see `tourkit.py`): a fresh SQLite ledger in a temporary directory, the
real TUI driven headless, the frozen clock, and the leak check on every plain screenshot. The
project is built once by the demo project generator (`seed_demo_project` from `wave1`); no
network, no Postgres. It writes nineteen SVGs. Every actor is written ``user:<name>``: a bare name
resolves to no account, so a screen that checks a read word (constraints, requisitions, work
orders, punch, scaffolds, the toolcrib) refuses it:

    01-iwps          the IWP register                          user:lhartmann
    02-constraints   the constraints                           user:gwhitfield (viewer, all modules)
    03-readiness     the readiness checks of one IWP          user:lhartmann
    04-lookahead     the look-ahead (weekly step 1)           user:lhartmann
    05-release       the release step (weekly step 3)         user:lhartmann
    06-commitments   the commitments of the open week         user:lhartmann
    07-progress      the progress of the IWPs in field work   user:lhartmann
    08-requisitions  the requisitions                          user:treyes
    09-work-orders   the work order backlog                    user:treyes
    10-punch         the punch list                            user:hsato
    11-schedule      the schedules                            user:lhartmann
    12-packages      the packages                             user:lhartmann
    13-scaffolds     the scaffold register                     user:lhartmann
    14-scaffold-record  one scaffold with its inspections      user:lhartmann
    15-toolcrib      the toolcrib TC1 at the crib     user:treyes
    16-inspections   the inspection log                       user:hsato
    17-inspection    one Done inspection, with failed questions user:hsato (P200-INS-0009)
    18-permits       the permit register                      user:ipetrov
    19-permit        one Active permit, with its gas tests    user:ipetrov (P200-PTW-0001)
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:  # `dev` is not an installed package
    sys.path.append(str(REPO))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.append(str(Path(__file__).resolve().parent))

import tourkit as tk  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from tourkit import Workspace  # noqa: E402

from dev.seed.demo_project.world import PROJECT_ID as PROJECT  # noqa: E402
from dev.tour.wave1 import seed_demo_project  # noqa: E402

DEFAULT_OUT = REPO / "docs/reports/tour/phase-2"
TODAY = datetime(2026, 11, 6, 9, 0, 0, tzinfo=UTC)  # the project calendar's "today"
AWP = "lhartmann"  # the project engineer: awp (IWPs, readiness, weekly cycle), schedules, packages
IWP = "P200-IWP-CIV-0001"  # an IWP number from the 01-iwps shot
STORES = "treyes"  # the materials coordinator: requisitions, work orders, the toolcrib
SCAFFOLD = "P200-SCF-0001"  # the one scaffold of the demo project (scaffold section, T11a)
CRIB = "TC1"  # the toolcrib of P200
INSPECTION = "P200-INS-0009"  # a Done inspection with a failed question (the generator is fixed)
PERMIT = "P200-PTW-0001"  # an Active permit with three gas tests (the generator is fixed)


async def _open(pilot: Pilot[Any], app: Any, make: Callable[[Any], Any], what: str) -> None:
    """Wait for the shell, push the screen on the app's client and wait for its rows."""
    await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
    app.push_screen(make(app.client))
    await tk.until(pilot, lambda: len(app.screen.rows) > 0, what, timeout=60.0)
    await tk.settle(pilot, 3)


def scenario(
    ws: Workspace,
    name: str,
    title: str,
    actor: str,
    make: Callable[[Any], Any],
    what: str,
    *needles: str,
    technical: bool = False,
) -> None:
    """One screen of the tour: open it as ``actor`` and save the shot once ``needles`` show."""
    from tl_tui.main import build_app

    app = build_app(ws.db, PROJECT, live=False, actor=actor)

    async def run_it(pilot: Pilot[Any]) -> None:
        await _open(pilot, app, make, what)
        tk.shot_tui(ws, app, name, title, *needles, technical=technical)

    tk.run_tui(ws, app, run_it)


def record(
    ws: Workspace,
    name: str,
    title: str,
    actor: str,
    make: Callable[[Any], Any],
    what: str,
    *needles: str,
) -> None:
    """One record screen of the tour (a modal with no rows): push it on the app's client and save
    the shot once ``needles`` show. The record's key is pinned, as the log's keys are fixed."""
    from tl_tui.main import build_app

    app = build_app(ws.db, PROJECT, live=False, actor=actor)

    async def run_it(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        app.push_screen(make(app.client))
        await tk.until(pilot, lambda: all(n in tk.screen_text(app) for n in needles), what)
        await tk.settle(pilot, 3)
        tk.shot_tui(ws, app, name, title, *needles)

    tk.run_tui(ws, app, run_it)


def scaffold_record(ws: Workspace) -> None:
    """14: one scaffold opened on its record (the register's Enter does the same push)."""
    from tl_tui.main import build_app
    from tl_tui.widgets.scaffold_register import ScaffoldScreen

    app = build_app(ws.db, PROJECT, live=False, actor=f"user:{AWP}")

    async def run_it(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        app.push_screen(ScaffoldScreen(app.client, PROJECT, SCAFFOLD))
        await tk.until(pilot, lambda: "Inspections" in tk.screen_text(app), "the scaffold record")
        tk.shot_tui(
            ws,
            app,
            "14-scaffold-record",
            "One scaffold of P200 with its inspections",
            SCAFFOLD,
            "Inspections",
        )

    tk.run_tui(ws, app, run_it)


def toolcrib(ws: Workspace) -> None:
    """15: the toolcrib screen (a modal, so no ``rows``) at TC1, before any issue or return."""
    from tl_tui.main import build_app
    from tl_tui.widgets.toolcrib_screen import ToolcribScreen

    app = build_app(ws.db, PROJECT, live=False, actor=f"user:{STORES}")

    async def run_it(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        app.push_screen(ToolcribScreen(app.client, PROJECT, f"user:{STORES}", CRIB))
        await tk.until(pilot, lambda: len(app.screen.query("#tc-line")) > 0, "the toolcrib line")
        # before any issue or return: no done text, so no lot id on the screen
        tk.shot_tui(ws, app, "15-toolcrib", f"The toolcrib {CRIB} of P200", CRIB)

    tk.run_tui(ws, app, run_it)


def shots(ws: Workspace) -> None:
    from tl_tui.widgets.constraint_screen import ConstraintScreen
    from tl_tui.widgets.inspection_log import InspectionLogScreen, InspectionScreen
    from tl_tui.widgets.iwp_register import IwpRegisterScreen
    from tl_tui.widgets.package_log import PackageLogScreen
    from tl_tui.widgets.permit_log import PermitLogScreen, PermitScreen
    from tl_tui.widgets.punch_log import PunchLogScreen
    from tl_tui.widgets.readiness_screen import ReadinessScreen
    from tl_tui.widgets.requisition_register import RequisitionLogScreen
    from tl_tui.widgets.scaffold_register import ScaffoldLogScreen
    from tl_tui.widgets.schedule_screen import ScheduleScreen
    from tl_tui.widgets.weekly_screen import (
        CommitmentsScreen,
        LookAheadScreen,
        ProgressScreen,
        ReleaseScreen,
    )
    from tl_tui.widgets.work_order_backlog import WorkOrderBacklogScreen

    scenario(
        ws,
        "01-iwps",
        "The IWP register of P200: the work packages in their states",
        AWP,
        lambda c: IwpRegisterScreen(c, PROJECT),
        "the IWPs",
        "P200-IWP-CIV-0001",
        "Interim package 01 (CIV)",
    )
    scenario(
        ws,
        "02-constraints",
        "The constraints of P200",
        "user:gwhitfield",
        lambda c: ConstraintScreen(c, PROJECT),
        "the constraints",
        "P200-CON-0001",
        "Scaffold",
    )
    scenario(
        ws,
        "03-readiness",
        "The readiness checks of one IWP of P200",
        AWP,
        lambda c: ReadinessScreen(c, PROJECT, IWP),
        "the readiness checks",
        "Constraints cleared",
        "P200-CON-0001",
    )
    scenario(
        ws,
        "04-lookahead",
        "The look-ahead of P200: the activities of the next weeks",
        AWP,
        lambda c: LookAheadScreen(c, PROJECT),
        "the look-ahead",
        "A1110",
        "Fabricate valves",
    )
    scenario(
        ws,
        "05-release",
        "The release step of P200: the Ready IWPs",
        AWP,
        lambda c: ReleaseScreen(c, PROJECT),
        "the release",
        "P200-IWP-ISL-0001",
        "signoffs 0 of 2",
    )
    scenario(
        ws,
        "06-commitments",
        "The commitments of the open week of P200",
        AWP,
        lambda c: CommitmentsScreen(c, PROJECT),
        "the commitments",
        "2026-W45",
        "nothing committed",
    )
    scenario(
        ws,
        "07-progress",
        "The progress of P200: the IWPs in field work",
        AWP,
        lambda c: ProgressScreen(c, PROJECT),
        "the progress",
        "P200-IWP-INS-0005",
        "Interim package 09 (INS)",
    )
    scenario(
        ws,
        "08-requisitions",
        "The requisitions of P200",
        "user:treyes",
        lambda c: RequisitionLogScreen(c, PROJECT),
        "the requisitions",
        "P200-REQ-GEN-0001",
        "Crane lift for the pipe rack steel",
    )
    scenario(
        ws,
        "09-work-orders",
        "The work order backlog of P200",
        "user:treyes",
        lambda c: WorkOrderBacklogScreen(c, PROJECT),
        "the work orders",
        "P200-WO-0001",
        "Labour",
    )
    scenario(
        ws,
        "10-punch",
        "The punch list of P200",
        "user:hsato",
        lambda c: PunchLogScreen(c, PROJECT),
        "the punch items",
        "P200-PUN-0001",
        "Weld undersize at spool joint",
    )
    scenario(
        ws,
        "11-schedule",
        "The schedules of P200",
        AWP,
        lambda c: ScheduleScreen(c, PROJECT, f"user:{AWP}"),
        "the schedules",
        "MAIN",
        "schedule-week-4.xer",
    )
    scenario(
        ws,
        "12-packages",
        "The packages of P200",
        AWP,
        lambda c: PackageLogScreen(c, PROJECT),
        "the packages",
        "EWP-0101",
        "Pipe rack structural steel",
    )
    scenario(
        ws,
        "13-scaffolds",
        "The scaffold register of P200: the scaffolds in their states",
        f"user:{AWP}",
        lambda c: ScaffoldLogScreen(c, PROJECT),
        "the scaffolds",
        SCAFFOLD,
        "Designed",
    )
    scaffold_record(ws)
    toolcrib(ws)
    scenario(
        ws,
        "16-inspections",
        "The inspection log of P200",
        "user:hsato",
        lambda c: InspectionLogScreen(c, PROJECT),
        "the inspections",
        "P200-INS-0009",
        "Scaffold handover, substation roof",
    )
    record(
        ws,
        "17-inspection",
        "One inspection of P200: a Done inspection with failed questions",
        "user:hsato",
        lambda c: InspectionScreen(c, PROJECT, INSPECTION),
        "the inspection",
        INSPECTION,
        "to be fixed and shown again",
    )
    scenario(
        ws,
        "18-permits",
        "The permit register of P200",
        "user:ipetrov",
        lambda c: PermitLogScreen(c, PROJECT),
        "the permits",
        PERMIT,
        "Hot work",
    )
    record(
        ws,
        "19-permit",
        "One permit of P200: an Active permit with its gas tests",
        "user:ipetrov",
        lambda c: PermitScreen(c, PROJECT, PERMIT),
        "the permit",
        PERMIT,
        "Gas tests",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The Phase 2 tour: wave 2 to 4 screens on P200.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else Path.cwd() / args.out
    for old in out.glob("*.svg"):
        old.unlink()
    ws = Workspace(out)
    try:
        print("building the project P200 with the generator", flush=True)
        seed_demo_project(ws)
        tk.freeze()
        tk.CLOCK.now = TODAY  # the calendar's today; the frozen clock is otherwise 2026-10-12
        print("the shots", flush=True)
        shots(ws)
    except tk.TourFailed as exc:
        print(f"TourFailed: {exc}", file=sys.stderr)
        return 1
    finally:
        ws.close()
    print(f"wrote {len(ws.written)} screenshots to {out}")
    return tk.report_leaks()


if __name__ == "__main__":
    sys.exit(main())
