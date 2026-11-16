"""The expected failures of the forms module. Each takes a fixed message: never an answer, never a
cell of the input and never an id the viewer could not read.

They subclass ``ServiceError``; ``tl_api.errors`` maps each to a status and a stable code (the
registry line is supervisor glue). A refusal of who may act is core's ``ForbiddenError``. A refusal
of an id the viewer may not read, a draft of another author or an absent id is core's
``RecordNotFoundError`` with ``MSG_UNKNOWN``.
"""

from __future__ import annotations

from tl_core.services.errors import ServiceError

MSG_UNKNOWN = "no record with that id"
MSG_PROJECT = "a form is filled in a project"
MSG_STALE = "the record changed since it was read"
MSG_DRAFT_SAVES = "the draft was saved as often as it may be; submit it or discard it"
MSG_SELF_REVIEW = "the person who filled a form may not review it"
MSG_NOT_FILLABLE = "that template cannot be filled in this way"
MSG_NOT_PUBLISHED = "that template is not published"
MSG_TEMPLATE_PROBLEMS = "the template is not complete"
MSG_ANSWER_PROBLEMS = "the answers have problems"
MSG_NOTHING = "nothing to change"
MSG_ONE_DRAFT = "that template already has a version in draft"
MSG_INTAKE_FIELDS = "purpose and accepts_as belong to a public intake template only"
MSG_CODE_TAKEN = "that code is already in use"
MSG_NOT_INTAKE = "that template is not open to public intake"
MSG_EXPIRY = "the expiry is in the past or beyond the days a code may last"
MSG_NOT_ACCEPTED_AS = "that template does not accept an item as that command"
MSG_FIELD_LIST = "the field list is not a list of objects"


#: At most this many problems are listed in a text; the rest are counted.
MAX_LISTED = 12


def _joined(head: str, problems: tuple[str, ...]) -> str:
    shown = "; ".join(problems[:MAX_LISTED])
    more = len(problems) - MAX_LISTED
    tail = f"; and {more} more" if more > 0 else ""
    return f"{head}: {shown}{tail}" if problems else head


class FormsError(ServiceError):
    """Base of the module's expected failures."""


class FormsScopeError(FormsError):
    """A submission belongs to a project scope; a template to the company."""


class FormTemplateError(FormsError):
    """A rule of a template: its questions, its intake flags, one draft per lineage."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__(_joined(MSG_TEMPLATE_PROBLEMS, problems))
        self.problems = problems


class FormRuleError(FormsError):
    """A rule of the fields of a command: nothing to change, the save bound, a template not
    fillable."""


class FormStateError(FormsError):
    """The record is in a state that does not take the command."""


class FormAnswersError(FormsError):
    """The answers do not fit the template. ``problems`` are the rules' texts: they name field ids
    and never repeat an answer value."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__(_joined(MSG_ANSWER_PROBLEMS, problems))
        self.problems = problems


class StaleVersionError(FormsError):
    """The record changed since the caller read it (``expected_version`` is not the version)."""
