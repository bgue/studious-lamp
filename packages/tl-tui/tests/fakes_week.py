"""In-memory awp progress, weekly-plan and look-ahead reads, and the two awp command doors, for
`FakeClient` (P2-I5 T11b).

The fake answers from what a test loads (`load_weeks`, `load_progress`, `load_hashes`,
`load_counts`, `load_kpis`, `load_look_ahead`, `load_miss_reasons`). It filters and sorts them the
way the views and routes do (counts by number, weeks latest first, limits clamped the way the views
clamp them) and raises `RecordNotFoundError` with the routes' text for an unloaded week or IWP
number. The look-ahead has no schedules to check: an unloaded look-ahead raises
`ScheduleNotFoundError`. The fake has no viewer: what a test loads is what a reader may see.

`awp_command` and `constraint_command` check the name and the class first, as the API client does
(`ForbiddenError` before anything is recorded). A call that passes is appended to
`self.sent_commands` as `(name, cmd)` and answered with a `CommandResult` (stream id "fake",
version 1), or, when a test sets `self.command_error`, raises that error after it is recorded.

`seed_week` gives it the shape the acceptance seed uses: two plans (2026-W44 Closed with ppc 66.7
and three commitments; 2026-W45 Committed), three IWP count rows, two KPI tiles, one look-ahead of
two activities and two IWPs, and three miss reasons.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from decimal import Decimal

from tl_api.routes.awp_progress import IwpHash, IwpProgress, RollupBody
from tl_core.auth.errors import ForbiddenError
from tl_core.constraints import commands as constraint_commands
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp import week_views
from tl_mod_awp.commands import AWP_COMMANDS
from tl_mod_awp.iwp_counts import COUNTS_LIMIT, IwpCountRow
from tl_mod_awp.kpis import KpiTile
from tl_mod_awp.look_ahead_view import LookAheadItem, LookAheadIwp, LookAheadView
from tl_mod_schedule.errors import ScheduleNotFoundError
from tl_mod_schedule.lookahead import LookAheadRow

PROJECT = "P123"


def _clamp(limit: int, most: int) -> int:
    return max(1, min(int(limit), most))


class FakeWeekSupport:
    """Mixin for `FakeClient`: call `_init_week()` from its `__init__`."""

    def _init_week(self) -> None:
        self._weeks: dict[str, dict[str, week_views.WeekDetail]] = {}
        self._progress: dict[str, dict[str, IwpProgress]] = {}
        self._hashes: dict[str, dict[str, IwpHash]] = {}
        self._counts: dict[str, list[IwpCountRow]] = {}
        self._kpis: dict[str, list[KpiTile]] = {}
        self._awp_look_aheads: dict[str, LookAheadView] = {}
        self._miss_reasons: dict[str, list[str]] = {}
        self.sent_commands: list[tuple[str, Command]] = []
        self.command_error: Exception | None = None

    # --- seeding -----------------------------------------------------------------------------

    def load_weeks(self, project: str, plans: Mapping[str, week_views.WeekDetail]) -> None:
        """The weekly plans of ``project`` by their ISO week (``YYYY-Www``)."""
        self._weeks[project] = {week: plan.model_copy(deep=True) for week, plan in plans.items()}

    def load_progress(self, project: str, progress: Mapping[str, IwpProgress]) -> None:
        """The earned progress of IWPs of ``project`` by number."""
        self._progress[project] = {n: p.model_copy(deep=True) for n, p in progress.items()}

    def load_hashes(self, project: str, hashes: Mapping[str, IwpHash]) -> None:
        """The record hashes of IWPs of ``project`` by number."""
        self._hashes[project] = {n: h.model_copy(deep=True) for n, h in hashes.items()}

    def load_counts(self, project: str, rows: Iterable[IwpCountRow] = ()) -> None:
        """The IWP log counts of ``project``."""
        self._counts[project] = [row.model_copy(deep=True) for row in rows]

    def load_kpis(self, project: str, tiles: Iterable[KpiTile] = ()) -> None:
        """The KPI tiles of ``project``, in the order given."""
        self._kpis[project] = [tile.model_copy(deep=True) for tile in tiles]

    def load_look_ahead(self, project: str, view: LookAheadView) -> None:
        """The look-ahead of ``project``, whatever schedule a test names."""
        self._awp_look_aheads[project] = deepcopy(view)

    def load_miss_reasons(self, project: str, reasons: Iterable[str] = ()) -> None:
        """The miss-reason keys of ``project``."""
        self._miss_reasons[project] = list(reasons)

    # --- the reads ---------------------------------------------------------------------------

    def list_iwp_counts(self, project: str) -> list[IwpCountRow]:
        found = sorted(self._counts.get(project, []), key=lambda row: row.number)
        return [row.model_copy(deep=True) for row in found[:COUNTS_LIMIT]]

    def get_iwp_progress(self, project: str, number: str) -> IwpProgress:
        found = self._progress.get(project, {}).get(number)
        if found is None:
            raise RecordNotFoundError(f"no IWP {number!r}")
        return found.model_copy(deep=True)

    def get_progress_rollup(self, project: str) -> RollupBody:
        # No rollup is loaded by the fake: it answers the empty roll-up of the project.
        return RollupBody(
            scope=f"project:{project}", as_of_seq=0, cwps=[], nodes=[], lines=[], notes=[]
        )

    def get_iwp_hash(self, project: str, number: str) -> IwpHash:
        found = self._hashes.get(project, {}).get(number)
        if found is None:
            raise RecordNotFoundError(f"no IWP {number!r}")
        return found.model_copy(deep=True)

    def list_kpis(self, project: str) -> list[KpiTile]:
        return [tile.model_copy(deep=True) for tile in self._kpis.get(project, [])]

    def list_weekly_plans(self, project: str, *, limit: int = 60) -> list[week_views.WeekRow]:
        plans = self._weeks.get(project, {})
        newest_first = sorted(plans.values(), key=lambda plan: plan.week, reverse=True)
        rows = [
            week_views.WeekRow(**plan.model_dump(include=set(week_views.WeekRow.model_fields)))
            for plan in newest_first
        ]
        return rows[: _clamp(limit, week_views.MAX_WEEKS)]

    def get_weekly_plan(self, project: str, week: str) -> week_views.WeekDetail:
        found = self._weeks.get(project, {}).get(week)
        if found is None:
            raise RecordNotFoundError(f"no week {week!r}")
        return found.model_copy(deep=True)

    def list_miss_reasons(self, project: str) -> list[str]:
        return list(self._miss_reasons.get(project, []))

    def get_awp_look_ahead(
        self, project: str, schedule: str, *, snapshot: int | None = None, weeks: int = 4
    ) -> LookAheadView:
        found = self._awp_look_aheads.get(project)
        if found is None:
            raise ScheduleNotFoundError(f"the fake has no look-ahead for {schedule}")
        return deepcopy(found)

    # --- the two command doors ---------------------------------------------------------------

    def awp_command(self, name: str, cmd: Command) -> CommandResult:
        spec = next((c for c in AWP_COMMANDS if c.model.__name__ == name), None)
        if spec is None or type(cmd) is not spec.model:
            raise ForbiddenError(f"{name} is not an awp command")
        return self._record_command(name, cmd)

    def constraint_command(self, name: str, cmd: Command) -> CommandResult:
        spec = next(
            (c for c in constraint_commands.command_table() if c.model.__name__ == name), None
        )
        if spec is None or type(cmd) is not spec.model:
            raise ForbiddenError(f"{name} is not a constraint command")
        return self._record_command(name, cmd)

    def _record_command(self, name: str, cmd: Command) -> CommandResult:
        self.sent_commands.append((name, cmd))
        if self.command_error is not None:
            raise self.command_error
        return CommandResult(stream_id="fake", key=None, version=1, events=[])


# --- the acceptance seed ---------------------------------------------------------------------


def _commitment(
    key: str, state: str, outcome: str | None, reason: str | None
) -> week_views.CommitmentRow:
    return week_views.CommitmentRow(
        iwp_id=f"IWP-{key}",
        iwp_key=f"{PROJECT}-IWP-PIP-{key}",
        iwp_state=state,
        foreman="user:uma",
        committed_hours="40.0",
        outcome=outcome,
        miss_reason=reason,
    )


def _plan(
    n: int,
    week: str,
    week_start: str,
    state: str,
    *,
    ppc: str | None,
    closed_at: str | None,
    commitments: list[week_views.CommitmentRow],
) -> week_views.WeekDetail:
    return week_views.WeekDetail(
        id=f"PLAN-{n}",
        key=f"{PROJECT}-WK-{n}",
        week=week,
        week_start=week_start,
        state=state,
        ppc=ppc,
        closed_at=closed_at,
        version=3 if state == "Closed" else 1,
        commitments=commitments,
        notes=[],
    )


def seed_week(client: FakeWeekSupport, project: str = PROJECT) -> None:
    """The acceptance seed's shape on ``client``: two plans, three count rows, two KPI tiles, one
    look-ahead of two activities and two IWPs, and three miss reasons."""
    closed = _plan(
        1,
        "2026-W44",
        "2026-10-26",
        "Closed",
        ppc="66.7",
        closed_at="2026-11-02",
        commitments=[
            _commitment("0001", "Issued", "done", None),
            _commitment("0002", "Issued", "done", None),
            _commitment("0003", "Issued", "missed", "Weather"),
        ],
    )
    committed = _plan(
        2,
        "2026-W45",
        "2026-11-02",
        "Committed",
        ppc=None,
        closed_at=None,
        commitments=[_commitment("0001", "Issued", None, None)],
    )
    client.load_weeks(PROJECT, {"2026-W44": closed, "2026-W45": committed})
    client.load_counts(
        PROJECT,
        [
            IwpCountRow(
                number=f"{PROJECT}-IWP-PIP-0001",
                state_since="2026-10-20",
                ready_ok=9,
                ready_total=9,
                evaluated=True,
                open_blocking=0,
            ),
            IwpCountRow(
                number=f"{PROJECT}-IWP-PIP-0002",
                state_since="2026-10-27",
                ready_ok=5,
                ready_total=9,
                evaluated=True,
                open_blocking=1,
            ),
            IwpCountRow(
                number=f"{PROJECT}-IWP-PIP-0003",
                state_since=None,
                ready_ok=0,
                ready_total=0,
                evaluated=False,
                open_blocking=0,
            ),
        ],
    )
    client.load_kpis(
        PROJECT,
        [
            KpiTile(
                name="kpi_ppc",
                value=Decimal("66.7"),
                numerator=2,
                denominator=3,
                detail="2 of 3 committed IWPs done, last 2 closed weeks",
            ),
            KpiTile(
                name="kpi_constraint_free",
                value=Decimal("50.0"),
                numerator=1,
                denominator=2,
                detail="1 of 2 committed IWPs free of open blocking constraints",
            ),
        ],
    )
    activity_a = LookAheadRow(
        activity_id="A1230",
        name="Pipe rack erection",
        wbs_path="1.2",
        status="Not Started",
        phase="starting",
        early_start="2026-11-09",
        early_finish="2026-11-20",
        total_float_days=3.0,
        critical=True,
        percent_complete=0.0,
    )
    activity_b = LookAheadRow(
        activity_id="A1240",
        name="Cable tray install",
        wbs_path="1.3",
        status="In Progress",
        phase="in_progress",
        early_start="2026-11-02",
        early_finish="2026-11-16",
        total_float_days=None,
        critical=False,
        percent_complete=25.0,
    )
    iwp_one = LookAheadIwp(
        id="IWP-1",
        number=f"{PROJECT}-IWP-PIP-0001",
        state="Ready",
        planned_start="2026-12-01",
        need_by="2026-11-17",
        evaluated=True,
        ready=True,
        checks_ok=9,
        checks_total=9,
        open_blocking=0,
    )
    iwp_two = LookAheadIwp(
        id="IWP-2",
        number=f"{PROJECT}-IWP-PIP-0002",
        state="Issued",
        planned_start="2026-12-08",
        need_by="2026-11-24",
        evaluated=False,
        ready=False,
        checks_ok=0,
        checks_total=0,
        open_blocking=1,
    )
    view = LookAheadView(
        snapshot_key="MAIN@1",
        data_date="2026-11-02",
        window_start="2026-11-02",
        window_end="2026-11-30",
        weeks=4,
        lead_weeks=2,
        counts={"starting": 1, "in_progress": 1, "late_start": 0, "total": 2, "critical": 1},
        items=(
            LookAheadItem(row=activity_a, iwps=(iwp_one,)),
            LookAheadItem(row=activity_b, iwps=(iwp_two,)),
        ),
    )
    client.load_look_ahead(PROJECT, view)
    client.load_miss_reasons(PROJECT, ["Weather", "Materials", "Design"])


__all__ = ["FakeWeekSupport", "PROJECT", "seed_week"]
