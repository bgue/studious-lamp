"""In-memory forms reads for `FakeClient` (V3-F1b): templates, submissions and the write door.

It holds the templates (``load_form_templates``) and submissions (``load_form_submissions``) a test
gave it. Reads answer as the routes do: a missing key raises `RecordNotFoundError` with the route's
text. `form_command` takes a ``SubmitForm`` only: it checks the answers with the same rules the
service uses, refuses with their problems, and else adds a Submitted row with the next number and
records the command in `form_commands`. `seed_forms` makes the rows the forms screen tests share.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from tl_core.auth.errors import ForbiddenError
from tl_core.forms import rules
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError, ServiceError
from tl_mod_forms import views as forms_views
from tl_mod_forms.commands import SubmitForm
from tl_mod_forms.routes import MSG_SUBMISSION, MSG_TEMPLATE

PROJECT = "P123"


def fld(fid: str, kind: str = "text", **more: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": fid,
        "text": f"Question {fid}",
        "kind": kind,
        "required": True,
        "unit": None,
        "min": None,
        "max": None,
        "choices": None,
        "fails_when": None,
        "section": None,
        "help": None,
        "visible_when": None,
    }
    base.update(more)
    return base


class FakeFormsSupport:
    """Mixin for `FakeClient`: call `_init_forms()` from its `__init__`."""

    def _init_forms(self) -> None:
        self._form_templates: list[tuple[forms_views.TemplateRow, list[dict[str, Any]]]] = []
        self._form_submissions: dict[str, list[forms_views.SubmissionDetail]] = {}
        self.form_commands: list[Command] = []

    def load_form_templates(
        self, templates: Sequence[tuple[forms_views.TemplateRow, list[dict[str, Any]]]]
    ) -> None:
        self._form_templates = list(templates)

    def load_form_submissions(
        self, project: str, details: Sequence[forms_views.SubmissionDetail]
    ) -> None:
        self._form_submissions[project] = list(details)

    def list_form_templates(
        self,
        *,
        state: str | None = None,
        intake: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> forms_views.Page[forms_views.TemplateRow]:
        rows = [r for r, _ in self._form_templates if state is None or r.state == state]
        rows.sort(key=lambda r: (r.key or "", r.version or 0))
        cut = rows[offset : offset + max(1, min(int(limit), forms_views.MAX_LIMIT))]
        return forms_views.Page(rows=cut, total=len(rows))

    def get_form_template(self, key: str, version: int, *, projection: str | None = None) -> Any:
        for row, fields in self._form_templates:
            if row.key == key and row.version == version:
                return {"row": row.__dict__ | {}, "fields": fields, "accepts_as": []}
        raise RecordNotFoundError(MSG_TEMPLATE)

    def list_form_submissions(
        self,
        project: str,
        *,
        state: str | None = None,
        template: str | None = None,
        subject: str | None = None,
        author: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> forms_views.Page[forms_views.SubmissionRow]:
        rows = [
            d.row
            for d in self._form_submissions.get(project, [])
            if (state is None or d.row.state == state)
            and (template is None or d.row.template_id == template)
            and (author is None or d.row.author == author)
        ]
        rows.sort(key=lambda r: r.key or r.id)
        cut = rows[offset : offset + max(1, min(int(limit), forms_views.MAX_LIMIT))]
        return forms_views.Page(rows=cut, total=len(rows))

    def get_form_submission(self, project: str, key: str) -> forms_views.SubmissionDetail:
        for d in self._form_submissions.get(project, []):
            if key in (d.row.key, d.row.id):
                return d
        raise RecordNotFoundError(MSG_SUBMISSION)

    def get_form_for(self, project: str, key: str) -> Any:
        raise RecordNotFoundError("no form for this record")

    def list_intake_items(self, project: str, *, state: str | None = None, limit: int = 100) -> Any:
        raise NotImplementedError("the intake queue is built in V3-F4")

    def get_intake_item(self, project: str, item_id: str) -> Any:
        raise NotImplementedError("the intake queue is built in V3-F4")

    def form_command(self, name: str, cmd: Command) -> CommandResult:
        if name != "SubmitForm" or not isinstance(cmd, SubmitForm):
            raise ForbiddenError(f"{name} is not a forms command in this fake")
        project = cmd.scope.removeprefix("project:")
        found = next((r for r, _ in self._form_templates if r.id == cmd.template_id), None)
        if found is None:
            raise RecordNotFoundError(MSG_TEMPLATE)
        fields = next(f for r, f in self._form_templates if r.id == cmd.template_id)
        problems = rules.validate_answers(fields, list(cmd.answers), fmt=found.format_version or 2)
        if problems:
            raise ServiceError("; ".join(problems))
        self.form_commands.append(cmd)
        held = self._form_submissions.setdefault(project, [])
        number = 1 + max(
            (int((d.row.key or "0").rsplit("-", 1)[-1]) for d in held if d.row.key), default=0
        )
        key = f"{project}-FRM-{number:04d}"
        row = forms_views.SubmissionRow(
            id=f"SUB-{len(held) + 1}",
            key=key,
            state="Submitted",
            template_id=found.id,
            template_version=found.version,
            subject_id=None,
            answer_class=None,
            author=cmd.actor,
            submitted_on="2026-11-17",
            reviewed_by=None,
            reviewed_on=None,
            draft_saves=None,
            version=1,
        )
        held.append(
            forms_views.SubmissionDetail(
                row=row, answers=list(cmd.answers), review_note=None, void_reason=None
            )
        )
        return CommandResult(stream_id=row.id, key=key, version=1, events=[])


def template(n: int, title: str, fields: list[dict[str, Any]], *, state: str = "Published") -> Any:
    row = forms_views.TemplateRow(
        id=f"TPL-ID-{n}",
        key=f"TPL-{n:04d}",
        title=title,
        version=1,
        state=state,
        format_version=2,
        field_count=len(fields),
        content_hash=None,
        bound_record_type=None,
        answer_class=None,
        intake=None,
        purpose=None,
        published_on="2026-11-01" if state == "Published" else None,
        retired_on=None,
    )
    return row, fields


def submission(
    n: int, tpl: forms_views.TemplateRow, state: str, author: str, answers: list[dict[str, Any]]
) -> forms_views.SubmissionDetail:
    draft = state == "Draft"
    row = forms_views.SubmissionRow(
        id=f"SUB-{n}",
        key=None if draft else f"{PROJECT}-FRM-{n:04d}",
        state=state,
        template_id=tpl.id,
        template_version=tpl.version,
        subject_id=None,
        answer_class=None,
        author=author,
        submitted_on=None if draft else "2026-11-10",
        reviewed_by="user:ada" if state == "Accepted" else None,
        reviewed_on="2026-11-11" if state == "Accepted" else None,
        draft_saves=1 if draft else None,
        version=1,
    )
    return forms_views.SubmissionDetail(
        row=row,
        answers=answers,
        review_note="Checked and filed." if state == "Accepted" else None,
        void_reason=None,
    )


def seed_forms(client: Any) -> None:
    """Two published templates and a draft one, three submissions (one of them a draft)."""
    talk, talk_fields = template(
        1,
        "Toolbox talk",
        [
            fld("topic", section="Talk", help="One line."),
            fld("count", "number", min=1, max=50, unit="people"),
            fld("ppe", "yes_no_na"),
            fld("hazards", "multi", choices=["Falls", "Lifting", "Electrical"], required=False),
            fld("detail", required=False, visible_when={"q": "ppe", "is": "no"}),
        ],
    )
    check, check_fields = template(2, "Pre-use check", [fld("tool"), fld("ok", "yes_no_na")])
    old, old_fields = template(3, "Old form", [fld("x")], state="Retired")
    client.load_form_templates([(talk, talk_fields), (check, check_fields), (old, old_fields)])
    client.load_form_submissions(
        PROJECT,
        [
            submission(1, talk, "Submitted", "user:uma", [{"q": "topic", "value": "Ladders"}]),
            submission(
                2,
                check,
                "Accepted",
                "user:rob",
                [{"q": "tool", "value": "Drill"}, {"q": "ok", "value": "yes", "note": "serviced"}],
            ),
            submission(3, talk, "Draft", "user:kim", [{"q": "topic", "value": "Half done"}]),
        ],
    )
