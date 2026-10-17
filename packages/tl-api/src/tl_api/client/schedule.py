"""The schedule module's reads over HTTP: schedules, snapshots, activities, comparison (P1-I4).

The same models the embedded services return (``tl_mod_schedule.views`` and the frozen dataclasses
of ``compare``, ``lookahead`` and ``resolver``). The module's errors (``ScheduleNotFoundError``,
``SnapshotNotFoundError`` and the rest) are rebuilt from the error body.
"""

from __future__ import annotations

from pydantic import TypeAdapter
from tl_core.services.commands import CommandResult
from tl_mod_schedule import views
from tl_mod_schedule.compare import Comparison
from tl_mod_schedule.handlers.activity import LinkActivity
from tl_mod_schedule.handlers.publish import PublishScheduleSnapshot
from tl_mod_schedule.handlers.schedules import DefineSchedule
from tl_mod_schedule.handlers.snapshots import (
    OpenScheduleSnapshot,
    StartScheduleSnapshot,
    VoidScheduleSnapshot,
)
from tl_mod_schedule.lookahead import LookAhead
from tl_mod_schedule.resolver import ActivityLink, OrphanedLink, Resolution

from tl_api.client.base import ApiClientBase, quote


def _bool(value: bool | None) -> str | None:
    return None if value is None else ("true" if value else "false")


class ScheduleApi(ApiClientBase):
    def list_schedules(self, project: str) -> list[views.ScheduleView]:
        """A project's schedules (``GET /projects/{project}/schedules``)."""
        data = self._get_json(f"/projects/{quote(project)}/schedules")
        return self._models(views.ScheduleView, data)

    def get_schedule(self, project: str, code: str) -> views.ScheduleDetailView:
        """One schedule with its snapshots (``GET /projects/{project}/schedules/{code}``)."""
        data = self._get_json(f"/projects/{quote(project)}/schedules/{quote(code)}")
        return self._model(views.ScheduleDetailView, data)

    def get_schedule_snapshot(self, project: str, code: str, number: int) -> views.SnapshotView:
        """One snapshot by number (``GET .../schedules/{code}/snapshots/{number}``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/schedules/{quote(code)}/snapshots/{number}"
        )
        return self._model(views.SnapshotView, data)

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
        """A page of a built snapshot's activities (``GET .../schedules/{code}/activities``)."""
        params = {
            "snapshot": snapshot,
            "critical": _bool(critical),
            "status": status,
            "q": q,
            "limit": limit,
            "offset": offset,
        }
        data = self._get_json(
            f"/projects/{quote(project)}/schedules/{quote(code)}/activities", params
        )
        return TypeAdapter(views.ActivityPage).validate_python(data)

    def compare_snapshots(
        self,
        project: str,
        code: str,
        *,
        new: int | None = None,
        old: int | None = None,
        limit: int = views.DEFAULT_COMPARE_LIMIT,
    ) -> Comparison:
        """What changed between two built snapshots (``GET .../schedules/{code}/comparison``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/schedules/{quote(code)}/comparison",
            {"new": new, "old": old, "limit": limit},
        )
        return TypeAdapter(Comparison).validate_python(data)

    def get_look_ahead(
        self, project: str, code: str, *, snapshot: int | None = None, weeks: int = 4
    ) -> LookAhead:
        """The look-ahead of a built snapshot (``GET .../schedules/{code}/look-ahead``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/schedules/{quote(code)}/look-ahead",
            {"snapshot": snapshot, "weeks": weeks},
        )
        return TypeAdapter(LookAhead).validate_python(data)

    def list_orphaned_links(self, project: str, code: str) -> list[OrphanedLink]:
        """Links flagged because their activity left the schedule (``.../orphans``)."""
        data = self._get_json(f"/projects/{quote(project)}/schedules/{quote(code)}/orphans")
        return TypeAdapter(list[OrphanedLink]).validate_python(data)

    def get_schedule_activity(
        self, project: str, code: str, activity_id: str, *, snapshot: int | None = None
    ) -> views.ActivityDetail:
        """One activity with its relationships (``.../activity-details/{activity_id}``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/schedules/{quote(code)}"
            f"/activity-details/{quote(activity_id)}",
            {"snapshot": snapshot},
        )
        return TypeAdapter(views.ActivityDetail).validate_python(data)

    def get_activity_trend(
        self, project: str, code: str, activity_id: str
    ) -> list[views.TrendPoint]:
        """The activity in every published snapshot (``.../activity-trends/{activity_id}``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/schedules/{quote(code)}"
            f"/activity-trends/{quote(activity_id)}"
        )
        return TypeAdapter(list[views.TrendPoint]).validate_python(data)

    def resolve_activity(
        self, project: str, code: str, activity_id: str, *, as_of: str | None = None
    ) -> Resolution:
        """What the activity is now or as of a snapshot or date (``.../activity-resolutions``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/schedules/{quote(code)}"
            f"/activity-resolutions/{quote(activity_id)}",
            {"as_of": as_of},
        )
        return TypeAdapter(Resolution).validate_python(data)

    def list_activity_links(self, project: str, record_id: str) -> list[ActivityLink]:
        """The activity links of a record (``GET /projects/{p}/records/{id}/activity-links``)."""
        data = self._get_json(
            f"/projects/{quote(project)}/records/{quote(record_id)}/activity-links"
        )
        return TypeAdapter(list[ActivityLink]).validate_python(data)

    def define_schedule(self, cmd: DefineSchedule) -> CommandResult:
        """Register a schedule (``POST /commands/DefineSchedule``): a controller's act."""
        return self._command("DefineSchedule", cmd)

    def open_schedule_snapshot(self, cmd: OpenScheduleSnapshot) -> CommandResult:
        """Open the next snapshot of a schedule (``POST /commands/OpenScheduleSnapshot``)."""
        return self._command("OpenScheduleSnapshot", cmd)

    def start_schedule_snapshot(self, cmd: StartScheduleSnapshot) -> CommandResult:
        """Queue the build of a snapshot (``POST /commands/StartScheduleSnapshot``)."""
        return self._command("StartScheduleSnapshot", cmd)

    def publish_schedule_snapshot(self, cmd: PublishScheduleSnapshot) -> CommandResult:
        """Make a valid snapshot current (``POST /commands/PublishScheduleSnapshot``)."""
        return self._command("PublishScheduleSnapshot", cmd)

    def void_schedule_snapshot(self, cmd: VoidScheduleSnapshot) -> CommandResult:
        """Void a snapshot that is not published (``POST /commands/VoidScheduleSnapshot``)."""
        return self._command("VoidScheduleSnapshot", cmd)

    def link_activity(self, cmd: LinkActivity) -> CommandResult:
        """Link a record to an activity by its stable id (``POST /commands/LinkActivity``)."""
        return self._command("LinkActivity", cmd)
