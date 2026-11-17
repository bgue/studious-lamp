"""The form source of an inspection (V3-F1s; the contract is ``tl_core.forms.types``).

A Scheduled inspection offers the questions of its pinned checklist; the answers go to the module's
own ``RecordInspectionResult`` (the word ``quality.inspection.record`` decides, not a forms word).
A pure read under the viewer: the hidden test comes first, so a hidden inspection answers ``None``
exactly as an absent one does, and the pinned checklist is read under the same viewer. The rules
are ``insp_rules`` (never copied here).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.forms import rules
from tl_core.forms.types import FormBinding, FormSource, TemplateRef

from tl_mod_quality import insp_rules
from tl_mod_quality.names import CHECKLIST, CHECKLIST_TABLE, INSPECTION, INSPECTION_TABLE, SCHEDULED

#: The access word the viewer needs to read an inspection (``schema/settings/access-words.yaml``).
VIEW_WORD = "quality.view"
COMMAND = "RecordInspectionResult"
ANSWERS_ARG = "answers"
#: Fixed words for a record the viewer reads but that takes no form now.
REASON_NO_CHECKLIST = "no_checklist"
REASON_RECORDED = "already_recorded"
REASON_CANCELLED = "cancelled"
REASON_NOT_SCHEDULED = "not_scheduled"

_ROW = text(
    "SELECT r.version AS version, COALESCE(ws.state, 'Planned') AS state, i.checklist_id AS cid, "
    f"i.id AS id FROM {INSPECTION_TABLE} i JOIN cur_core_record r ON r.id = i.id "
    "LEFT JOIN cur_workflow_state ws ON ws.record_id = i.id "
    "WHERE i.id = :id AND r.type = :type AND r.voided = :no"
)
_CHECKLIST_TEMPLATE = (
    "SELECT c.questions_json AS questions, c.checklist_version AS version "
    f"FROM {CHECKLIST_TABLE} c WHERE c.id = :cid"
)


def _unavailable(record_id: str, reason: str) -> FormBinding:
    return FormBinding(record_type=INSPECTION, key=record_id, available=False, reason=reason)


class InspectionFormSource:
    """The form source of ``quality.Inspection``."""

    record_type = INSPECTION
    view_word = VIEW_WORD

    def _questions(
        self, conn: Connection, checklist_id: str, viewer: confidentiality.Viewer
    ) -> tuple[list[dict[str, Any]], int] | None:
        visible, extra = confidentiality.not_hidden("c.id", viewer)
        found = (
            conn.execute(
                text(f"{_CHECKLIST_TEMPLATE} AND {visible}"),
                {"cid": checklist_id, **extra},
            )
            .mappings()
            .first()
        )
        if found is None:
            return None
        raw = found["questions"]
        questions: list[dict[str, Any]] = raw if isinstance(raw, list) else json.loads(str(raw))
        return questions, int(found["version"])

    def binding(
        self, conn: Connection, record_id: str, viewer: confidentiality.Viewer, now: datetime
    ) -> FormBinding | None:
        with confidentiality.use_viewer(viewer):
            if confidentiality.is_hidden(conn, record_id, viewer):
                return None
            row = (
                conn.execute(_ROW, {"id": record_id, "type": INSPECTION, "no": False})
                .mappings()
                .first()
            )
            if row is None:
                return None
            state = str(row["state"])
            if state != SCHEDULED:
                reason = {
                    "Cancelled": REASON_CANCELLED,
                    "Planned": REASON_NO_CHECKLIST,
                }.get(state, REASON_RECORDED)
                return _unavailable(record_id, reason)
            if row["cid"] is None:
                return _unavailable(record_id, REASON_NO_CHECKLIST)
            pinned = self._questions(conn, str(row["cid"]), viewer)
        if pinned is None:
            return _unavailable(record_id, REASON_NO_CHECKLIST)
        questions, version = pinned
        return FormBinding(
            record_type=INSPECTION,
            key=record_id,
            template=TemplateRef(
                source_type=CHECKLIST,
                source_id=str(row["cid"]),
                version=version,
                fmt=1,
                content_hash=rules.content_hash(questions, fmt=1),
            ),
            available=True,
            command=COMMAND,
            fixed_args={"inspection": record_id},
            answers_arg=ANSWERS_ARG,
            expected_version=int(row["version"]),
        )

    # What the one runner that sends a binding (``tl_mod_forms.bound``) asks of a source ---------

    def fields(
        self, conn: Connection, binding: FormBinding, viewer: confidentiality.Viewer
    ) -> list[dict[str, Any]]:
        """The questions the binding's template names, read under the viewer."""
        assert binding.template is not None
        with confidentiality.use_viewer(viewer):
            found = self._questions(conn, binding.template.source_id, viewer)
        return [] if found is None else found[0]

    def problems(self, fields: list[dict[str, Any]], answers: list[dict[str, Any]]) -> list[str]:
        """The module's own answer rules (``insp_rules``)."""
        return insp_rules.validate_answers(fields, answers)

    def arguments(self, binding: FormBinding, answers: list[dict[str, Any]]) -> dict[str, Any]:
        """The arguments of ``RecordInspectionResult``: the answers go in as they are."""
        args: dict[str, Any] = dict(binding.fixed_args)
        args[ANSWERS_ARG] = answers
        if binding.expected_version is not None:
            args["expected_version"] = binding.expected_version
        return args


def source() -> FormSource:
    """The entry point ``throughline.form_sources`` names for ``quality.Inspection``."""
    return InspectionFormSource()
