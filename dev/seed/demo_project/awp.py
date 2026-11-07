"""awp section: the WBS and its cost codes, 12 work areas, the path of construction (v1, then v2),
40-60 construction work packages in mixed states, and 10 external package references.

Every write goes through the awp command handlers and the cost import handler, one unit of work per
command (``world.run``). The ``build`` draws from the section's own ``rng`` only and uses the
project calendar (``START``, ``TODAY``) for every date; nothing reads the clock.

The WBS is project -> area (100-600) -> discipline -> system -> sub-system, five levels, about 100
nodes. Cost codes are mapped to the sub-system leaves only. Each work package is allocated 100% to
one leaf of its own area and discipline. Two of the ten external packages are constraint sources;
each is linked, with the ``requires`` relation, to packages that are Released for IWP development.
"""

from __future__ import annotations

import random
from datetime import timedelta
from pathlib import Path

from tl_adapters.db import open_uow
from tl_core.services.links import AddLink, handle_add_link
from tl_mod_awp.commands import (
    AllocateCwpToWbs,
    CloseCwp,
    CompleteCwp,
    CreateCwp,
    DefineCwa,
    DefinePathOfConstruction,
    DefineWbsNode,
    MapWbsToCostCodes,
    MoveCwaInPath,
    RecordExternalPackage,
    ReleaseCwp,
    StartCwpDevelopment,
    StartCwpExecution,
)
from tl_mod_awp.handlers.cwa import handle_define_cwa
from tl_mod_awp.handlers.cwp import (
    handle_allocate_cwp_to_wbs,
    handle_close_cwp,
    handle_complete_cwp,
    handle_create_cwp,
    handle_release_cwp,
    handle_start_cwp_development,
    handle_start_cwp_execution,
)
from tl_mod_awp.handlers.packages import handle_record_external_package
from tl_mod_awp.handlers.path import handle_define_path_of_construction, handle_move_cwa_in_path
from tl_mod_awp.handlers.wbs import handle_define_wbs_node, handle_map_wbs_to_cost_codes
from tl_mod_cost.handlers.snapshots import ImportCostSnapshot, handle_import_cost_snapshot
from tl_mod_cost.imports.model import CostRow
from tl_mod_engineering.document import load_standards_file
from tl_mod_engineering.loader import load_standards

from dev.seed.demo_project.core import ADMIN, AREAS
from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import START, TODAY, World

STANDARDS = Path(__file__).resolve().parent / "data" / "awp" / "standards.yaml"
# the project engineer, an awp user: areas, work packages and their allocation
BUILDER = "lhartmann"
ROOT = "P200"
CWP_COUNT = 50
PATH_VERSION_V1 = 1
#: planned 10, in development 4, released for IWP development 32, closed 4
STATES = ("planned",) * 10 + ("development",) * 4 + ("released",) * 32 + ("closed",) * 4

#: discipline code -> (title, cost code prefix); the codes are the company standards' list
DISCIPLINES: dict[str, tuple[str, str]] = {
    "PIP": ("Piping", "2100"),
    "STR": ("Structural", "2200"),
    "CIV": ("Civil", "2300"),
    "ELE": ("Electrical", "2400"),
    "INS": ("Instrumentation", "2500"),
    "MEC": ("Mechanical", "2600"),
    "ISL": ("Insulation", "2700"),
    "PNT": ("Painting", "2800"),
}
SYSTEMS: tuple[str, ...] = (
    "Reactor feed",
    "Fractionator overhead",
    "Cooling water",
    "Steam and condensate",
    "Nitrogen",
    "Tank transfer",
    "Cable and tray",
    "Control loops",
)
SUBSYSTEMS: tuple[str, ...] = (
    "Spool set",
    "Supports",
    "Hydrotest package",
    "Headers",
    "Skid",
    "Tie-in set",
    "Loop group",
    "Equipment bay",
)
# (kind, number, title, status, constraint source): an EWP is the owner's engineering package, a
# PWP its procurement package. The two constraint sources hold back field work.
PACKAGES: tuple[tuple[str, str, str, str, bool], ...] = (
    ("ewp", "EWP-0101", "Pipe rack structural steel", "IFC issued", False),
    ("ewp", "EWP-0102", "Reactor pad foundations", "Issued for construction", True),
    ("ewp", "EWP-0103", "Fractionator platform", "In review", False),
    ("ewp", "EWP-0104", "Tank farm dyke and drainage", "Issued for design", False),
    ("ewp", "EWP-0105", "Substation cable and tray", "IFC issued", True),
    ("ewp", "EWP-0106", "Cooling water pump set", "In review", False),
    ("pwp", "PWP-0201", "Heat exchangers", "Purchase order placed", False),
    ("pwp", "PWP-0202", "Pumps and drivers", "Delivery forecast", False),
    ("pwp", "PWP-0203", "Structural steel supply", "Partly delivered", False),
    ("pwp", "PWP-0204", "Control valves", "Expediting", False),
)
CONSTRAINT_SOURCES = frozenset({"EWP-0102", "EWP-0105"})


