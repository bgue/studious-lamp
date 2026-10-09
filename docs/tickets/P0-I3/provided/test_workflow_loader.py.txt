"""Workflow definition loader and registry (P0-I3-T08; brief 8)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_core.workflow.definition import (
    ConformanceGuard,
    ExpectedLinksGuard,
    RequiredLinksGuard,
    RequiredPsetsGuard,
    RolesGuard,
    WorkflowDefinition,
)
from tl_core.workflow.loader import (
    WorkflowError,
    WorkflowRegistry,
    default_workflows,
    load_workflow,
    load_workflows,
    parse_workflow,
    semantic_problems,
)

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "workflows"

GOOD = """
id: demo.flow
version: 2
record_type: core.Record
scope: project:P123
initial_state: Draft
states:
  - name: Draft
    label: Draft state
  - name: Review
  - name: Done
transitions:
  - name: submit
    label: Submit
    from: [Draft]
    to: Review
    guards:
      - kind: required_psets
        psets: [valve_data]
        values: [valve_data.size_in]
      - kind: conformance
      - kind: required_links
        links:
          - relation: requires
            target_type: core.Record
            min_count: 2
      - kind: roles
        any_of: [reviewer, admin]
  - name: finish
    from: [Review]
    to: Done
    guards:
      - kind: expected_links
