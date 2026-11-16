"""What the forms module gives the platform (``tl_core.modules``; ADR-0010).

The entry point ``throughline.modules`` / ``forms`` names ``spec``. This slice holds the record
types, their projectors and the fifteen commands (P2-FORMS S3 and S7c: eleven for templates,
submissions and review, four for intake).
``forms.Submission`` is ``draft_only``: a form is filled and saved offline (``SaveFormDraft``,
``SubmitForm``); template, review and void commands are central. The module declares no
hook field. Its one ``confidential`` source classes a submission by its ``answer_class``
(``confidential.py``); the subject rows and the author-only draft rule are in
``tl_core.confidentiality``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tl_core.modules import ModuleSpec, ProposableCommand
from tl_core.projection.types import Projector
from tl_core.services.commands import Command

from tl_mod_forms import MODULE
from tl_mod_forms.commands import (
    AcceptFormSubmission,
    AcceptIntakeItem,
    DiscardFormDraft,
    DraftFormTemplate,
    EditFormTemplate,
    IssueIntakeCode,
    PublishFormTemplate,
    RejectIntakeItem,
    RetireFormTemplate,
    ReturnFormSubmission,
    ReviseFormTemplate,
    RevokeIntakeCode,
    SaveFormDraft,
    SubmitForm,
    VoidFormSubmission,
)
from tl_mod_forms.confidential import CONFIDENTIAL
from tl_mod_forms.guards import submitted_or_later
from tl_mod_forms.handlers.intake import (
    handle_accept_intake_item,
    handle_issue_intake_code,
    handle_reject_intake_item,
    handle_revoke_intake_code,
)
from tl_mod_forms.handlers.review import (
    handle_accept_form_submission,
    handle_return_form_submission,
    handle_void_form_submission,
)
from tl_mod_forms.handlers.submission import (
    handle_discard_form_draft,
    handle_save_form_draft,
    handle_submit_form,
)
from tl_mod_forms.handlers.template import (
    handle_draft_form_template,
    handle_edit_form_template,
    handle_publish_form_template,
    handle_retire_form_template,
    handle_revise_form_template,
)
from tl_mod_forms.names import (
    INTAKE_ISSUE,
    INTAKE_REVIEW,
    PROPOSE_SUBMISSION,
    RECORD_TYPES,
    REVIEW,
    SUBMISSION,
    SUBMIT,
    TEMPLATE_EDIT,
    TEMPLATE_PUBLISH,
    VOID_WORD,
)
from tl_mod_forms.projectors import (
    IntakeCodeProjector,
    IntakeItemProjector,
    SubmissionProjector,
    TemplateProjector,
)


@dataclass(frozen=True)
class FormsCommand:
    """A command, its handler and its fine access word (the API reads ``model`` and ``access``)."""

    model: type[Command]
    handler: Any  # Callable[[UnitOfWork, Any], CommandResult]
    access: str


#: The word the API table (``tl_api.commands``) reads for the module's row type.
ApiCommand = FormsCommand

FORMS_COMMANDS: tuple[FormsCommand, ...] = (
    FormsCommand(DraftFormTemplate, handle_draft_form_template, TEMPLATE_EDIT),
    FormsCommand(EditFormTemplate, handle_edit_form_template, TEMPLATE_EDIT),
    FormsCommand(PublishFormTemplate, handle_publish_form_template, TEMPLATE_PUBLISH),
    FormsCommand(ReviseFormTemplate, handle_revise_form_template, TEMPLATE_EDIT),
    FormsCommand(RetireFormTemplate, handle_retire_form_template, TEMPLATE_PUBLISH),
    FormsCommand(SaveFormDraft, handle_save_form_draft, SUBMIT),
    FormsCommand(DiscardFormDraft, handle_discard_form_draft, SUBMIT),
    FormsCommand(SubmitForm, handle_submit_form, SUBMIT),
    FormsCommand(AcceptFormSubmission, handle_accept_form_submission, REVIEW),
    FormsCommand(ReturnFormSubmission, handle_return_form_submission, REVIEW),
    FormsCommand(VoidFormSubmission, handle_void_form_submission, VOID_WORD),
    FormsCommand(IssueIntakeCode, handle_issue_intake_code, INTAKE_ISSUE),
    FormsCommand(RevokeIntakeCode, handle_revoke_intake_code, INTAKE_ISSUE),
    FormsCommand(AcceptIntakeItem, handle_accept_intake_item, INTAKE_REVIEW),
    FormsCommand(RejectIntakeItem, handle_reject_intake_item, INTAKE_REVIEW),
)

#: The life of a link that starts at the record (accept, decline, re-pin, verify, flag, retract).
LINK_LIFE = frozenset(
    {"AcceptLink", "DeclineLink", "RepinLink", "VerifyLink", "FlagLink", "RetractLink"}
)
#: A submission takes property values, links, files and the life of its links once it is submitted
#: (``guards.submitted_or_later``). Its fields and state change only through the module's commands:
#: not ``UpdateRecord``, ``VoidRecord`` or ``TransitionWorkflow`` (ADR-0010 addendum 1). A template
#: and the intake records take no generic command.
FORMS_GENERIC_COMMANDS = frozenset({"SetPsetValues", "AddLink", "AttachFile"}) | LINK_LIFE

#: What an agent may propose: a submission (``SubmitForm``). Accepting runs it as the accepting
#: person, who becomes its author and needs ``forms.submit`` (a ``user`` word). The other
#: fourteen commands are in ``tests/tools/proposable_exclusions.toml`` with the reason.
PROPOSABLE = (ProposableCommand(PROPOSE_SUBMISSION, SubmitForm, handle_submit_form, "user"),)


def projectors() -> list[Projector]:
    """Fresh projectors in the order they are registered."""
    return [
        TemplateProjector(),
        SubmissionProjector(),
        IntakeCodeProjector(),
        IntakeItemProjector(),
    ]


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=RECORD_TYPES,
        projectors=projectors,
        generic_commands={SUBMISSION: FORMS_GENERIC_COMMANDS},
        generic_guards={(SUBMISSION, c): submitted_or_later for c in FORMS_GENERIC_COMMANDS},
        proposable=PROPOSABLE,
        confidential=CONFIDENTIAL,
        # command name -> access word, from the module's own table (ADR-0021)
        command_words={c.model.__name__: c.access for c in FORMS_COMMANDS},
        # a form is filled and saved offline; the number is taken when it is submitted
        offline_drafts={SUBMISSION: frozenset({"SaveFormDraft", "SubmitForm"})},
    )
