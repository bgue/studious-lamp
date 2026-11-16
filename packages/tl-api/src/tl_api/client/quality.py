"""The quality module's punch and inspection reads over HTTP and its one write door (P2-PUNCH-T04,
P2-INSP-T08).

The same models the embedded client returns (``tl_mod_quality.views`` and
``tl_mod_quality.insp_views``: dataclasses, so they are decoded with a ``TypeAdapter``). A missing
or hidden item is the service's ``RecordNotFoundError``, rebuilt from the 404 body.
``quality_command(name, cmd)`` runs a model of ``tl_mod_quality.module.QUALITY_COMMANDS`` by name,
posted to ``/commands/<name>``.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter
from tl_core.auth.errors import ForbiddenError
from tl_core.services.commands import Command, CommandResult
from tl_mod_quality import insp_views
from tl_mod_quality import views as punch_views
from tl_mod_quality.module import QUALITY_COMMANDS

from tl_api.client.base import ApiClientBase, quote

_PAGE: TypeAdapter[punch_views.PunchPage] = TypeAdapter(punch_views.PunchPage)
_DETAIL: TypeAdapter[punch_views.PunchDetail] = TypeAdapter(punch_views.PunchDetail)
_INSP_PAGE: TypeAdapter[insp_views.InspectionPage] = TypeAdapter(insp_views.InspectionPage)
_INSP_DETAIL: TypeAdapter[insp_views.InspectionDetail] = TypeAdapter(insp_views.InspectionDetail)
_CHK_PAGE: TypeAdapter[insp_views.ChecklistPage] = TypeAdapter(insp_views.ChecklistPage)
_CHK_DETAIL: TypeAdapter[insp_views.ChecklistDetail] = TypeAdapter(insp_views.ChecklistDetail)


class QualityApi(ApiClientBase):
    def list_punch_items(
        self,
        project: str,
        *,
        state: str | None = None,
        area: str | None = None,
        system: str | None = None,
        assignee: str | None = None,
        category: str | None = None,
        from_key: str | None = None,
        overdue: bool = False,
        limit: int = 200,
    ) -> punch_views.PunchPage:
        """A project's punch items by key (``GET .../punch``; ``from`` is the source key)."""
        data: Any = self._get_json(
            f"/projects/{quote(project)}/punch",
            {
                "state": state,
                "area": area,
                "system": system,
                "assignee": assignee,
                "category": category,
                "from": from_key,
                "overdue": overdue,
                "limit": limit,
            },
        )
        return _PAGE.validate_python(data)

    def get_punch_item(self, project: str, key: str) -> punch_views.PunchDetail:
        """One punch item (``GET .../punch/{key}``); 404 for a missing or hidden item."""
        data: Any = self._get_json(f"/projects/{quote(project)}/punch/{quote(key)}")
        return _DETAIL.validate_python(data)

    def get_punch_counts(self, project: str) -> dict[str, int]:
        """The visible items by state (``GET .../punch-counts``)."""
        data: Any = self._get_json(f"/projects/{quote(project)}/punch-counts")
        return {str(state): int(n) for state, n in data.items()}

    def list_inspections(
        self,
        project: str,
        *,
        state: str | None = None,
        point: str | None = None,
        area: str | None = None,
        inspector: str | None = None,
        subject: str | None = None,
        for_key: str | None = None,
        limit: int = 200,
    ) -> insp_views.InspectionPage:
        """A project's inspections by key (``GET /quality/inspections?project=``; ``for`` is the
        work package key, ``subject`` the subject key); ``total`` counts the visible matches."""
        data: Any = self._get_json(
            "/quality/inspections",
            {
                "project": project,
                "state": state,
                "point": point,
                "area": area,
                "inspector": inspector,
                "subject": subject,
                "for": for_key,
                "limit": limit,
            },
        )
        return _INSP_PAGE.validate_python(data)

    def get_inspection(self, project: str, key: str) -> insp_views.InspectionDetail:
        """One inspection (``GET /quality/inspections/{key}``); 404 for a missing or hidden one."""
        data: Any = self._get_json(f"/quality/inspections/{quote(key)}", {"project": project})
        return _INSP_DETAIL.validate_python(data)

    def list_checklists(
        self,
        project: str,
        *,
        state: str | None = None,
        discipline: str | None = None,
        limit: int = 200,
    ) -> insp_views.ChecklistPage:
        """A project's checklists by key (``GET /quality/checklists?project=``)."""
        data: Any = self._get_json(
            "/quality/checklists",
            {"project": project, "state": state, "discipline": discipline, "limit": limit},
        )
        return _CHK_PAGE.validate_python(data)

    def get_checklist(self, project: str, key: str) -> insp_views.ChecklistDetail:
        """One checklist (``GET /quality/checklists/{key}``); 404 for a missing or hidden one."""
        data: Any = self._get_json(f"/quality/checklists/{quote(key)}", {"project": project})
        return _CHK_DETAIL.validate_python(data)

    def quality_command(self, name: str, cmd: Command) -> CommandResult:
        """Run a quality command by name (``POST /commands/<name>``, the token's actor).

        A name that is not in ``QUALITY_COMMANDS``, or a command of another class, raises
        ``ForbiddenError`` before anything is sent.
        """
        spec = next((c for c in QUALITY_COMMANDS if c.model.__name__ == name), None)
        if spec is None or type(cmd) is not spec.model:
            raise ForbiddenError(f"{name} is not a quality command")
        return self._command(name, cmd)
