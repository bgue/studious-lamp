"""Names the forms module shares: record types, states, tables, events, access words, settings."""

from __future__ import annotations

from typing import Final

TEMPLATE: Final = "forms.Template"
SUBMISSION: Final = "forms.Submission"
INTAKE_CODE: Final = "forms.IntakeCode"
INTAKE_ITEM: Final = "forms.IntakeItem"
RECORD_TYPES: Final = frozenset({TEMPLATE, SUBMISSION, INTAKE_CODE, INTAKE_ITEM})

TEMPLATE_TABLE: Final = "cur_forms_template"
SUBMISSION_TABLE: Final = "cur_forms_submission"
INTAKE_CODE_TABLE: Final = "cur_forms_intake_code"
INTAKE_ITEM_TABLE: Final = "cur_forms_intake_item"
#: Operational: no event produces it and no projector writes it (a rebuild never clears it).
INTAKE_BODY_TABLE: Final = "forms_intake_body"
TEMPLATE_VIEW: Final = "v_forms_template"
SUBMISSION_VIEW: Final = "v_forms_submission"
INTAKE_CODE_VIEW: Final = "v_forms_intake_code"
INTAKE_ITEM_VIEW: Final = "v_forms_intake_item"

TEMPLATE_WORKFLOW: Final = "forms.template"
SUBMISSION_WORKFLOW: Final = "forms.submission"
INTAKE_CODE_WORKFLOW: Final = "forms.intake-code"
INTAKE_ITEM_WORKFLOW: Final = "forms.intake-item"

#: Workflow states.
DRAFT: Final = "Draft"
PUBLISHED: Final = "Published"
RETIRED: Final = "Retired"
SUBMITTED: Final = "Submitted"
RETURNED: Final = "Returned"
ACCEPTED: Final = "Accepted"
VOIDED: Final = "Voided"
DISCARDED: Final = "Discarded"
ACTIVE: Final = "Active"
REVOKED: Final = "Revoked"
PENDING: Final = "Pending"
REJECTED: Final = "Rejected"
TEMPLATE_STATES: Final = (DRAFT, PUBLISHED, RETIRED)
SUBMISSION_STATES: Final = (DRAFT, SUBMITTED, RETURNED, ACCEPTED, VOIDED, DISCARDED)
INTAKE_CODE_STATES: Final = (ACTIVE, REVOKED)
INTAKE_ITEM_STATES: Final = (PENDING, ACCEPTED, REJECTED)

TEMPLATE_CREATED: Final = "Template.Created"
TEMPLATE_EDITED: Final = "Template.Edited"
TEMPLATE_PUBLISHED: Final = "Template.Published"
TEMPLATE_RETIRED: Final = "Template.Retired"
TEMPLATE_EVENTS: Final = frozenset(
    {TEMPLATE_CREATED, TEMPLATE_EDITED, TEMPLATE_PUBLISHED, TEMPLATE_RETIRED}
)
SUBMISSION_DRAFT_SAVED: Final = "Submission.DraftSaved"
SUBMISSION_DRAFT_DISCARDED: Final = "Submission.DraftDiscarded"
SUBMISSION_SUBMITTED: Final = "Submission.Submitted"
SUBMISSION_ACCEPTED: Final = "Submission.Accepted"
SUBMISSION_RETURNED: Final = "Submission.Returned"
SUBMISSION_VOIDED: Final = "Submission.Voided"
SUBMISSION_EVENTS: Final = frozenset(
    {
        SUBMISSION_DRAFT_SAVED,
        SUBMISSION_DRAFT_DISCARDED,
        SUBMISSION_SUBMITTED,
        SUBMISSION_ACCEPTED,
        SUBMISSION_RETURNED,
        SUBMISSION_VOIDED,
    }
)
INTAKE_CODE_ISSUED: Final = "IntakeCode.Issued"
INTAKE_CODE_REVOKED: Final = "IntakeCode.Revoked"
INTAKE_CODE_EVENTS: Final = frozenset({INTAKE_CODE_ISSUED, INTAKE_CODE_REVOKED})
INTAKE_ITEM_RECEIVED: Final = "IntakeItem.Received"
INTAKE_ITEM_ACCEPTED: Final = "IntakeItem.Accepted"
INTAKE_ITEM_REJECTED: Final = "IntakeItem.Rejected"
INTAKE_ITEM_PURGED: Final = "IntakeItem.Purged"
INTAKE_ITEM_EVENTS: Final = frozenset(
    {INTAKE_ITEM_RECEIVED, INTAKE_ITEM_ACCEPTED, INTAKE_ITEM_REJECTED, INTAKE_ITEM_PURGED}
)
EVENTS: Final = TEMPLATE_EVENTS | SUBMISSION_EVENTS | INTAKE_CODE_EVENTS | INTAKE_ITEM_EVENTS

#: Access words (``schema/settings/access-words.yaml``).
VIEW: Final = "forms.view"
TEMPLATE_EDIT: Final = "forms.template.edit"
TEMPLATE_PUBLISH: Final = "forms.template.publish"
SUBMIT: Final = "forms.submit"
REVIEW: Final = "forms.review"
VOID_WORD: Final = "forms.void"
INTAKE_ISSUE: Final = "forms.intake.issue"
INTAKE_REVIEW: Final = "forms.intake.review"
WORDS: Final = (
    VIEW,
    TEMPLATE_EDIT,
    TEMPLATE_PUBLISH,
    SUBMIT,
    REVIEW,
    VOID_WORD,
    INTAKE_ISSUE,
    INTAKE_REVIEW,
)

#: Settings (``schema/settings/platform.yaml``).
DRAFT_SAVES_MAX: Final = "forms.draft_saves_max"
INTAKE_ENABLED: Final = "forms.intake.enabled"
INTAKE_RATE_PER_ADDRESS: Final = "forms.intake.rate_per_address_per_hour"
INTAKE_RATE_PER_CODE: Final = "forms.intake.rate_per_code_per_hour"
INTAKE_PENDING_MAX: Final = "forms.intake.pending_per_code_max"
INTAKE_RETENTION_DAYS: Final = "forms.intake.retention_days"
INTAKE_CODE_MAX_DAYS: Final = "forms.intake.code_max_days"
SETTINGS: Final = (
    DRAFT_SAVES_MAX,
    INTAKE_ENABLED,
    INTAKE_RATE_PER_ADDRESS,
    INTAKE_RATE_PER_CODE,
    INTAKE_PENDING_MAX,
    INTAKE_RETENTION_DAYS,
    INTAKE_CODE_MAX_DAYS,
)

#: The service actor of the public intake endpoint. It holds no access word.
INTAKE_ACTOR: Final = "svc:intake"
FEED_NONE: Final = "none"

#: Workflow transitions (``schema/fixtures/workflows/forms-*.yaml``).
T_PUBLISH: Final = "publish"
T_RETIRE: Final = "retire"
T_SUBMIT: Final = "submit"
T_ACCEPT: Final = "accept"
T_RETURN: Final = "return"
T_VOID: Final = "void"
T_DISCARD: Final = "discard"
T_REVOKE: Final = "revoke"
T_REJECT: Final = "reject"

PROPOSE_SUBMISSION: Final = "propose_form_submission"
