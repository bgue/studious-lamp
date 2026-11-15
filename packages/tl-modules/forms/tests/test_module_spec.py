"""The forms module spec (P2-FORMS S2)."""

from __future__ import annotations

from tl_core.modules import ModuleSpec, confidential_sources, load_modules
from tl_mod_forms import MODULE
from tl_mod_forms.module import projectors, spec
from tl_mod_forms.names import (
    EVENTS,
    INTAKE_ACTOR,
    INTAKE_CODE,
    INTAKE_ITEM,
    RECORD_TYPES,
    SETTINGS,
    SUBMISSION,
    TEMPLATE,
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


def test_no_commands_no_proposable_no_generic_commands_no_hooks() -> None:
    built = spec()
    assert dict(built.command_words) == {}
    assert tuple(built.proposable) == ()
    assert not built.generic_commands
    assert not built.company_roles


def test_no_confidential_declaration_yet() -> None:
    """CR1 adds it with the subject rows, before any read path ships."""
    built = spec()
    assert getattr(built, "confidential", None) in (None, (), [])
    assert not [c for c in confidential_sources() if c.table.startswith(("cur_forms", "forms_"))]


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
