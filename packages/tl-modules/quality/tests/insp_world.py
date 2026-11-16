"""The punch world plus checklists and inspections, for the S2 tests and the acceptance script.

People as in ``punch_world``: ``uma`` (user: plans, schedules), ``rob`` (user and a superuser
grant: records and may not verify what he recorded), ``sue`` (the quality superuser: publishes,
verifies, cancels), ``dora`` (the document controller, who reads restricted records), ``vera`` (a
viewer), ``ada`` (admin) and ``ian`` (a plain user with no module grant). Every row is made by a
real command.
"""

from __future__ import annotations

from typing import Any

from punch_world import IWP, SCOPE, World
from tl_mod_quality.names import CHECKLIST_TABLE, INSPECTION_TABLE

QUESTIONS: list[dict[str, Any]] = [
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
    },
    {
        "id": "q2",
        "text": "Label legible?",
        "kind": "yes_no_na",
        "required": False,
        "unit": None,
        "min": None,
        "max": None,
        "choices": None,
        "fails_when": "no",
    },
    {
        "id": "q3",
        "text": "Test pressure",
        "kind": "number",
        "required": False,
        "unit": "bar",
        "min": 1,
        "max": 10,
        "choices": None,
        "fails_when": "out_of_range",
    },
]


def answers(q1: str = "yes", q2: str = "yes", q3: float = 5, note: str | None = None) -> list[Any]:
    """Answers to ``QUESTIONS``; ``note`` goes on the first."""
    return [
        {"q": "q1", "value": q1, "note": note},
        {"q": "q2", "value": q2, "note": None},
        {"q": "q3", "value": q3, "note": None},
    ]


class InspWorld(World):
    def people(self) -> None:
        super().people()
        self.person("ian", ("user",))

    def checklist(
        self, *, publish: bool = True, questions: list[dict[str, Any]] | None = None, **more: Any
    ) -> str:
        """A checklist (its id), Published by ``sue`` unless ``publish`` is false."""
        made = self.call(
            "uma",
            "CreateChecklist",
            title=more.pop("title", "Hydrotest pre-check"),
            questions=QUESTIONS if questions is None else questions,
            **more,
        )
        if publish:
            self.call("sue", "PublishChecklist", checklist=made.stream_id)
        return str(made.stream_id)

    def plan(self, subject: str | None = None, who: str = "uma", **more: Any) -> str:
        """A Planned inspection (its id) of ``subject`` (a new IWP when not given)."""
        subject = subject or self.record(IWP, f"IWP-{self.count('cur_core_record')}")
        fields = {"title": "Flange make-up", "point": "hold", **more}
        return str(self.call(who, "PlanInspection", subject_id=subject, **fields).stream_id)

    def scheduled(
        self,
        subject: str | None = None,
        checklist: str | None = None,
        who: str = "uma",
        **more: Any,
    ) -> str:
        """A Scheduled inspection (its id) with a Published checklist."""
        item = self.plan(subject, who=who, **more)
        self.call(
            who,
            "ScheduleInspection",
            inspection=item,
            checklist=checklist or self.checklist(),
            scheduled_for="2026-12-01",
            inspector="M. Okafor",
        )
        return item

    def recorded(self, item: str, who: str = "rob", **more: Any) -> Any:
        return self.call(who, "RecordInspectionResult", inspection=item, **more)

    def inspection_row(self, record: str) -> dict[str, Any]:
        return self.rows(f"SELECT * FROM {INSPECTION_TABLE} WHERE id = :i", i=record)[0]

    def checklist_row(self, record: str) -> dict[str, Any]:
        return self.rows(f"SELECT * FROM {CHECKLIST_TABLE} WHERE id = :i", i=record)[0]

    def state_of(self, record: str, initial: str) -> str:
        found = self.scalar("SELECT status FROM cur_core_record WHERE id = :i", i=record)
        return initial if found is None else str(found)

    def raised_by(self, inspection: str) -> list[dict[str, Any]]:
        """The punch items linked ``raised_against`` the inspection, by key."""
        return self.rows(
            "SELECT p.id, r.key, r.title, p.category, p.source_id, p.raised_by, p.area "
            "FROM cur_links l JOIN cur_quality_punch_item p ON p.id = l.from_id "
            "JOIN cur_core_record r ON r.id = p.id "
            "WHERE l.to_id = :i AND l.relation = 'raised_against' AND l.status <> 'retracted' "
            "ORDER BY r.key",
            i=inspection,
        )

    def punch_total(self) -> int:
        return int(self.scalar("SELECT count(*) FROM cur_quality_punch_item"))


__all__ = ["IWP", "QUESTIONS", "SCOPE", "InspWorld", "answers"]
