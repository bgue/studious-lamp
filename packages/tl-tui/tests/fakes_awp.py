"""In-memory awp reads for `FakeClient` (P2-I1 T03b): the eight reads of `ClientInterface`.

The fake answers from the lists a test gives it (`load_awp`). It filters them the way the module's
views do (state, discipline, CWA code, depth, package kind), sorts them the way the views sort, and
raises `RecordNotFoundError` for an unknown CWP number, WBS code or path version. `seed_awp` gives
it the shape of the acceptance seed: 3 CWPs, 2 CWAs, a 3-node WBS, path versions 1 and 2 (2 is
current), one EWP and one PWP.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Literal

from tl_api.routes.awp import CwpDetailView, TimelineRow
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp import views as awp_views
from tl_mod_awp.names import ST_CLOSED, ST_PLANNED, ST_RELEASED

PROJECT = "P123"


class FakeAwpSupport:
    """Mixin for `FakeClient`: call `_init_awp()` from its `__init__`."""

    def _init_awp(self) -> None:
        self._awp_cwps: dict[str, list[CwpDetailView]] = {}
        self._awp_cwas: dict[str, list[awp_views.CwaRow]] = {}
        self._awp_wbs: dict[str, list[awp_views.WbsRow]] = {}
        self._awp_paths: dict[str, dict[int, awp_views.PathView]] = {}
        self._awp_versions: dict[str, list[awp_views.PathVersion]] = {}
        self._awp_packages: dict[str, list[awp_views.PackageRow]] = {}

    # --- seeding -----------------------------------------------------------------------------

    def load_awp(
        self,
        project: str,
        *,
        cwps: Iterable[CwpDetailView] = (),
        cwas: Iterable[awp_views.CwaRow] = (),
        wbs: Iterable[awp_views.WbsRow] = (),
        paths: Iterable[awp_views.PathView] = (),
        versions: Iterable[awp_views.PathVersion] = (),
        packages: Iterable[awp_views.PackageRow] = (),
    ) -> None:
        """Replace what the fake holds for ``project``. ``wbs`` is in depth-first order, as the
        view returns it."""
        self._awp_cwps[project] = list(cwps)
        self._awp_cwas[project] = list(cwas)
        self._awp_wbs[project] = list(wbs)
        self._awp_paths[project] = {path.version: path for path in paths}
        self._awp_versions[project] = list(versions)
        self._awp_packages[project] = list(packages)

    # --- the reads ---------------------------------------------------------------------------

    def list_cwps(
        self,
        project: str,
        *,
        state: str | None = None,
        discipline: str | None = None,
        cwa: str | None = None,
    ) -> list[awp_views.CwpRow]:
        found = sorted(self._awp_cwps.get(project, []), key=lambda d: d.number)
        rows = [_cwp_row(detail) for detail in found]
        return [
            row
            for row in rows
            if (state is None or row.state == state)
            and (discipline is None or row.discipline == discipline)
            and (cwa is None or row.cwa == cwa)
        ]

    def get_cwp(self, project: str, number: str) -> CwpDetailView:
        for detail in self._awp_cwps.get(project, []):
            if detail.number == number:
                return detail.model_copy(deep=True)
        raise RecordNotFoundError(f"no CWP {number!r}")

    def list_cwas(self, project: str) -> list[awp_views.CwaRow]:
        return sorted(self._awp_cwas.get(project, []), key=lambda area: area.code)

    def wbs_tree(self, project: str, *, depth: int | None = None) -> list[awp_views.WbsRow]:
        rows = list(self._awp_wbs.get(project, []))
        if depth is None:
            return rows
        return [row for row in rows if row.depth < depth]

    def get_wbs_node(self, project: str, code: str) -> awp_views.WbsRow:
        for row in self._awp_wbs.get(project, []):
            if row.code == code:
                return row
        raise RecordNotFoundError(f"no WBS node {code!r}")

    def get_path(self, project: str, version: int | None = None) -> awp_views.PathView:
        paths = self._awp_paths.get(project, {})
        if not paths:
            raise RecordNotFoundError(f"no path {project!r} at version {version!r}")
        wanted = next(iter(paths.values())).current_version if version is None else version
        if wanted not in paths:
            raise RecordNotFoundError(f"no path {project!r} at version {version!r}")
        return paths[wanted].model_copy(deep=True)

    def list_path_versions(self, project: str) -> list[awp_views.PathVersion]:
        return sorted(self._awp_versions.get(project, []), key=lambda v: v.version, reverse=True)

    def list_packages(
        self, project: str, *, kind: Literal["EWP", "PWP"] | None = None
    ) -> list[awp_views.PackageRow]:
        found = sorted(self._awp_packages.get(project, []), key=lambda p: (p.package_no, p.kind))
        return [p for p in found if kind is None or p.kind == kind]


def _cwp_row(detail: CwpDetailView) -> awp_views.CwpRow:
    return awp_views.CwpRow(**detail.model_dump(include=set(awp_views.CwpRow.model_fields)))


def seed_awp(client: FakeAwpSupport, project: str = PROJECT) -> None:
    """The acceptance seed's shape on ``client``: 3 CWPs, 2 CWAs (A2 retired), a 3-node WBS (1,
    1.1, 1.2), path versions 1 and 2 (2 current), one EWP and one PWP."""
    cwas = [
        awp_views.CwaRow(
            id="CWA-A1", code="A1", title="Area A1", location_text="Unit 1", retired=False
        ),
        awp_views.CwaRow(id="CWA-A2", code="A2", title="Area A2", location_text=None, retired=True),
    ]
    wbs = [
        awp_views.WbsRow(
            id="WBS-1",
            code="1",
            title="Plant",
            parent_code=None,
            depth=1,
            position=1,
            retired=False,
            total_hours=Decimal("120"),
            by_cost_code={"4210": Decimal("120")},
        ),  # fmt: skip
        awp_views.WbsRow(
            id="WBS-1.1",
            code="1.1",
            title="Piping",
            parent_code="1",
            depth=2,
            position=1,
            retired=False,
            total_hours=Decimal("80"),
            by_cost_code={"4210": Decimal("80")},
        ),  # fmt: skip
        awp_views.WbsRow(
            id="WBS-1.2",
            code="1.2",
            title="Electrical",
            parent_code="1",
            depth=2,
            position=2,
            retired=False,
            total_hours=None,
            by_cost_code={},
        ),  # fmt: skip
    ]
    cwps = [
        _seed_cwp(
            1,
            "Piping spool set",
            ST_RELEASED,
            "PIP",
            "A1",
            Decimal("40"),
            [
                ("created", "2026-10-09", "user:sue", ""),
                ("released", "2026-10-20", "user:sue", "IFC"),
            ],
        ),  # fmt: skip
        _seed_cwp(
            2,
            "Cable tray run",
            ST_PLANNED,
            "ELE",
            "A1",
            Decimal("25.5"),
            [("created", "2026-10-12", "user:uma", "")],
        ),  # fmt: skip
        _seed_cwp(
            3,
            "Valve install",
            ST_CLOSED,
            "PIP",
            "A2",
            None,
            [("created", "2026-10-02", "user:sue", "")],
        ),  # fmt: skip
    ]
    paths = [
        awp_views.PathView(
            id="PATH-P123",
            key="P123-PATH",
            title="Path of construction",
            version=1,
            current_version=2,
            steps=[
                awp_views.PathStep(
                    position=1,
                    cwa="A1",
                    reason_code=None,
                    actor="user:sue",
                    recorded_at="2026-10-01T09:00:00+00:00",
                )
            ],
        ),  # fmt: skip
        awp_views.PathView(
            id="PATH-P123",
            key="P123-PATH",
            title="Path of construction",
            version=2,
            current_version=2,
            steps=[
                awp_views.PathStep(
                    position=1,
                    cwa="A1",
                    reason_code=None,
                    actor="user:sue",
                    recorded_at="2026-10-15T09:00:00+00:00",
                ),
                awp_views.PathStep(
                    position=2,
                    cwa="A2",
                    reason_code="reorder",
                    actor="user:sue",
                    recorded_at="2026-10-15T09:00:00+00:00",
                ),
            ],
        ),  # fmt: skip
    ]
    versions = [
        awp_views.PathVersion(version=1, recorded_at="2026-10-01T09:00:00+00:00",
                              actor="user:sue", step_count=1, is_current=False),
        awp_views.PathVersion(version=2, recorded_at="2026-10-15T09:00:00+00:00",
                              actor="user:sue", step_count=2, is_current=True),
    ]  # fmt: skip
    packages = [
        awp_views.PackageRow(
            id="EWP-1",
            kind="EWP",
            package_no="EWP-001",
            status_text="Issued",
            forecast_date="2026-11-30",
            actual_date=None,
            constraint_source=False,
            source_system=None,
        ),  # fmt: skip
        awp_views.PackageRow(
            id="PWP-1",
            kind="PWP",
            package_no="PWP-001",
            status_text=None,
            forecast_date=None,
            actual_date=None,
            constraint_source=True,
            source_system=None,
        ),  # fmt: skip
    ]
    client.load_awp(
        project, cwps=cwps, cwas=cwas, wbs=wbs, paths=paths, versions=versions, packages=packages
    )


def _seed_cwp(
    n: int,
    title: str,
    state: str,
    discipline: str,
    cwa: str,
    budget: Decimal | None,
    history: list[tuple[str, str, str, str]],
) -> CwpDetailView:
    """CWP ``n`` of the seed; ``history`` rows are (event, date, actor, note)."""
    return CwpDetailView(
        id=f"CWP-{n}", number=f"P123-CWP-{n:04d}", title=title, state=state,
        discipline=discipline, cwa=cwa, planned_start="2026-11-01", planned_finish="2026-12-15",
        budget_hours=budget, contractor_text=None, quantities=None,
        allocations=[awp_views.CwpAllocation(wbs_code="1.1", percent=Decimal("100"))],
        packages=[], activities=[], link_count=1, file_count=0,
        timeline=[
            TimelineRow(date=date, who=who, event=event, note=note)
            for event, date, who, note in history
        ],
    )  # fmt: skip
