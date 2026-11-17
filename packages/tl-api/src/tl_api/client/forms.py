"""The forms module's reads and its write door over HTTP (V3-F1a).

The same models the embedded client returns (``tl_mod_forms.views``: dataclasses, decoded with a
``TypeAdapter``; ``FormBinding`` from ``tl_core.forms.types``). ``project`` is a query parameter
for submissions and ``/forms/for``, as the routes take it; templates belong to the company and take
none. A missing, hidden or other-person's-draft record is the service's ``RecordNotFoundError``,
rebuilt from the 404 body. ``form_command(name, cmd)`` runs a model of
``tl_mod_forms.module.FORMS_COMMANDS`` by name, posted to ``/commands/<name>``. The intake
reads are not built yet (``NotImplementedError``).
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter
from tl_core.auth.errors import ForbiddenError
from tl_core.forms.types import FormBinding
from tl_core.services.commands import Command, CommandResult
from tl_mod_forms import views
from tl_mod_forms.module import FORMS_COMMANDS

from tl_api.client.base import ApiClientBase, quote

_TEMPLATES: TypeAdapter[views.Page[views.TemplateRow]] = TypeAdapter(views.Page[views.TemplateRow])
_SUBMISSIONS: TypeAdapter[views.Page[views.SubmissionRow]] = TypeAdapter(
    views.Page[views.SubmissionRow]
)
_SUBMISSION: TypeAdapter[views.SubmissionDetail] = TypeAdapter(views.SubmissionDetail)
_BINDING: TypeAdapter[FormBinding] = TypeAdapter(FormBinding)


class FormsApi(ApiClientBase):
    def list_form_templates(
        self,
        *,
        state: str | None = None,
        intake: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> views.Page[views.TemplateRow]:
        """The templates the caller may read (``GET /forms/templates``); ``total`` counts them."""
        data: Any = self._get_json(
            "/forms/templates",
            {"state": state, "intake": intake, "limit": limit, "offset": offset},
        )
        return _TEMPLATES.validate_python(data)

    def get_form_template(self, key: str, version: int, *, projection: str | None = None) -> Any:
        """One template version (``GET /forms/templates/{key}/versions/{n}``): the detail
        ``{row, fields, accepts_as}``, or with ``projection`` ``jsonschema`` or ``surveyjs`` that
        projection of its fields."""
        return self._get_json(
            f"/forms/templates/{quote(key)}/versions/{int(version)}", {"as": projection}
        )

    def get_form_for(self, project: str, key: str) -> FormBinding:
        """The form a record offers (``GET /forms/for/{key}?project=``); 404 when there is none."""
        data: Any = self._get_json(f"/forms/for/{quote(key)}", {"project": project})
        return _BINDING.validate_python(data)

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
    ) -> views.Page[views.SubmissionRow]:
        """A project's submissions, latest first (``GET /forms/submissions?project=``)."""
        data: Any = self._get_json(
            "/forms/submissions",
            {
                "project": project,
                "state": state,
                "template": template,
                "subject": subject,
                "author": author,
                "limit": limit,
                "offset": offset,
            },
        )
        return _SUBMISSIONS.validate_python(data)

    def get_form_submission(self, project: str, key: str) -> views.SubmissionDetail:
        """One submission with its answers (``GET /forms/submissions/{key}?project=``)."""
        data: Any = self._get_json(f"/forms/submissions/{quote(key)}", {"project": project})
        return _SUBMISSION.validate_python(data)

    def form_command(self, name: str, cmd: Command) -> CommandResult:
        """Run a forms command by name (a model of ``FORMS_COMMANDS``), as the person."""
        row = next((c for c in FORMS_COMMANDS if c.model.__name__ == name), None)
        if row is None or type(cmd) is not row.model:
            raise ForbiddenError(f"{name} is not a forms command")
        return self._command(name, cmd)

    # --- intake: built by a later unit (V3-F4) -------------------------------------------------

    def list_intake_items(self, project: str, *, state: str | None = None, limit: int = 100) -> Any:
        raise NotImplementedError("the intake reads are built in V3-F4")

    def get_intake_item(self, project: str, item_id: str) -> Any:
        raise NotImplementedError("the intake reads are built in V3-F4")
