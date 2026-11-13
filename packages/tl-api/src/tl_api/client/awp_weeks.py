"""The awp progress, weekly-plan and look-ahead reads over HTTP, and the two awp command doors
(P2-I5-T11b).

The same models the embedded client returns: ``tl_mod_awp`` views for the counts, the KPI tiles,
the weekly plans and the miss reasons, and the route models ``IwpProgress``, ``RollupBody`` and
``IwpHash`` for the rest. The look-ahead is rebuilt as the ``tl_mod_awp.look_ahead_view`` dataclass
from ``LookAheadBody``. A missing or hidden record raises the service's ``RecordNotFoundError``,
rebuilt from the 404 body. The command doors check the name and the class before anything is sent.
"""

from __future__ import annotations

from tl_core.auth.errors import ForbiddenError
from tl_core.constraints import commands as constraint_commands
from tl_core.services.commands import Command, CommandResult
from tl_mod_awp import week_views
from tl_mod_awp.commands import AWP_COMMANDS
from tl_mod_awp.iwp_counts import IwpCountRow
from tl_mod_awp.kpis import KpiTile
from tl_mod_awp.look_ahead_view import LookAheadItem, LookAheadIwp, LookAheadView
from tl_mod_schedule.lookahead import LookAheadRow

from tl_api.client.base import ApiClientBase, quote
from tl_api.routes.awp_progress import IwpHash, IwpProgress, RollupBody
from tl_api.routes.awp_weeks import LookAheadBody


class AwpWeeksApi(ApiClientBase):
    def list_iwp_counts(self, project: str) -> list[IwpCountRow]:
        """The IWP log counts by number (``GET .../awp/iwps/counts``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/iwps/counts")
        return self._models(IwpCountRow, data)

    def get_iwp_progress(self, project: str, number: str) -> IwpProgress:
        """The earned progress of one IWP (``GET .../awp/iwps/{number}/progress``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/iwps/{quote(number)}/progress")
        return self._model(IwpProgress, data)

    def get_progress_rollup(self, project: str) -> RollupBody:
        """The earned hours by CWP, node and cost code (``GET .../awp/progress/rollup``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/progress/rollup")
        return self._model(RollupBody, data)

    def get_iwp_hash(self, project: str, number: str) -> IwpHash:
        """The record hash of one IWP (``GET .../awp/iwps/{number}/hash``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/iwps/{quote(number)}/hash")
        return self._model(IwpHash, data)

    def list_kpis(self, project: str) -> list[KpiTile]:
        """The two KPI tiles, in their fixed order (``GET .../awp/kpis``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/kpis")
        return self._models(KpiTile, data)

    def list_weekly_plans(self, project: str, *, limit: int = 60) -> list[week_views.WeekRow]:
        """The weekly plans, the latest week first (``GET .../awp/weeks``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/weeks", {"limit": limit})
        return self._models(week_views.WeekRow, data)

    def get_weekly_plan(self, project: str, week: str) -> week_views.WeekDetail:
        """One weekly plan with its commitments (``GET .../awp/weeks/{week}``)."""
        data = self._get_json(f"/projects/{quote(project)}/awp/weeks/{quote(week)}")
        return self._model(week_views.WeekDetail, data)

    def list_miss_reasons(self, project: str) -> list[str]:
        """The keys of the miss-reason code list (``GET .../awp/miss-reasons``)."""
        data: list[str] = self._get_json(f"/projects/{quote(project)}/awp/miss-reasons")
        return list(data)

    def get_awp_look_ahead(
        self,
        project: str,
        schedule: str,
        *,
        snapshot: int | None = None,
        weeks: int = 4,
    ) -> LookAheadView:
        """The look-ahead joined with the IWPs linked to each activity (``.../awp/look-ahead``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/awp/look-ahead",
            {"schedule": schedule, "snapshot": snapshot, "weeks": weeks},
        )
        body = self._model(LookAheadBody, data)
        return LookAheadView(
            snapshot_key=body.snapshot_key,
            data_date=body.data_date,
            window_start=body.window_start,
            window_end=body.window_end,
            weeks=body.weeks,
            lead_weeks=body.lead_weeks,
            counts=dict(body.counts),
            items=tuple(
                LookAheadItem(
                    row=LookAheadRow(**item.row.model_dump()),
                    iwps=tuple(LookAheadIwp(**iwp.model_dump()) for iwp in item.iwps),
                )
                for item in body.items
            ),
        )

    def awp_command(self, name: str, cmd: Command) -> CommandResult:
        """Run an awp command by name (``POST /commands/<name>``, the token's actor).

        A name that is not in ``AWP_COMMANDS``, or a command of another class, raises
        ``ForbiddenError`` before anything is sent.
        """
        spec = next((c for c in AWP_COMMANDS if c.model.__name__ == name), None)
        if spec is None or type(cmd) is not spec.model:
            raise ForbiddenError(f"{name} is not an awp command")
        return self._command(name, cmd)

    def constraint_command(self, name: str, cmd: Command) -> CommandResult:
        """Run a constraint command by name (``POST /commands/<name>``, the token's actor).

        A name outside ``command_table()``, or a command of another class, raises
        ``ForbiddenError`` before anything is sent.
        """
        spec = next(
            (c for c in constraint_commands.command_table() if c.model.__name__ == name), None
        )
        if spec is None or type(cmd) is not spec.model:
            raise ForbiddenError(f"{name} is not a constraint command")
        return self._command(name, cmd)
