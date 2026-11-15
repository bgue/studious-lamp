"""The forms module spec, and the webhook text check for answers (P2-FORMS S2)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from tl_adapters.db import DbTarget, open_uow
from tl_core.confidentiality import Viewer, use_viewer
from tl_core.modules import ModuleSpec, confidential_sources, load_modules
from tl_core.webhooks.dispatch import Dispatcher
from tl_core.webhooks.rows import OutboxRow
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
    SUBMISSION_DRAFT_SAVED,
    SUBMISSION_SUBMITTED,
    TEMPLATE,
    WORDS,
)
from tl_mod_forms.projectors import (
    IntakeCodeProjector,
    IntakeItemProjector,
    SubmissionProjector,
    TemplateProjector,
)

MARKER = "ANSWER-MARKER-7f3c9"
STREAM = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2"
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


# ---- the webhook text check (SR-X1 F3): answers never reach a webhook body ------------------


def _row(event_type: str, detail: dict[str, Any]) -> OutboxRow:
    return OutboxRow(
        seq=1,
        event_id="01EVENT00000000000000000",
        scope="project:P1",
        event_type=event_type,
        stream_id=STREAM,
        stream_type=SUBMISSION,
        stream_version=2,
        subject_id=STREAM,
        actor="user:x",
        recorded_at="2026-11-14T00:00:00+00:00",
        correlation_id="c1",
        data={"origin": {"id": STREAM}, "changes": {}, "links": [], "detail": detail},
    )


def _detail(event_type: str) -> dict[str, Any]:
    answers = [{"q": "q1", "value": MARKER, "note": MARKER}]
    common = {
        "record_id": STREAM,
        "template_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P3",
        "template_version": 1,
        "template_hash": "ab" * 32,
        "subject_id": None,
        "answers": answers,
        "answer_class": "restricted",
    }
    if event_type == SUBMISSION_DRAFT_SAVED:
        return {**common, "save_no": 1, "feed_policy": "none"}
    return {**common, "submitted_on": "2026-11-14", "feed_policy": "none"}


@pytest.mark.parametrize("mode", ["thin", "delta", "full"])
@pytest.mark.parametrize("event_type", [SUBMISSION_DRAFT_SAVED, SUBMISSION_SUBMITTED])
def test_a_webhook_body_never_holds_the_answers(db: DbTarget, event_type: str, mode: str) -> None:
    with open_uow(db) as uow, use_viewer(Viewer("user:owner", 1, "user:owner")):
        body = Dispatcher(lambda readonly=False: uow).render_body(  # type: ignore[arg-type,call-arg]
            uow, _row(event_type, _detail(event_type)), mode
        )
    assert MARKER not in body, (event_type, mode)
    assert json.loads(body)["type"]
