"""In-memory schedules and cost for `FakeClient` (P1-I4): the M11 reads of `ClientInterface`.

It holds schedules with their snapshots and the typed rows of each, and answers the reads the way
the embedded client does: activities filtered and paged, comparisons computed by the module's own
`compare`, the module's errors for an unknown schedule, snapshot or activity. The look-ahead, the
orphans, the resolutions and the activity links of a record are whatever the test gave it.
`test_embedded_schedule.py` runs the same reads on this fake and on the embedded client and compares
the answers.
"""

from __future__ import annotations

from tl_core.auth.errors import ForbiddenError
from tl_core.services.commands import CommandResult
from tl_mod_cost import views as cost_views
from tl_mod_cost.errors import CostCodeNotFoundError
from tl_mod_schedule import views
from tl_mod_schedule.compare import Comparison, SnapshotData, compare
from tl_mod_schedule.errors import (
    ActivityNotFoundError,
    NoCurrentSnapshotError,
    ScheduleNotFoundError,
    SnapshotNotFoundError,
    SnapshotStateError,
)
from tl_mod_schedule.handlers.activity import LinkActivity
from tl_mod_schedule.handlers.publish import PublishScheduleSnapshot
from tl_mod_schedule.lookahead import LookAhead
from tl_mod_schedule.registry import DEFAULT_DAY_HOURS, ActivityRow, RelationshipRow
from tl_mod_schedule.resolver import ActivityLink, OrphanedLink, Resolution
from tl_mod_schedule.testing import make_activity, make_relationship

BUILT = ("Valid", "Published", "Superseded")


def snapshot_view(
    code: str,
    number: int,
    data_date: str | None,
    state: str,
    *,
    current: bool,
    previous: int | None,
) -> views.SnapshotView:
    return views.SnapshotView(
        id=f"SNAP-{code}-{number}", key=f"{code}#{number}", number=number, state=state,
        is_current=current, data_date=data_date, previous_number=previous, p6_version="20.12",
        p6_project=code, activity_count=5, relationship_count=4, wbs_count=2, calendar_count=1,
        code_count=0, udf_count=0, error_count=0, warning_count=0,
        source_name=f"{code}-{number}.xer", source_size=1000, source_sha256="a" * 64,
        requested_by="user:dev", attempts=1,
        last_error=None, built_at=data_date, published_at=data_date if current else None,
        report_file_id=None, raw_file_id=None,
    )  # fmt: skip


