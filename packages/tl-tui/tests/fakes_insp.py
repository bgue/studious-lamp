"""In-memory inspection and checklist reads for `FakeClient` (P2-INSP-T08).

It holds the inspections and checklists a test gave it, per project (`load_inspections`,
`load_checklists`), and answers each read with the filters of the matching view
(``tl_mod_quality.insp_views``): state, point, area, inspector, subject, the work package (``for``)
for inspections; state and discipline for checklists. Each list is sorted by key and cut to
``limit`` (1 to ``MAX_LIMIT``); ``total`` counts the matches before the cut. A missing key raises
`RecordNotFoundError` with the route's text. `quality_command` takes any model of
``QUALITY_COMMANDS`` and records it in `punch_commands` (the list the punch fake uses), after the
same name check as the embedded client; this mixin comes before the punch mixin in `FakeClient`, so
its door is the one that runs. `seed_inspections` makes the six inspections and three checklists
the inspection screen tests share.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from fakes_punch import FakePunchSupport
from tl_api.routes.insp import MSG_CHECKLIST_NOT_FOUND, MSG_INSPECTION_NOT_FOUND
from tl_core.auth.errors import ForbiddenError
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_mod_quality import insp_views
from tl_mod_quality.module import PUNCH_COMMANDS, QUALITY_COMMANDS
from tl_mod_quality.names import (
    CANCELLED,
    DONE,
    DRAFT,
    PLANNED,
    POINTS,
    PUBLISHED,
    RETIRED,
    SCHEDULED,
    VERIFIED,
)


class FakeInspSupport:
    """Mixin for `FakeClient`: call `_init_insp()` from its `__init__`."""

    punch_commands: list[Command]  # set by the punch mixin's `_init_punch()`

    def _init_insp(self) -> None:
        self._inspections: dict[str, list[insp_views.InspectionDetail]] = {}
        self._checklists: dict[str, list[insp_views.ChecklistDetail]] = {}

    # --- seeding -----------------------------------------------------------------------------

    def load_inspections(
        self, project: str, details: Sequence[insp_views.InspectionDetail]
    ) -> None:
        """Replace one project's inspections. Each detail's ``row`` is what the lists show."""
        self._inspections[project] = list(details)

    def load_checklists(self, project: str, details: Sequence[insp_views.ChecklistDetail]) -> None:
        """Replace one project's checklists. Each detail's ``row`` is what the lists show."""
        self._checklists[project] = list(details)

    # --- reads -------------------------------------------------------------------------------

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
        if state is not None and state not in insp_views.INSPECTION_STATES:
            raise ValueError(insp_views.MSG_STATE)
        if point is not None and point not in POINTS:
            raise ValueError(insp_views.MSG_POINT)
        cap = max(1, min(int(limit), insp_views.MAX_LIMIT))
        matches: list[insp_views.InspectionRow] = []
        for item in sorted(self._inspections.get(project, []), key=lambda d: d.row.key):
            row = item.row
            if state is not None and row.state != state:
                continue
            if point is not None and row.point != point:
                continue
            if area is not None and row.area != area:
                continue
            if inspector is not None and row.inspector != inspector:
                continue
            if subject is not None and row.subject_key != subject:
                continue
            if for_key is not None and row.for_key != for_key:
                continue
            matches.append(row)
        return insp_views.InspectionPage(rows=matches[:cap], total=len(matches))

    def get_inspection(self, project: str, key: str) -> insp_views.InspectionDetail:
        for item in self._inspections.get(project, []):
            if item.row.key == key:
                return item
        raise RecordNotFoundError(MSG_INSPECTION_NOT_FOUND)

    def list_checklists(
        self,
        project: str,
        *,
        state: str | None = None,
        discipline: str | None = None,
        limit: int = 200,
    ) -> insp_views.ChecklistPage:
        if state is not None and state not in insp_views.CHECKLIST_STATES:
            raise ValueError(insp_views.MSG_CHECKLIST_STATE)
        cap = max(1, min(int(limit), insp_views.MAX_LIMIT))
        matches: list[insp_views.ChecklistRow] = []
        for item in sorted(self._checklists.get(project, []), key=lambda d: d.row.key):
            row = item.row
            if state is not None and row.state != state:
                continue
            if discipline is not None and row.discipline != discipline:
                continue
            matches.append(row)
        return insp_views.ChecklistPage(rows=matches[:cap], total=len(matches))

    def get_checklist(self, project: str, key: str) -> insp_views.ChecklistDetail:
        for item in self._checklists.get(project, []):
            if item.row.key == key:
                return item
        raise RecordNotFoundError(MSG_CHECKLIST_NOT_FOUND)

    # --- the write door ----------------------------------------------------------------------

    def quality_command(self, name: str, cmd: Command) -> CommandResult:
        if any(c.model.__name__ == name for c in PUNCH_COMMANDS):
            # the punch door, called as the punch mixin's own function (not through self, which
            # resolves to this method)
            return FakePunchSupport.quality_command(cast(FakePunchSupport, self), name, cmd)
        spec = next((c for c in QUALITY_COMMANDS if c.model.__name__ == name), None)
        if spec is None or type(cmd) is not spec.model:
            raise ForbiddenError(f"{name} is not a quality command")
        self.punch_commands.append(cmd)
        return CommandResult(stream_id="INS-1", key=None, version=1, events=[])


def _checklist(n: int, state: str, discipline: str | None) -> insp_views.ChecklistDetail:
    row = insp_views.ChecklistRow(
        id=f"CHK-{n}",
        key=f"P123-CHK-{n:04d}",
        title=f"Checklist {n}",
        discipline=discipline,
        version=1,
        state=state,
        question_count=1,
    )
    published = state in (PUBLISHED, RETIRED)
    return insp_views.ChecklistDetail(
        row=row,
        questions=[
            {
                "id": "q1",
                "text": "Gauge fitted?",
                "kind": "yes_no_na",
                "required": True,
                "unit": None,
                "min": None,
                "max": None,
                "choices": None,
                "fails_when": "no",
            }
        ],
        supersedes_key=None,
        published_by="user:sue" if published else None,
        published_on="2026-10-01" if published else None,
        retired_on="2026-11-01" if state == RETIRED else None,
        record_version=1,
    )


def _inspection(
    n: int,
    state: str,
    *,
    point: str,
    area: str | None,
    subject_key: str,
    inspector: str | None = None,
    for_key: str | None = None,
    result: str | None = None,
    done_on: str | None = None,
    punch_keys: Sequence[str] = (),
    cancel_reason: str | None = None,
    answers: Sequence[dict[str, Any]] = (),
    failed: Sequence[insp_views.FailedAnswer] = (),
) -> insp_views.InspectionDetail:
    """One inspection of the seed: the row and the facts a state carries."""
    scheduled = state in (SCHEDULED, DONE, VERIFIED)
    row = insp_views.InspectionRow(
        id=f"INS-{n}",
        key=f"P123-INS-{n:04d}",
        title=f"Inspection {n}",
        subject_key=subject_key,
        for_key=for_key,
        state=state,
        point=point,
        area=area,
        planned_on="2026-10-01",
        scheduled_for="2026-12-01" if scheduled else None,
        inspector=inspector,
        result=result,
        done_on=done_on,
        punch_count=len(punch_keys),
    )
    done = state in (DONE, VERIFIED)
    return insp_views.InspectionDetail(
        row=row,
        checklist_key="P123-CHK-0002" if scheduled else None,
        checklist_version=1 if scheduled else None,
        answers=list(answers),
        note=None,
        done_at=f"{done_on}T09:00:00Z" if done and done_on else None,
        recorded_by="user:rob" if done else None,
        verified_by="user:sue" if state == VERIFIED else None,
        verified_on="2026-10-05" if state == VERIFIED else None,
        reinspection_of_key=None,
        cancel_reason=cancel_reason,
        punch_keys=list(punch_keys),
        version=1,
        failed=list(failed),
    )


def seed_inspections(client: FakeInspSupport, project: str = "P123") -> list[str]:
    """Six inspections and three checklists for ``project``; the inspection keys in key order.

    Inspections: Planned (hold), Scheduled (hold, inspector M. Okafor), Done with a Reject result
    (witness, one punch item, one failed answer "Gauge fitted?" with the note "Gauge
    missing"), Verified (review, Pass), Cancelled (surveillance) and Planned for
    the work package P123-IWP-0001. Checklists: Draft, Published and Retired.
    """
    inspections = [
        _inspection(1, PLANNED, point="hold", area="L1", subject_key="P123-CWP-0001"),
        _inspection(
            2,
            SCHEDULED,
            point="hold",
            area="L2",
            subject_key="P123-CWP-0001",
            inspector="M. Okafor",
        ),
        _inspection(
            3,
            DONE,
            point="witness",
            area="L2",
            subject_key="P123-CWP-0002",
            inspector="M. Okafor",
            result="Reject",
            done_on="2026-10-03",
            punch_keys=["P123-PUN-0001"],
            answers=[{"q": "q1", "value": "no", "note": "Gauge missing"}],
            failed=[insp_views.FailedAnswer(question="Gauge fitted?", note="Gauge missing")],
        ),
        _inspection(
            4,
            VERIFIED,
            point="review",
            area="L3",
            subject_key="P123-CWP-0002",
            inspector="R. Ferrari",
            result="Pass",
            done_on="2026-10-02",
        ),
        _inspection(
            5,
            CANCELLED,
            point="surveillance",
            area="L1",
            subject_key="P123-CWP-0003",
            cancel_reason="Area closed",
        ),
        _inspection(
            6,
            PLANNED,
            point="hold",
            area="L1",
            subject_key="P123-CWP-0003",
            for_key="P123-IWP-0001",
        ),
    ]
    client.load_inspections(project, inspections)
    client.load_checklists(
        project,
        [
            _checklist(1, DRAFT, "Mechanical"),
            _checklist(2, PUBLISHED, "Piping"),
            _checklist(3, RETIRED, "Mechanical"),
        ],
    )
    return [item.row.key for item in inspections]