def _cost_codes() -> list[tuple[str, str]]:
    """(code, title) of the erection and test cost code of each discipline."""
    found: list[tuple[str, str]] = []
    for disc, (title, prefix) in DISCIPLINES.items():
        found.append((f"{prefix}-{disc}-ERC", f"{title} erection"))
        found.append((f"{prefix}-{disc}-TST", f"{title} test"))
    return found


def _wbs(world: World, rng: random.Random) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    """The WBS under ROOT: the id of every node, and the leaves as (code, area, discipline)."""
    ids: dict[str, str] = {}
    leaves: list[tuple[str, str, str]] = []

    def define(code: str, title: str, parent: str | None) -> None:
        made = world.run(
            handle_define_wbs_node,
            DefineWbsNode,
            by=ADMIN,
            code=code,
            title=title,
            parent_code=parent,
        )
        ids[code] = str(made.stream_id)

    define(ROOT, "North Refinery, Hydrotreater Unit 2 expansion", None)
    for area, area_title in AREAS:
        area_code = f"{ROOT}.{area}"
        define(area_code, f"Area {area}, {area_title}", ROOT)
        for disc in sorted(rng.sample(sorted(DISCIPLINES), 2)):
            disc_code = f"{area_code}.{disc}"
            define(disc_code, f"{DISCIPLINES[disc][0]}, area {area}", area_code)
            for s, system in enumerate(rng.sample(SYSTEMS, 2), start=1):
                system_code = f"{disc_code}.{s:02d}"
                define(system_code, system, disc_code)
                for n, sub in enumerate(rng.sample(SUBSYSTEMS, rng.choice((2, 3))), start=1):
                    leaf = f"{system_code}.{n:02d}"
                    define(leaf, sub, system_code)
                    leaves.append((leaf, area, disc))
    return ids, leaves