class FakeScheduleSupport:
    """Mixin for `FakeClient`: call `_init_schedule()` from its `__init__`."""

    def _init_schedule(self) -> None:
        self._schedules: dict[tuple[str, str], views.ScheduleDetailView] = {}
        self._rows: dict[tuple[str, str, int], tuple[list[ActivityRow], list[RelationshipRow]]] = {}
        self._look_aheads: dict[tuple[str, str], LookAhead] = {}
        self._orphans: dict[tuple[str, str], list[OrphanedLink]] = {}
        self._resolutions: dict[tuple[str, str, str, str], Resolution] = {}
        self._activity_links: dict[str, list[ActivityLink]] = {}
        self._cost_codes: dict[str, dict[str, cost_views.CostCodeDetailView]] = {}
        self._cost_snapshots: dict[str, list[cost_views.CostSnapshotView]] = {}
        self.schedule_commands: list[object] = []  # every command a schedule screen sent

    # --- seeding -----------------------------------------------------------------------------

    def seed_schedule(self, project: str = "P123") -> None:
        """Schedule MAIN with two published snapshots a week apart (the shape of the demo).

        Snapshot 1 (data date 2026-10-05) has A1220, A1230 (9 days of float), A1240 and A1990;
        snapshot 2 (2026-10-12) lacks A1990, has A2500, and A1230 has 4 days of float. A1230 is
        critical in neither; A1220 is critical in both.
        """
        one = [
            make_activity("A1220", name="Set rack foundations", total_float_hr=0.0, critical=True,
                          seq=1, status="completed", percent_complete=100.0),
            make_activity("A1230", name="Install pipe rack supports", total_float_hr=72.0, seq=2),
            make_activity("A1240", name="Erect pipe spools on rack", total_float_hr=40.0, seq=3),
            make_activity("A1990", name="Temporary fencing", total_float_hr=96.0, seq=4),
        ]  # fmt: skip
        two = [
            make_activity("A1220", name="Set rack foundations", total_float_hr=0.0, critical=True,
                          seq=1, status="completed", percent_complete=100.0),
            make_activity("A1230", name="Install pipe rack supports", total_float_hr=32.0,
                          early_finish="2026-10-23T16:00", seq=2),
            make_activity("A1240", name="Erect pipe spools on rack", total_float_hr=40.0, seq=3),
            make_activity("A2500", name="Weld inspection hold point", total_float_hr=16.0, seq=4),
        ]  # fmt: skip
        links = [make_relationship("A1220", "A1230"), make_relationship("A1230", "A1240")]
        self.add_schedule(
            project,
            "MAIN",
            [
                ("2026-10-05T08:00", "Superseded", one, links),
                (
                    "2026-10-12T08:00",
                    "Published",
                    two,
                    [*links, make_relationship("A1230", "A2500")],
                ),
            ],
        )

    def add_schedule(
        self,
        project: str,
        code: str,
        snapshots: list[tuple[str | None, str, list[ActivityRow], list[RelationshipRow]]],
    ) -> None:
        """A schedule with snapshots oldest first: (data date, state, activities, relationships).

        The last Published snapshot is the current one.
        """
        current = next(
            (i + 1 for i in reversed(range(len(snapshots))) if snapshots[i][1] == "Published"),
            None,
        )
        built = [i + 1 for i, s in enumerate(snapshots) if s[1] in BUILT]
        shown: list[views.SnapshotView] = []
        for number, (date, state, activities, relationships) in enumerate(snapshots, start=1):
            before = [n for n in built if n < number and snapshots[n - 1][0] is not None]
            shown.append(
                snapshot_view(
                    code,
                    number,
                    date,
                    state,
                    current=number == current,
                    previous=max(before) if before and state in BUILT else None,
                )  # fmt: skip
            )
            self._rows[(project, code, number)] = (activities, relationships)
        shown.reverse()  # newest number first
        top = next((s for s in shown if s.is_current), None)
        self._schedules[(project, code)] = views.ScheduleDetailView(
            id=f"SCHED-{code}", code=code, title=f"{code} schedule", schedule_type="current",
            owner=None, p6_project=code,
            current_snapshot_number=None if top is None else top.number,
            current_data_date=None if top is None else top.data_date,
            snapshot_count=len(shown), snapshots=shown,
        )  # fmt: skip

    def seed_cost(self, project: str = "P123") -> None:
        """Three cost codes (4210 with a child) and two snapshots."""
        figures = {name: None for name in cost_views.MEASURE_COLUMNS}
        top = cost_views.CostCodeDetailView(
            id="CC-4210", code="4210", title="Piping", parent_code=None, level=1, uom=None,
            is_active=True, period="2026-07", as_of="2026-07-31",
            figures={**figures, "hours_budget": 1000.0, "hours_actual": 400.0},
            children=["4210-PIP"],
            history=[
                cost_views.SnapshotValueView(
                    period="2026-07", revision=1, as_of="2026-07-31",
                    figures={**figures, "hours_budget": 1000.0, "hours_actual": 400.0},
                )
            ],
        )  # fmt: skip
        child = top.model_copy(
            update={
                "id": "CC-4210-PIP", "code": "4210-PIP", "title": "Pipe installation",
                "parent_code": "4210", "level": 2, "uom": "in-dia", "children": [],
            }
        )  # fmt: skip
        self._cost_codes[project] = {"4210": top, "4210-PIP": child}
        self._cost_snapshots[project] = [
            cost_views.CostSnapshotView(
                id="CS-1", period="2026-07", revision=1, key="2026-07@1", as_of="2026-07-31",
                currency="USD", source_name="july.csv", source_sha256="b" * 64, row_count=2,
                new_code_count=2, revised_code_count=0, created_at="2026-08-01T09:00:00+00:00",
            )
        ]  # fmt: skip

    # --- giving it what a test needs ---------------------------------------------------------

    def put_schedule(
        self,
        project: str,
        detail: views.ScheduleDetailView,
        rows: dict[int, tuple[list[ActivityRow], list[RelationshipRow]]],
    ) -> None:
        """A schedule as the embedded client read it, with the typed rows of its built snapshots."""
        self._schedules[(project, detail.code)] = detail
        for number, pair in rows.items():
            self._rows[(project, detail.code, number)] = pair

    def put_look_ahead(self, project: str, code: str, answer: LookAhead) -> None:
        self._look_aheads[(project, code)] = answer

    def put_orphans(self, project: str, code: str, answer: list[OrphanedLink]) -> None:
        self._orphans[(project, code)] = answer

    def put_resolution(
        self, project: str, code: str, activity_id: str, as_of: str | None, answer: Resolution
    ) -> None:
        self._resolutions[(project, code, activity_id, as_of or "")] = answer

    def put_activity_links(self, record_id: str, answer: list[ActivityLink]) -> None:
        self._activity_links[record_id] = answer

    def put_cost_code(self, project: str, answer: cost_views.CostCodeDetailView) -> None:
        self._cost_codes.setdefault(project, {})[answer.code] = answer

    def put_cost_snapshots(self, project: str, answer: list[cost_views.CostSnapshotView]) -> None:
        self._cost_snapshots[project] = answer

    # --- the reads ---------------------------------------------------------------------------

    def _detail(self, project: str, code: str) -> views.ScheduleDetailView:
        found = self._schedules.get((project, code))
        if found is None:
            raise ScheduleNotFoundError(f"no schedule {code!r} in project:{project}")
        return found

    def _snapshot(
        self, project: str, code: str, number: int | None, *, built: bool = False
    ) -> views.SnapshotView:
        detail = self._detail(project, code)
        if number is None:
            if detail.current_snapshot_number is None:
                raise NoCurrentSnapshotError(f"schedule {code} has no published snapshot yet")
            number = detail.current_snapshot_number
        found = next((s for s in detail.snapshots if s.number == number), None)
        if found is None:
            raise SnapshotNotFoundError(f"schedule {code} has no snapshot {number}")
        if built and found.state not in BUILT:
            raise SnapshotStateError(
                f"snapshot {found.key} is {found.state}: it has no activities to read"
            )
        return found

    def list_schedules(self, project: str) -> list[views.ScheduleView]:
        found = [d for (p, _), d in self._schedules.items() if p == project]
        return [
            views.ScheduleView(**d.model_dump(exclude={"snapshots"}))
            for d in sorted(found, key=lambda d: d.code)
        ]

    def get_schedule(
        self, project: str, code: str, *, limit: int = 50, offset: int = 0
    ) -> views.ScheduleDetailView:
        detail = self._detail(project, code)
        page = detail.snapshots[max(0, offset) : max(0, offset) + max(1, limit)]
        return detail.model_copy(update={"snapshots": page})

    def get_schedule_snapshot(self, project: str, code: str, number: int) -> views.SnapshotView:
        return self._snapshot(project, code, number)

    def list_activities(
        self,
        project: str,
        code: str,
        *,
        snapshot: int | None = None,
        critical: bool | None = None,
        status: str | None = None,
        q: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> views.ActivityPage:
        shown = self._snapshot(project, code, snapshot, built=True)
        rows = self._rows[(project, code, shown.number)][0]
        needle = q.lower() if q else None
        matched = [
            a
            for a in sorted(rows, key=lambda a: a.seq)
            if (critical is None or a.critical == critical)
            and (status is None or a.status == status)
            and (needle is None or needle in a.activity_id.lower() or needle in a.name.lower())
        ]
        start = max(0, offset)
        size = max(1, min(limit, views.MAX_PAGE))
        return views.ActivityPage(
            snapshot_key=shown.key, snapshot_number=shown.number, data_date=shown.data_date,
            total=len(matched), offset=start, rows=tuple(matched[start : start + size]),
        )  # fmt: skip

    def _data(self, project: str, code: str, shown: views.SnapshotView) -> SnapshotData:
        activities, relationships = self._rows[(project, code, shown.number)]
        assert shown.data_date is not None
        return SnapshotData(
            shown.key, shown.number, shown.data_date,
            {a.activity_id: a for a in activities}, relationships, {"1": DEFAULT_DAY_HOURS},
        )  # fmt: skip

    def compare_snapshots(
        self,
        project: str,
        code: str,
        *,
        new: int | None = None,
        old: int | None = None,
        limit: int = views.DEFAULT_COMPARE_LIMIT,
    ) -> Comparison:
        newer = self._snapshot(project, code, new, built=True)
        if old is None:
            if newer.previous_number is None:
                raise SnapshotNotFoundError(
                    f"snapshot {newer.key} has no earlier snapshot to compare"
                )
            old = newer.previous_number
        older = self._snapshot(project, code, old, built=True)
        result = compare(self._data(project, code, older), self._data(project, code, newer))
        return result.limited(max(1, min(limit, views.MAX_COMPARE_LIMIT)))

    def get_look_ahead(
        self, project: str, code: str, *, snapshot: int | None = None, weeks: int = 4
    ) -> LookAhead:
        self._snapshot(project, code, snapshot, built=True)
        found = self._look_aheads.get((project, code))
        if found is None:
            raise NoCurrentSnapshotError(f"the fake has no look-ahead for {code}")
        return found

    def list_orphaned_links(self, project: str, code: str) -> list[OrphanedLink]:
        self._detail(project, code)
        return list(self._orphans.get((project, code), []))

    def get_schedule_activity(
        self, project: str, code: str, activity_id: str, *, snapshot: int | None = None
    ) -> views.ActivityDetail:
        shown = self._snapshot(project, code, snapshot, built=True)
        activities, relationships = self._rows[(project, code, shown.number)]
        found = next((a for a in activities if a.activity_id == activity_id), None)
        if found is None:
            raise ActivityNotFoundError(f"snapshot {shown.key} has no activity {activity_id!r}")
        return views.ActivityDetail(
            snapshot_key=shown.key, snapshot_number=shown.number, activity=found,
            predecessors=tuple(r for r in relationships if r.succ_activity_id == activity_id),
            successors=tuple(r for r in relationships if r.pred_activity_id == activity_id),
        )  # fmt: skip

    def get_activity_trend(
        self, project: str, code: str, activity_id: str
    ) -> list[views.TrendPoint]:
        detail = self._detail(project, code)
        points: list[views.TrendPoint] = []
        for shown in sorted(detail.snapshots, key=lambda s: s.data_date or ""):
            if shown.state not in ("Published", "Superseded"):
                continue
            found = next(
                (a for a in self._rows[(project, code, shown.number)][0]
                 if a.activity_id == activity_id),
                None,
            )  # fmt: skip
            if found is None:
                continue
            days = None if found.total_float_hr is None else round(found.total_float_hr / 8.0, 2)
            points.append(
                views.TrendPoint(
                    snapshot_number=shown.number,
                    data_date=shown.data_date,
                    state=shown.state,
                    total_float_days=days,
                    early_start=found.early_start,
                    early_finish=found.early_finish,
                    percent_complete=found.percent_complete,
                    critical=found.critical,
                )  # fmt: skip
            )
        if not points:
            raise ActivityNotFoundError(f"no published snapshot of {code} has {activity_id!r}")
        return points

    def resolve_activity(
        self, project: str, code: str, activity_id: str, *, as_of: str | None = None
    ) -> Resolution:
        self._detail(project, code)
        found = self._resolutions.get((project, code, activity_id, as_of or ""))
        if found is None:
            raise ActivityNotFoundError(f"the fake has no resolution of {activity_id!r}")
        return found

    def list_activity_links(self, project: str, record_id: str) -> list[ActivityLink]:
        return list(self._activity_links.get(record_id, []))

    def link_activity(self, cmd: LinkActivity) -> CommandResult:
        self.schedule_commands.append(cmd)
        return CommandResult(stream_id="LINK-1", key=None, version=1, events=[])

    def publish_schedule_snapshot(self, cmd: PublishScheduleSnapshot) -> CommandResult:
        if not self.is_controller:  # type: ignore[attr-defined]
            raise ForbiddenError("this command needs the document_controller or admin role")
        self.schedule_commands.append(cmd)
        return CommandResult(stream_id=cmd.snapshot_id, key=None, version=1, events=[])

    # --- cost --------------------------------------------------------------------------------

    def list_cost_snapshots(self, project: str) -> list[cost_views.CostSnapshotView]:
        return list(self._cost_snapshots.get(project, []))

    def list_cost_codes(
        self,
        project: str,
        *,
        parent: str | None = None,
        q: str | None = None,
        limit: int = 1000,
    ) -> list[cost_views.CostCodeView]:
        needle = q.lower() if q else None
        found: list[cost_views.CostCodeView] = []
        for code in sorted(self._cost_codes.get(project, {})):
            detail = self._cost_codes[project][code]
            if parent is not None and detail.parent_code != parent:
                continue
            if (
                needle is not None
                and needle not in code.lower()
                and needle not in detail.title.lower()
            ):
                continue
            found.append(
                cost_views.CostCodeView(**detail.model_dump(exclude={"children", "history"}))
            )
        return found[: max(1, min(limit, cost_views.MAX_CODES))]

    def get_cost_code(self, project: str, code: str) -> cost_views.CostCodeDetailView:
        found = self._cost_codes.get(project, {}).get(code)
        if found is None:
            raise CostCodeNotFoundError(f"no cost code {code!r} in project:{project}")
        return found
