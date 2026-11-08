"""``validate_intent``: limits, references, states, command names, normalisation (ADR-0025 d4)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.sqlite.uow import create_schema, open_uow
from tl_core.confidentiality import LOWEST, Viewer
from tl_core.intent import (
    CANONICAL_MAX_BYTES,
    Intent,
    IntentInvalid,
    IntentRef,
    IntentReferenceUnknown,
    IntentToward,
    check_intent,
    intent_json,
    validate_intent,
)
from tl_core.numbering.config import NumberingRegistry, use_numbering
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_core.services.records import handle_create_record
from tl_core.uow import UnitOfWork
from tl_core.workflow.definition import WorkflowDefinition
from tl_core.workflow.loader import WorkflowRegistry
from tl_core.workflow.provider import use_workflows

SCOPE = "project:P123"


@pytest.fixture
def uow(tmp_path: Path) -> Iterator[UnitOfWork]:
    db = tmp_path / "tl.db"
    create_schema(db)
    with use_numbering(NumberingRegistry([])), open_uow(db) as handle:
        yield handle


def make(uow: UnitOfWork, key: str, scope: str = SCOPE) -> str:
    return handle_create_record(
        uow,
        CreateRecord(
            actor="user:u", source="test", scope=scope, record_type="core.Record",
            title="T " + key, key=key,
        ),
    ).stream_id  # fmt: skip


def cmd(intent: Intent | dict[str, Any] | None, scope: str = SCOPE) -> UpdateRecord:
    value = Intent.model_validate(intent) if isinstance(intent, dict) else intent
    return UpdateRecord(
        actor="user:u", source="test", scope=scope, stream_id="x", expected_version=1,
        changes={"title": "t"}, intent=value,
    )  # fmt: skip


def check(uow: UnitOfWork, intent: Intent | dict[str, Any] | None) -> Intent | None:
    return validate_intent(uow.conn(), cmd(intent), viewer=LOWEST)


def bad(uow: UnitOfWork, intent: Intent | dict[str, Any]) -> str:
    with pytest.raises(IntentInvalid) as raised:
        check(uow, intent)
    return str(raised.value)


# --- limits: at the bound passes, one over is refused -------------------------------------------


def test_why_at_500_passes_and_501_is_refused(uow: UnitOfWork) -> None:
    assert check(uow, {"why": "a" * 500}) is not None
    assert "500" in bad(uow, {"why": "a" * 501})


def test_text_and_condition_at_200_pass_and_201_is_refused(uow: UnitOfWork) -> None:
    rid = make(uow, "R-1")
    assert check(uow, {"next": [{"text": "t" * 200}]}) is not None
    assert "200" in bad(uow, {"next": [{"text": "t" * 201}]})
    toward = {"target": rid, "condition": "c" * 200}
    assert check(uow, {"toward": toward}) is not None
    assert "200" in bad(uow, {"toward": {**toward, "condition": "c" * 201}})


def test_next_holds_five_and_six_is_refused(uow: UnitOfWork) -> None:
    five = [{"text": f"step {i}"} for i in range(5)]
    got = check(uow, {"next": five})
    assert got is not None and len(got.next) == 5
    assert "5" in bad(uow, {"next": [*five, {"text": "six"}]})


def test_goal_ref_pattern(uow: UnitOfWork) -> None:
    assert check(uow, {"goal_ref": "a-z_09" + "x" * 58}) is not None  # 64 characters
    for value in ("x" * 65, "UPPER", "has space", "", "dot.ted"):
        bad(uow, {"goal_ref": value})


def test_canonical_size_cap_is_4000_bytes(uow: UnitOfWork) -> None:
    # five 200-character texts and a 500-character why are 1500 characters; multibyte text is
    # what can reach 4000 bytes (each character 3 bytes)
    big = {"why": "é" * 500, "next": [{"text": "é" * 200} for _ in range(5)]}
    stored = intent_json(Intent.model_validate(big))
    assert stored is not None and len(stored.encode()) < CANONICAL_MAX_BYTES + 1000
    wide = {"why": "漢" * 500, "next": [{"text": "漢" * 200} for _ in range(5)]}
    with pytest.raises(IntentInvalid, match="4000"):
        check(uow, wide)  # 1500 characters of 3 bytes: over the cap
    narrow = {"why": "漢" * 500, "next": [{"text": "漢" * 200} for _ in range(2)]}
    got = check(uow, narrow)  # 900 characters: 2700 bytes plus the frame, under the cap
    assert got is not None


# --- characters -----------------------------------------------------------------------------


@pytest.mark.parametrize("char", ["\x01", "\x07", "\x1b", "\x7f", "\x85"])
def test_control_characters_are_refused_everywhere(uow: UnitOfWork, char: str) -> None:
    rid = make(uow, "R-1")
    bad(uow, {"why": f"a{char}b"})
    bad(uow, {"next": [{"text": f"a{char}b"}]})
    bad(uow, {"toward": {"target": rid, "condition": f"a{char}b"}})


@pytest.mark.parametrize("char", ["\u202e", "\u200b"])  # RIGHT-TO-LEFT OVERRIDE, ZERO WIDTH SPACE
def test_format_characters_are_refused_like_control_characters(uow: UnitOfWork, char: str) -> None:
    rid = make(uow, "R-1")
    assert "control character" in bad(uow, {"why": f"a{char}b"})
    assert "control character" in bad(uow, {"next": [{"text": f"a{char}b"}]})
    assert "control character" in bad(uow, {"toward": {"target": rid, "condition": f"a{char}b"}})


def test_a_key_in_scope_and_company_resolves_to_the_scope_row(uow: UnitOfWork) -> None:
    company = make(uow, "K-1", scope="company")  # inserted first: an unordered read may return it
    scoped = make(uow, "K-1", scope=SCOPE)
    assert company != scoped
    got = check(uow, {"toward": {"target": "K-1", "condition": "x"}})
    assert got is not None and got.toward is not None and got.toward.target == scoped


def test_newline_and_tab_are_allowed_in_why(uow: UnitOfWork) -> None:
    assert check(uow, {"why": "line one\n\tline two"}) is not None


def test_a_nul_never_reaches_the_validator() -> None:
    with pytest.raises(ValueError, match="NUL"):
        cmd({"why": "a\x00b"})


# --- normalisation --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "empty", [{}, {"why": None}, {"next": []}, {"next": [{}]}, {"toward": None}]
)
def test_empty_intents_become_none(uow: UnitOfWork, empty: dict[str, Any]) -> None:
    assert check(uow, empty) is None
    assert check_intent(cmd(empty), uow.conn(), LOWEST).intent is None


def test_no_intent_returns_the_same_command(uow: UnitOfWork) -> None:
    command = cmd(None)
    assert check_intent(command, uow.conn(), LOWEST) is command


# --- next ------------------------------------------------------------------------------------


def test_next_command_must_be_registered_and_is_not_permission_checked(uow: UnitOfWork) -> None:
    rid = make(uow, "R-1")
    ok = check(uow, {"next": [{"command": "TransitionWorkflow", "target": rid}]})
    assert ok is not None and ok.next[0].command == "TransitionWorkflow"
    assert check(uow, {"next": [{"command": "ChangeSetting"}]}) is not None  # admin-ish, allowed
    assert "does not exist" in bad(uow, {"next": [{"command": "NoSuchCommand"}]})


def test_a_module_command_name_is_registered(uow: UnitOfWork) -> None:
    assert check(uow, {"next": [{"command": "DefineWbsNode"}]}) is not None


def test_next_item_shapes(uow: UnitOfWork) -> None:
    rid = make(uow, "R-1")
    bad(uow, {"next": [{"text": "x", "command": "CreateRecord"}]})
    bad(uow, {"next": [{"text": "x", "target": rid}]})
    bad(uow, {"next": [{"target": rid}]})  # a target needs a command
    got = check(uow, {"next": [{"command": "CreateRecord"}]})
    assert got is not None and got.next[0].target is None


# --- references: keys resolve to ids, stored as ids -------------------------------------------


def test_keys_resolve_to_ids_and_ids_pass_through(uow: UnitOfWork) -> None:
    one, two = make(uow, "R-1"), make(uow, "R-2")
    got = check(
        uow,
        {
            "next": [
                {"command": "UpdateRecord", "target": "R-1"},
                {"command": "UpdateRecord", "target": two},
            ],
            "toward": {"target": "R-2", "condition": "signed off"},
        },
    )
    assert got is not None
    assert [i.target for i in got.next] == [one, two]
    assert got.toward is not None and got.toward.target == two
    assert "R-1" not in (intent_json(got) or "")


def test_a_stored_id_survives_a_key_rename(uow: UnitOfWork) -> None:
    rid = make(uow, "R-1")
    got = check(uow, {"toward": {"target": "R-1", "condition": "done"}})
    assert got is not None
    uow.conn().execute(
        text("UPDATE cur_core_record SET key = 'R-1-RENAMED' WHERE id = :i"), {"i": rid}
    )
    again = check(uow, got)  # the stored id still resolves
    assert again is not None and again.toward is not None and again.toward.target == rid
    with pytest.raises(IntentReferenceUnknown):
        check(uow, {"toward": {"target": "R-1", "condition": "done"}})  # the old key is gone


def test_unknown_foreign_scope_and_voided_references_all_answer_the_same(uow: UnitOfWork) -> None:
    make(uow, "OTHER-1", scope="project:OTHER")
    voided = make(uow, "R-V")
    uow.conn().execute(text("UPDATE cur_core_record SET voided = 1 WHERE id = :i"), {"i": voided})
    messages = set()
    for target in ("NOPE", "OTHER-1", "R-V", "01J000000000000000000000"):
        with pytest.raises(IntentReferenceUnknown) as raised:
            check(uow, {"toward": {"target": target, "condition": "x"}})
        messages.add((raised.value.code, str(raised.value)))
    assert messages == {("intent_reference_unknown", "intent reference not found")}


def test_a_company_record_resolves_from_a_project_command(uow: UnitOfWork) -> None:
    rid = make(uow, "CO-1", scope="company")
    got = check(uow, {"toward": {"target": "CO-1", "condition": "x"}})
    assert got is not None and got.toward is not None and got.toward.target == rid


def test_a_viewer_who_cannot_read_a_restricted_record_gets_the_unknown_answer(
    uow: UnitOfWork,
) -> None:
    rid = make(uow, "R-1")
    from tl_core import confidentiality

    hidden = {rid}
    original = confidentiality.is_hidden
    confidentiality.is_hidden = lambda conn, record_id, viewer=None: record_id in hidden  # type: ignore[assignment]
    try:
        with pytest.raises(IntentReferenceUnknown) as hidden_answer:
            validate_intent(
                uow.conn(), cmd({"toward": {"target": rid, "condition": "x"}}), viewer=Viewer()
            )
        with pytest.raises(IntentReferenceUnknown) as missing_answer:
            validate_intent(
                uow.conn(),
                cmd({"toward": {"target": "01J000000000000000000000", "condition": "x"}}),
                viewer=Viewer(),
            )
    finally:
        confidentiality.is_hidden = original  # type: ignore[assignment]
    assert str(hidden_answer.value) == str(missing_answer.value)
    assert hidden_answer.value.code == missing_answer.value.code


# --- toward: a workflow state, else a condition --------------------------------------------------

FLOW = WorkflowDefinition.model_validate(
    {
        "id": "t.flow", "version": 1, "record_type": "core.Record", "scope": SCOPE,
        "initial_state": "A", "states": [{"name": "A"}, {"name": "B"}],
        "transitions": [{"name": "go", "from": ["A"], "to": "B"}],
    }
)  # fmt: skip


def test_toward_state_must_be_a_state_of_the_targets_workflow(uow: UnitOfWork) -> None:
    make(uow, "R-1")
    with use_workflows(WorkflowRegistry([FLOW])):
        assert check(uow, {"toward": {"target": "R-1", "state": "B"}}) is not None
        assert "not a state" in bad(uow, {"toward": {"target": "R-1", "state": "Z"}})
        assert check(uow, {"toward": {"target": "R-1", "condition": "free text"}}) is not None


def test_toward_state_without_a_workflow_is_refused_and_a_condition_is_not(
    uow: UnitOfWork,
) -> None:
    make(uow, "R-1")
    with use_workflows(WorkflowRegistry([])):
        assert "not a state" in bad(uow, {"toward": {"target": "R-1", "state": "B"}})
        assert check(uow, {"toward": {"target": "R-1", "condition": "x"}}) is not None


def test_toward_needs_exactly_one_of_state_and_condition(uow: UnitOfWork) -> None:
    make(uow, "R-1")
    with use_workflows(WorkflowRegistry([FLOW])):
        bad(uow, {"toward": {"target": "R-1"}})
        bad(uow, {"toward": {"target": "R-1", "state": "B", "condition": "x"}})


def test_models_are_the_s1_models() -> None:
    assert IntentRef(text="x").text == "x" and IntentToward(target="t").state is None