def build(world: World, rng: random.Random) -> None:
    with open_uow(world.target) as uow:
        load_standards(
            uow, load_standards_file(STANDARDS), actor=f"user:{ADMIN}", source="demo-project"
        )

    # cost codes, then the WBS (on the day the project's plan starts), then the cost code mapping
    with world.on(TODAY):
        world.run(
            handle_import_cost_snapshot,
            ImportCostSnapshot,
            by=ADMIN,
            period=TODAY.strftime("%Y-%m"),
            as_of=TODAY.isoformat(),
            rows=[CostRow(code=code, description=title) for code, title in _cost_codes()],
        )
    with world.on(START + timedelta(days=6)):
        ids, leaves = _wbs(world, rng)
    with world.on(START + timedelta(days=9)):
        for leaf, _area, disc in leaves:
            prefix = DISCIPLINES[disc][1]
            erection, test = f"{prefix}-{disc}-ERC", f"{prefix}-{disc}-TST"
            if rng.random() < 0.5:
                lines = [{"cost_code": erection, "percent": "100.00"}]
            else:
                lines = [
                    {"cost_code": erection, "percent": "60.00"},
                    {"cost_code": test, "percent": "40.00"},
                ]
            world.run(
                handle_map_wbs_to_cost_codes,
                MapWbsToCostCodes,
                by=ADMIN,
                node=ids[leaf],
                allocations=lines,
            )

    # 12 work areas, two per area; the path of construction is v1, then one re-sequence makes v2
    cwas: dict[str, list[str]] = {}
    with world.on(START + timedelta(days=14)):
        for area, _title in AREAS:
            for n in (1, 2):
                code = f"CWA-{area}-{n:02d}"
                world.run(
                    handle_define_cwa,
                    DefineCwa,
                    by=BUILDER,
                    code=code,
                    title=f"Area {area}, work area {n}",
                    location_text=f"Unit 2, area {area}",
                )
                cwas.setdefault(area, []).append(code)
        world.run(
            handle_define_path_of_construction,
            DefinePathOfConstruction,
            by=ADMIN,
            steps=[{"cwa_code": c} for area, _t in AREAS for c in cwas[area]],
        )
    with world.on(START + timedelta(days=45)):
        # the definition is version 1 (``PathOfConstruction.Defined``); a move reads that version
        world.run(
            handle_move_cwa_in_path,
            MoveCwaInPath,
            by=ADMIN,
            cwa_code="CWA-300-02",
            to_position=4,
            reason_code="Procurement",
            note="Tank farm steel is late; the second tank area moves up",
            expected_version=PATH_VERSION_V1,
        )

    # 50 work packages in mixed states, each allocated 100% to one leaf of its area and discipline
    order = rng.sample(leaves, len(leaves))
    released: list[str] = []  # the packages that are Released for IWP development now
    for i, state in enumerate(rng.sample(STATES, CWP_COUNT)):
        leaf, area, disc = order[i % len(order)]
        title = DISCIPLINES[disc][0]
        start = START + timedelta(days=rng.randrange(40, 200))
        finish = start + timedelta(days=rng.randrange(21, 90))
        with world.on(START + timedelta(days=20 + i // 4)):
            cwp = str(
                world.run(
                    handle_create_cwp,
                    CreateCwp,
                    by=BUILDER,
                    discipline=disc,
                    title=f"{title} package {leaf}",
                    cwa_code=rng.choice(cwas[area]),
                    planned_start=start.isoformat(),
                    planned_finish=finish.isoformat(),
                    budget_hours=str(rng.randrange(200, 4001, 50)),
                ).stream_id
            )
            world.run(
                handle_allocate_cwp_to_wbs,
                AllocateCwpToWbs,
                by=BUILDER,
                cwp=cwp,
                allocations=[{"wbs_code": leaf, "percent": "100.00"}],
            )
            if state != "planned":
                world.run(handle_start_cwp_development, StartCwpDevelopment, by=BUILDER, cwp=cwp)
            if state in ("released", "closed"):
                world.run(
                    handle_release_cwp,
                    ReleaseCwp,
                    by=ADMIN,
                    cwp=cwp,
                    expected_version=world.version(cwp),
                )
            if state == "released":
                released.append(cwp)
            if state == "closed":
                world.run(handle_start_cwp_execution, StartCwpExecution, by=ADMIN, cwp=cwp)
                world.run(handle_complete_cwp, CompleteCwp, by=ADMIN, cwp=cwp)
                world.run(handle_close_cwp, CloseCwp, by=ADMIN, cwp=cwp)

    # 10 external package references; two are constraint sources, each linked to released packages
    package_ids: dict[str, str] = {}
    with world.on(START + timedelta(days=60)):
        for kind, number, title, status, constraint in PACKAGES:
            made = world.run(
                handle_record_external_package,
                RecordExternalPackage,
                by=ADMIN,
                package_type=kind,
                package_no=number,
                title=title,
                status_text=status,
                forecast_date=(START + timedelta(days=rng.randrange(60, 180))).isoformat(),
                constraint_source=constraint,
                source_system="Engineering DMS" if kind == "ewp" else "Procurement system",
            )
            package_ids[number] = str(made.stream_id)
        for _kind, number, *_rest in PACKAGES:
            count = 2 if number in CONSTRAINT_SOURCES else rng.choice((1, 2))
            for cwp in rng.sample(released, count):
                world.run(
                    handle_add_link,
                    AddLink,
                    by=BUILDER,
                    from_id=cwp,
                    to_id=package_ids[number],
                    relation="requires",
                )


register("awp", build, needs=("awp.CWP",))
