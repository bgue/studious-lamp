"""The form source of a permit (V3-F1s; the contract is ``tl_core.forms.types``).

An Approved permit offers the precaution list of its type as a yes/no form; the ticks go to the
module's own ``IssuePermit`` (the word ``permits.issue`` decides, not a forms word), which refuses
a precaution that is not ticked, a missing gas test or a missing isolation with its own rules. A
pure read under the viewer: the hidden test comes first, so a hidden permit answers ``None``
exactly as an absent one does. The template is the type's precaution list from the type table
(``types_table``), pinned by its content hash.

``answers_arg`` is ``precautions``: a client that sends the command itself sends the ids ticked
(answered ``yes``); ``arguments`` does that mapping for the runner (``tl_mod_forms.bound``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.forms import rules
from tl_core.forms.types import FormBinding, FormSource, TemplateRef

from tl_mod_permits.names import APPROVED, PERMIT, PERMIT_TABLE, REQUESTED, VIEW
from tl_mod_permits.types_table import load_types

VIEW_WORD = VIEW
COMMAND = "IssuePermit"
ANSWERS_ARG = "precautions"
SOURCE_TYPE = "permits.PermitType"
REASON_NOT_APPROVED = "not_approved"
TICKED = "yes"
FORMAT = 2

_ROW = text(
    "SELECT r.version AS version, COALESCE(w.state, :requested) AS state, "
    f"p.permit_type AS permit_type FROM {PERMIT_TABLE} p JOIN cur_core_record r ON r.id = p.id "
    "LEFT JOIN cur_workflow_state w ON w.record_id = p.id "
    "WHERE p.id = :id AND r.type = :type AND r.voided = :no"
)


def questions_of(permit_type: str) -> list[dict[str, Any]]:
    """The precaution list of a type as format 2 questions (a precaution id is not a ``q1`` id):
    each is a required yes or no, and a ``no`` is a fail."""
    rule = load_types().get(permit_type)
    if rule is None:
        return []
    return [
        {
            "id": p.id,
            "text": p.text,
            "kind": "yes_no_na",
            "required": True,
            "unit": None,
            "min": None,
            "max": None,
            "choices": None,
            "fails_when": "no",
            "section": None,
            "help": None,
            "visible_when": None,
        }
        for p in rule.precautions
    ]


class PermitFormSource:
    """The form source of ``permits.Permit``."""

    record_type = PERMIT
    view_word = VIEW_WORD

    def binding(
        self, conn: Connection, record_id: str, viewer: confidentiality.Viewer, now: datetime
    ) -> FormBinding | None:
        with confidentiality.use_viewer(viewer):
            if confidentiality.is_hidden(conn, record_id, viewer):
                return None
            row = (
                conn.execute(
                    _ROW, {"id": record_id, "type": PERMIT, "no": False, "requested": REQUESTED}
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        if str(row["state"]) != APPROVED:
            return FormBinding(
                record_type=PERMIT,
                key=record_id,
                available=False,
                reason=REASON_NOT_APPROVED,
                command=COMMAND,
            )
        permit_type = str(row["permit_type"])
        questions = questions_of(permit_type)
        if not questions:
            return FormBinding(
                record_type=PERMIT,
                key=record_id,
                available=False,
                reason=REASON_NOT_APPROVED,
                command=COMMAND,
            )
        return FormBinding(
            record_type=PERMIT,
            key=record_id,
            template=TemplateRef(
                source_type=SOURCE_TYPE,
                source_id=permit_type,
                version=1,
                fmt=FORMAT,
                content_hash=rules.content_hash(questions, fmt=FORMAT),
            ),
            available=True,
            command=COMMAND,
            fixed_args={"permit": record_id},
            answers_arg=ANSWERS_ARG,
            expected_version=int(row["version"]),
        )

    # What the one runner that sends a binding (``tl_mod_forms.bound``) asks of a source ---------

    def fields(
        self, conn: Connection, binding: FormBinding, viewer: confidentiality.Viewer
    ) -> list[dict[str, Any]]:
        """The questions the binding's template names (a type table, never a record)."""
        assert binding.template is not None
        return questions_of(binding.template.source_id)

    def problems(self, fields: list[dict[str, Any]], answers: list[dict[str, Any]]) -> list[str]:
        """The generic answer rules of format 2 (every precaution answered yes, no or na)."""
        return rules.validate_answers(fields, answers, fmt=FORMAT)

    def arguments(self, binding: FormBinding, answers: list[dict[str, Any]]) -> dict[str, Any]:
        """The arguments of ``IssuePermit``: the ids answered ``yes`` are the ticks."""
        args: dict[str, Any] = dict(binding.fixed_args)
        args[ANSWERS_ARG] = [str(a["q"]) for a in answers if a.get("value") == TICKED]
        if binding.expected_version is not None:
            args["expected_version"] = binding.expected_version
        return args


def source() -> FormSource:
    """The entry point ``throughline.form_sources`` names for ``permits.Permit``."""
    return PermitFormSource()
