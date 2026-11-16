"""The forms module spec (P2-FORMS S2)."""

from __future__ import annotations

from tl_core.modules import ModuleSpec, confidential_sources, load_modules
from tl_mod_forms import MODULE
from tl_mod_forms.commands import SubmitForm
from tl_mod_forms.module import FORMS_COMMANDS, FORMS_GENERIC_COMMANDS, projectors, spec
from tl_mod_forms.names import (
    EVENTS,
    INTAKE_ACTOR,
    INTAKE_CODE,
    INTAKE_ISSUE,
    INTAKE_ITEM,
    INTAKE_REVIEW,
    RECORD_TYPES,
    REVIEW,
    SETTINGS,
    SUBMISSION,
    SUBMIT,
    TEMPLATE,
    TEMPLATE_EDIT,
    TEMPLATE_PUBLISH,
    VOID_WORD,
    WORDS,
)
from tl_mod_forms.projectors import (
    IntakeCodeProjector,
    IntakeItemProjector,
    SubmissionProjector,
    TemplateProjector,
)

ALL = [TemplateProjector, SubmissionProjector, IntakeCodeProjector, IntakeItemProjector]


def test_spec_loads_with_the_record_types_and_the_projectors() -> None:
    built = spec()
    assert isinstance(built, ModuleSpec)
    assert built.name == MODULE == "forms"
    assert built.record_types == RECORD_TYPES
    assert RECORD_TYPES == {TEMPLATE, SUBMISSION, INTAKE_CODE, INTAKE_ITEM}
    assert [type(p) for p in built.projectors()] == ALL
    assert [type(p) for p in projectors()] == ALL
    assert INTAKE_ACTOR == "svc:intake"


def test_fifteen_commands_with_their_words_the_one_proposable_row_and_the_offline_drafts() -> None:
    built = spec()
    assert dict(built.command_words) == {
        "DraftFormTemplate": TEMPLATE_EDIT,
        "EditFormTemplate": TEMPLATE_EDIT,
        "PublishFormTemplate": TEMPLATE_PUBLISH,
        "ReviseFormTemplate": TEMPLATE_EDIT,
        "RetireFormTemplate": TEMPLATE_PUBLISH,
        "SaveFormDraft": SUBMIT,
        "DiscardFormDraft": SUBMIT,
        "SubmitForm": SUBMIT,
        "AcceptFormSubmission": REVIEW,
        "ReturnFormSubmission": REVIEW,
        "VoidFormSubmission": VOID_WORD,
        "IssueIntakeCode": INTAKE_ISSUE,
        "RevokeIntakeCode": INTAKE_ISSUE,
        "AcceptIntakeItem": INTAKE_REVIEW,
        "RejectIntakeItem": INTAKE_REVIEW,
    }
    assert len(FORMS_COMMANDS) == 15
    assert {c.model.__name__ for c in FORMS_COMMANDS} == set(built.command_words)
    assert {c.access for c in FORMS_COMMANDS} <= set(WORDS)
    (row,) = built.proposable
    assert (row.tool, row.model, row.access) == ("propose_form_submission", SubmitForm, "user")
    assert dict(built.offline_drafts) == {SUBMISSION: frozenset({"SaveFormDraft", "SubmitForm"})}
    assert all(built.command_words[n] == SUBMIT for n in built.offline_drafts[SUBMISSION])
    assert not built.company_roles


def test_the_generic_commands_are_those_of_a_submission_only() -> None:
    built = spec()
    assert set(built.generic_commands) == {SUBMISSION}
    allowed = built.generic_commands[SUBMISSION]
    assert allowed == FORMS_GENERIC_COMMANDS
    assert {"SetPsetValues", "AddLink", "AttachFile"} <= allowed
    assert not allowed & {"UpdateRecord", "VoidRecord", "TransitionWorkflow", "CreateRecord"}
    assert {k for k in built.generic_guards} == {(SUBMISSION, c) for c in allowed}


def test_one_confidential_source_classes_a_submission_by_its_answer_class() -> None:
    built = spec()
    assert [(c.table, c.class_column, c.null_class) for c in built.confidential] == [
        ("cur_forms_submission", "answer_class", "internal")
    ]
    assert built.confidential[0].record_types == {SUBMISSION}
    assert [c for c in confidential_sources() if c.table.startswith("cur_forms")] == list(
        built.confidential
    )


def test_the_platform_discovers_the_module_through_its_entry_point() -> None:
    by_name = {m.name: m for m in load_modules()}
    assert by_name["forms"].record_types == RECORD_TYPES


def test_the_projectors_handle_the_sixteen_events_once_each() -> None:
    handled = [e for p in projectors() for e in p.handles]
    assert len(handled) == 16 == len(set(handled))
    assert set(handled) == EVENTS


def test_eight_words_and_seven_settings() -> None:
    assert len(WORDS) == 8 and all(w.startswith("forms.") for w in WORDS)
    assert len(SETTINGS) == 7 and all(s.startswith("forms.") for s in SETTINGS)