"""


def definition(**overrides: object) -> WorkflowDefinition:
    data: dict[str, object] = {
        "id": "t.flow",
        "version": 1,
        "record_type": "core.Record",
        "initial_state": "A",
        "states": [{"name": "A"}, {"name": "B"}],
        "transitions": [{"name": "go", "from": ["A"], "to": "B"}],
    }
    data.update(overrides)
    return WorkflowDefinition.model_validate(data)


# --- parse_workflow -------------------------------------------------------------------------


def test_parses_a_complete_definition() -> None:
    flow = parse_workflow(GOOD, source="good.yaml")
    assert (flow.id, flow.version, flow.record_type, flow.scope) == (
        "demo.flow",
        2,
        "core.Record",
        "project:P123",
    )
    assert flow.initial_state == "Draft"
    assert flow.state_names() == ["Draft", "Review", "Done"]
    assert flow.states[0].label == "Draft state"
    submit = flow.transition("submit")
    assert submit is not None
    assert submit.from_states == ["Draft"]
    assert submit.to == "Review"
    assert submit.label == "Submit"
    kinds = [type(g) for g in submit.guards]
    assert kinds == [RequiredPsetsGuard, ConformanceGuard, RequiredLinksGuard, RolesGuard]
    psets_guard, conformance_guard, links_guard, roles_guard = submit.guards
    assert isinstance(psets_guard, RequiredPsetsGuard)
    assert (psets_guard.psets, psets_guard.values) == (["valve_data"], ["valve_data.size_in"])
    assert isinstance(conformance_guard, ConformanceGuard)
    assert conformance_guard.max_status == "warning"
    assert isinstance(links_guard, RequiredLinksGuard)
    assert links_guard.links[0].relation == "requires"
    assert links_guard.links[0].min_count == 2
    assert isinstance(roles_guard, RolesGuard)
    assert roles_guard.any_of == ["reviewer", "admin"]
    finish = flow.transition("finish")
    assert finish is not None
    assert isinstance(finish.guards[0], ExpectedLinksGuard)


def test_scope_defaults_to_company() -> None:
    text = GOOD.replace("scope: project:P123\n", "")
    assert parse_workflow(text).scope == "company"


def test_definition_helpers() -> None:
    flow = parse_workflow(GOOD)
    assert flow.transition("nope") is None
    assert [t.name for t in flow.transitions_from("Draft")] == ["submit"]
    assert flow.transitions_from("Done") == []


def test_invalid_yaml_names_the_source() -> None:
    with pytest.raises(WorkflowError, match=r"^bad\.yaml: invalid YAML"):
        parse_workflow("id: [unclosed", source="bad.yaml")


@pytest.mark.parametrize("text", ["- a\n- b\n", "just text", ""])
def test_a_document_that_is_not_a_mapping_is_refused(text: str) -> None:
    with pytest.raises(WorkflowError, match=r"^x\.yaml: a workflow file must be a YAML mapping"):
        parse_workflow(text, source="x.yaml")


def test_structural_errors_are_listed_one_per_line() -> None:
    text = GOOD.replace("version: 2", "version: 0").replace("record_type: core.Record\n", "")
    with pytest.raises(WorkflowError) as caught:
        parse_workflow(text, source="s.yaml")
    lines = str(caught.value).splitlines()
    assert all(line.startswith("s.yaml: ") for line in lines)
    assert any("version" in line for line in lines)
    assert any("record_type" in line for line in lines)


def test_unknown_keys_are_refused() -> None:
    with pytest.raises(WorkflowError, match="colour"):
        parse_workflow(GOOD + "colour: red\n", source="k.yaml")


def test_an_unknown_guard_kind_is_refused() -> None:
    text = GOOD.replace("kind: conformance", "kind: telepathy")
    with pytest.raises(WorkflowError, match="s.yaml"):
        parse_workflow(text, source="s.yaml")


def test_semantic_problems_are_reported_by_parse_workflow() -> None:
    text = GOOD.replace("to: Review", "to: Nowhere")
    with pytest.raises(WorkflowError) as caught:
        parse_workflow(text, source="m.yaml")
    assert "m.yaml: transition 'submit' ends in unknown state 'Nowhere'" in str(caught.value)


# --- semantic_problems ----------------------------------------------------------------------


def test_a_sound_definition_has_no_problems() -> None:
    assert semantic_problems(definition()) == []


def test_duplicate_state() -> None:
    flow = definition(states=[{"name": "A"}, {"name": "B"}, {"name": "A"}])
    assert "duplicate state 'A'" in semantic_problems(flow)


def test_initial_state_must_be_a_state() -> None:
    assert semantic_problems(definition(initial_state="Z")) == ["initial_state 'Z' is not a state"]


def test_duplicate_transition_name() -> None:
    flow = definition(
        transitions=[
            {"name": "go", "from": ["A"], "to": "B"},
            {"name": "go", "from": ["B"], "to": "A"},
        ]
    )
    assert semantic_problems(flow) == ["duplicate transition 'go'"]


def test_a_transition_needs_from_states() -> None:
    flow = definition(transitions=[{"name": "go", "from": [], "to": "B"}])
    problems = semantic_problems(flow)
    assert "transition 'go' has no from states" in problems


def test_unknown_from_and_to_states() -> None:
    flow = definition(transitions=[{"name": "go", "from": ["A", "Q"], "to": "R"}])
    problems = semantic_problems(flow)
    assert "transition 'go' starts in unknown state 'Q'" in problems
    assert "transition 'go' ends in unknown state 'R'" in problems


def test_unreachable_states_are_reported_in_declaration_order() -> None:
    flow = definition(
        states=[{"name": "A"}, {"name": "B"}, {"name": "C"}, {"name": "D"}],
        transitions=[{"name": "go", "from": ["A"], "to": "B"}],
    )
    assert semantic_problems(flow) == [
        "state 'C' is unreachable from the initial state",
        "state 'D' is unreachable from the initial state",
    ]


def test_a_state_reached_only_by_a_loop_is_reachable() -> None:
    flow = definition(
        states=[{"name": "A"}, {"name": "B"}, {"name": "C"}],
        transitions=[
            {"name": "go", "from": ["A"], "to": "B"},
            {"name": "on", "from": ["B"], "to": "C"},
            {"name": "back", "from": ["C"], "to": "A"},
        ],
    )
    assert semantic_problems(flow) == []


@pytest.mark.parametrize("scope", ["company", "project:P123", "project:a.b-c_d"])
def test_valid_scopes(scope: str) -> None:
    assert semantic_problems(definition(scope=scope)) == []


@pytest.mark.parametrize("scope", ["", "project", "project:", "project:a b", "tenant", "Company"])
def test_invalid_scopes(scope: str) -> None:
    assert f"invalid scope {scope!r}" in semantic_problems(definition(scope=scope))


def test_a_required_psets_guard_needs_something_to_require() -> None:
    flow = definition(
        transitions=[
            {"name": "go", "from": ["A"], "to": "B", "guards": [{"kind": "required_psets"}]}
        ]
    )
    assert semantic_problems(flow) == [
        "transition 'go': a required_psets guard needs psets or values"
    ]


# --- registry -------------------------------------------------------------------------------


def test_find_prefers_the_exact_scope_then_the_highest_version() -> None:
    company_v1 = definition(id="c", version=1)
    company_v2 = definition(id="c", version=2)
    project_v1 = definition(id="p", version=1, scope="project:P123")
    registry = WorkflowRegistry([company_v1, company_v2, project_v1])
    assert registry.find("core.Record", "project:P123") is project_v1
    assert registry.find("core.Record", "project:P999") is company_v2
    assert registry.find("core.Record", "company") is company_v2


def test_find_returns_none_without_a_match() -> None:
    registry = WorkflowRegistry([definition(scope="project:P123")])
    assert registry.find("core.Record", "project:P999") is None
    assert registry.find("other.Type", "project:P123") is None
    assert WorkflowRegistry().find("core.Record", "company") is None


def test_add_refuses_a_duplicate_id_version_and_scope() -> None:
    registry = WorkflowRegistry([definition()])
    with pytest.raises(WorkflowError, match="already registered"):
        registry.add(definition())
    registry.add(definition(version=2))
    registry.add(definition(scope="project:P1"))
    assert len(registry.all()) == 3


def test_all_keeps_registration_order() -> None:
    first, second = definition(id="one"), definition(id="two")
    assert WorkflowRegistry([first, second]).all() == [first, second]


def test_get_by_id_and_version_prefers_company() -> None:
    company = definition(id="g", version=3)
    project = definition(id="g", version=3, scope="project:P1")
    registry = WorkflowRegistry([project, company])
    assert registry.get("g", 3) is company
    assert registry.get("g", 4) is None
    assert registry.get("zzz", 3) is None


# --- files ----------------------------------------------------------------------------------


def test_load_workflow_reads_a_file(tmp_path: Path) -> None:
    path = tmp_path / "demo.yaml"
    path.write_text(GOOD, encoding="utf-8")
    assert load_workflow(path).id == "demo.flow"


def test_load_workflow_names_the_file_in_errors(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("id: [", encoding="utf-8")
    with pytest.raises(WorkflowError, match=r"^broken\.yaml: invalid YAML"):
        load_workflow(path)


def test_load_workflow_reports_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(WorkflowError, match=r"^nope\.yaml: cannot read file"):
        load_workflow(tmp_path / "nope.yaml")


def test_load_workflows_reads_a_directory_in_name_order(tmp_path: Path) -> None:
    (tmp_path / "b.yaml").write_text(GOOD.replace("demo.flow", "b.flow"), encoding="utf-8")
    (tmp_path / "a.yaml").write_text(GOOD.replace("demo.flow", "a.flow"), encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.yaml").write_text(GOOD.replace("demo.flow", "c.flow"), encoding="utf-8")
    registry = load_workflows(tmp_path)
    assert [d.id for d in registry.all()] == ["a.flow", "b.flow"]


def test_load_workflows_of_a_missing_directory_is_empty(tmp_path: Path) -> None:
    assert load_workflows(tmp_path / "missing").all() == []


def test_load_workflows_raises_on_the_first_bad_file(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("id: [", encoding="utf-8")
    (tmp_path / "b.yaml").write_text(GOOD, encoding="utf-8")
    with pytest.raises(WorkflowError, match=r"^a\.yaml"):
        load_workflows(tmp_path)


def test_the_shipped_sample_workflow_loads() -> None:
    registry = load_workflows(FIXTURE_DIR)
    flow = registry.find("core.Record", "project:P123")
    assert flow is not None
    assert flow.id == "core.review"
    assert flow.initial_state == "Draft"
    assert flow.state_names() == ["Draft", "Review", "Approved", "Issued"]
    approve = flow.transition("approve")
    assert approve is not None
    assert [type(g) for g in approve.guards] == [ExpectedLinksGuard, ConformanceGuard]
    assert [t.name for t in flow.transitions_from("Review")] == ["approve", "reject"]


def test_default_workflows_reads_the_schema_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    assert default_workflows().find("core.Record", "company") is not None


def test_default_workflows_follows_tl_schema_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "workflows").mkdir()
    (tmp_path / "workflows" / "x.yaml").write_text(GOOD, encoding="utf-8")
    monkeypatch.setenv("TL_SCHEMA_DIR", str(tmp_path))
    registry = default_workflows()
    assert [d.id for d in registry.all()] == ["demo.flow"]
