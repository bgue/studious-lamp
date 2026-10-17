"""Conformance checks for the P1-I7 integration contract (`tl_core.integration.contract`).

WS-A calls the ``check_*`` helpers from the tests of each action executor, of the mapping runtime
and of each enricher (``sys.path`` holds this directory, as for ``test_extractor_contract``). The
``test_*`` functions here pin the rules the contract models enforce themselves.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from typing import Any

import pytest
from pydantic import ValidationError
from tl_core.integration.contract import (
    ACCESS_RANK,
    ACTION_MAX_RESULT_BYTES,
    AUTOMATION_COMMANDS,
    ENRICHER_NAME_RE,
    MAPPING_LANGUAGE,
    MAPPING_MAX_COMMANDS,
    MAPPING_MAX_EXPRESSION_CHARS,
    MAPPING_MAX_SECONDS,
    MAX_MESSAGE_CHARS,
    PHASE1_EXECUTORS,
    RESERVED_CORRELATION_PREFIXES,
    RESERVED_LINK_SOURCES,
    RESERVED_SOURCE_PREFIXES,
    SERVER_SET_FIELDS,
    SERVICE_ACTOR_RE,
    ActionDefinition,
    ActionExecutor,
    ActionOutcome,
    ActionRequest,
    Enricher,
    EnrichmentInput,
    EnrichmentResult,
    EnrichmentSubject,
    EnrichmentValue,
    InboundEndpoint,
    MappedCommand,
    MappingOutcome,
    MappingRuntime,
    PlannedCommand,
    Problem,
    RecordRef,
    Rule,
    RuleStep,
    access_covers,
)

# --------------------------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------------------------


def check_problem(problem: Problem) -> None:
    assert len(problem.message) <= MAX_MESSAGE_CHARS
    assert "Traceback" not in problem.message
    assert "/home/" not in problem.message and "/tmp/" not in problem.message


def check_planned_command(planned: PlannedCommand) -> None:
    """A planned command is permitted only when an access is declared and nothing refuses it."""
    if planned.access is None:
        assert not planned.permitted, "a command nobody declared an access for is never permitted"
    if planned.problem is not None:
        check_problem(planned.problem)
    assert "actor" not in planned.command, "the runner sets the actor"


# --------------------------------------------------------------------------------------------
# Action executors
# --------------------------------------------------------------------------------------------


def check_outcome_shape(outcome: ActionOutcome) -> None:
    if outcome.status == "failed":
        assert outcome.problems
    if outcome.result is not None:
        size = len(json.dumps(outcome.result, sort_keys=True, separators=(",", ":")).encode())
        assert size <= ACTION_MAX_RESULT_BYTES
    for problem in outcome.problems:
        check_problem(problem)


def check_executor_contract(executor: ActionExecutor, requests: Iterable[ActionRequest]) -> None:
    """Run each request; every answer is a well-formed outcome, never an exception."""
    assert isinstance(executor, ActionExecutor)
    assert executor.kind in PHASE1_EXECUTORS
    seen = 0
    for request in requests:
        outcome = executor.execute(request)
        check_outcome_shape(outcome)
        seen += 1
    assert seen, "give the check at least one request"


# --------------------------------------------------------------------------------------------
# Mapping runtime (FANOUT D5)
# --------------------------------------------------------------------------------------------

#: Expressions the restricted profile accepts.
MAPPING_ALLOWED = (
    '{"command": "PostToFeed", "args": {"body": $string(note)}}',
    'results.{"command": "SetPsetValues", "args": {"pset": "nde", "values": {"result": result}}}',
    '$count(items) > 0 ? {"command": "PostToFeed", "args": {"body": $join(items, ", ")}} : []',
    'items[status = "open"].{"command": "PostToFeed", "args": {"body": $uppercase(name)}}',
)

#: Expressions the restricted profile refuses, each for a different reason.
MAPPING_FORBIDDEN = (
    "function($x) { $x }",  # a function definition (and so recursion)
    '$eval("1 + 1")',
    "$now()",
    "$millis()",
    "$random()",
    "$match(name, /a+/)",  # a regular expression
    '$replace(name, /a/, "b")',
    "$map(items, function($v) { $v })",  # a higher-order function and a lambda
    "$sift(record, function($v) { true })",
    "$substring(?, 0, 1)",  # partial application
    "x" * (MAPPING_MAX_EXPRESSION_CHARS + 1),  # too long
    "results.{",  # does not parse
)

NDE_PAYLOAD: dict[str, Any] = {
    "contractor": "acme-nde",
    "results": [
        {"weld": "47-1234-W012", "method": "RT", "result": "accept"},
        {"weld": "47-1234-W013", "method": "RT", "result": "reject"},
    ],
}
NDE_MAPPING = (
    'results.{"command": "SetPsetValues", "args": {"stream_id": {"$key": weld}, '
    '"pset": "nde", "values": {"method": method, "result": result}}}'
)
NDE_EXPECTED = [
    MappedCommand(
        command="SetPsetValues",
        args={
            "stream_id": {"$key": "47-1234-W012"},
            "pset": "nde",
            "values": {"method": "RT", "result": "accept"},
        },
    ),
    MappedCommand(
        command="SetPsetValues",
        args={
            "stream_id": {"$key": "47-1234-W013"},
            "pset": "nde",
            "values": {"method": "RT", "result": "reject"},
        },
    ),
]
#: Allowed by the profile, but too expensive: the time or memory bound must stop it.
MAPPING_RUNAWAY = "$count([1..10000].([1..10000]))"


def check_mapping_runtime_contract(runtime: MappingRuntime) -> None:
    """The restricted profile, the output rules and the bounds (WS-A T04 runtime)."""
    assert isinstance(runtime, MappingRuntime)
    assert runtime.language == MAPPING_LANGUAGE
    for expression in MAPPING_ALLOWED:
        assert runtime.check(expression) == [], expression
    for expression in MAPPING_FORBIDDEN:
        problems = runtime.check(expression)
        assert problems, f"the profile must refuse {expression[:40]!r}"
        for problem in problems:
            check_problem(problem)

    outcome = runtime.evaluate(NDE_MAPPING, NDE_PAYLOAD)
    assert outcome.status == "ok", outcome.problems
    assert outcome.commands == NDE_EXPECTED

    single = runtime.evaluate(
        '{"command": "PostToFeed", "args": {"body": contractor}}', NDE_PAYLOAD
    )
    assert single.status == "ok"
    assert single.commands == [MappedCommand(command="PostToFeed", args={"body": "acme-nde"})]

    for bad_output in (
        '"just text"',
        '{"command": "VoidRecord", "args": {}}',  # outside the automation allow-list
        '{"command": "PostToFeed", "args": {"body": "x", "actor": "user:admin"}}',
        '{"command": "PostToFeed", "args": {"deep": {"source": "rule:x"}}}',
        '{"command": "PostToFeed", "args": {}, "extra": 1}',
    ):
        refused = runtime.evaluate(bad_output, NDE_PAYLOAD)
        assert refused.status == "invalid_output", bad_output
        assert refused.commands == []

    count = MAPPING_MAX_COMMANDS + 1
    many = f'[1..{count}].{{"command": "PostToFeed", "args": {{"body": $string($)}}}}'
    assert runtime.evaluate(many, {}).status in ("invalid_output", "limit")

    broken = runtime.evaluate("results.{", NDE_PAYLOAD)
    assert broken.status == "error"

    started = time.monotonic()
    runaway = runtime.evaluate(MAPPING_RUNAWAY, {})
    assert runaway.status == "limit"
    # The envelope's wall clock plus the start-up of a child process.
    assert time.monotonic() - started < MAPPING_MAX_SECONDS + 5.0


# --------------------------------------------------------------------------------------------
# Enrichers (FANOUT D6)
# --------------------------------------------------------------------------------------------


def check_enricher_contract(enricher: Enricher, subjects: Iterable[EnrichmentSubject]) -> None:
    """Every result is well formed, deterministic and namespaced; nothing raises."""
    assert isinstance(enricher, Enricher)
    assert ENRICHER_NAME_RE.fullmatch(enricher.name), enricher.name
    assert enricher.version
    assert enricher.model_ref is None, "Phase 1 enrichers make no model call (ADR-0008)"
    seen = 0
    for subject in subjects:
        if not enricher.accepts(subject):
            continue
        result = enricher.enrich(subject)
        check_enrichment_result(enricher, subject, result)
        assert enricher.enrich(subject) == result, "an enricher is deterministic"
        seen += 1
    assert seen, "give the check at least one subject the enricher accepts"
    bare = EnrichmentSubject(record=RecordRef(id="r-bare", record_type="core.Record"), title="")
    if enricher.accepts(bare):
        check_enrichment_result(enricher, bare, enricher.enrich(bare))


def check_enrichment_result(
    enricher: Enricher, subject: EnrichmentSubject, result: EnrichmentResult
) -> None:
    assert result.enricher == enricher.name
    assert result.enricher_version == enricher.version
    if result.status == "failed":
        assert result.problems
    for problem in result.problems:
        check_problem(problem)
    assert any("ADR-0008" in note for note in result.notes), "say that no model was used"
    for proposed in result.values:
        EnrichmentValue(
            value_id="v-check",
            target=subject.record,
            property_path=f"enrich.{enricher.name}.{proposed.property}",
            value=proposed.value,
            enricher=enricher.name,
            enricher_version=enricher.version,
            confidence=proposed.confidence,
            inputs=[EnrichmentInput(record=subject.record)],
            produced_at="2026-10-17T00:00:00Z",
            acceptance_state="proposed",
        )


# --------------------------------------------------------------------------------------------
# Rules the contract models enforce
# --------------------------------------------------------------------------------------------


def _endpoint(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "app": "acme-nde",
        "name": "results",
        "scope": "project:P123",
        "mapping": NDE_MAPPING,
        "allowed_commands": ["SetPsetValues"],
        "service_actor": "svc:inbound-acme-nde-results",
        "owner": "user:admin",
    }
    return {**base, **changes}


def test_access_ranks_and_an_undeclared_access_covers_nothing() -> None:
    assert ACCESS_RANK == {"user": 0, "controller": 1, "admin": 2}
    assert access_covers("controller", "user")
    assert access_covers("admin", "controller")
    assert not access_covers("user", "controller")
    assert not access_covers("admin", None)
    assert not access_covers("root", "user")


def test_every_service_actor_kind_has_a_reserved_source_and_none_is_an_admin() -> None:
    for kind in ("rule", "inbound", "enricher", "action"):
        assert f"{kind}:" in RESERVED_SOURCE_PREFIXES
        assert SERVICE_ACTOR_RE.fullmatch(f"svc:{kind}-demo")
    assert SERVICE_ACTOR_RE.fullmatch("svc:admin") is None
    assert "thread_dispatch" in RESERVED_LINK_SOURCES
    assert "dispatch:" in RESERVED_CORRELATION_PREFIXES
    assert {"actor", "source", "scope", "correlation_id", "by_module"} <= SERVER_SET_FIELDS


def test_automation_never_names_a_destructive_or_admin_command() -> None:
    for name in ("VoidRecord", "ChangeSetting", "RetractLink", "AdminRetractLink", "RecordTag"):
        assert name not in AUTOMATION_COMMANDS


def test_a_mapped_command_refuses_server_fields_at_any_depth_and_unknown_commands() -> None:
    MappedCommand(command="SetPsetValues", args={"stream_id": {"$key": "W-1"}})
    for args in ({"actor": "user:x"}, {"values": {"source": "api"}}, {"a": [{"by_module": True}]}):
        with pytest.raises(ValidationError):
            MappedCommand(command="SetPsetValues", args=args)
    with pytest.raises(ValidationError):
        MappedCommand(command="VoidRecord")
    with pytest.raises(ValidationError):
        MappedCommand.model_validate({"command": "PostToFeed", "args": {}, "extra": 1})


def test_an_outcome_that_is_not_ok_says_why_and_carries_nothing() -> None:
    with pytest.raises(ValidationError):
        MappingOutcome(status="limit")
    with pytest.raises(ValidationError):
        MappingOutcome(
            status="error",
            commands=[MappedCommand(command="PostToFeed")],
            problems=[Problem(code="x", message="x")],
        )
    with pytest.raises(ValidationError):
        ActionOutcome(status="failed")


def test_an_endpoint_allows_only_automation_commands_and_starts_disabled_in_dry_run() -> None:
    endpoint = InboundEndpoint.model_validate(_endpoint())
    assert endpoint.dry_run and not endpoint.enabled
    assert endpoint.auth == "hmac_sha256"
    for bad in (
        {"allowed_commands": ["VoidRecord"]},
        {"service_actor": "svc:rule-x"},
        {"access": "admin"},
        {"max_body_bytes": 2 * 1024 * 1024},
        {"auth": "none"},
    ):
        with pytest.raises(ValidationError):
            InboundEndpoint.model_validate(_endpoint(**bad))


def test_a_rule_runs_only_allowed_commands_as_a_rule_actor_and_starts_disabled() -> None:
    rule = Rule(
        key="hse-notify",
        title="Notify HSE on #safety",
        scope="project:P123",
        when={"event_types": ["Feed.Posted"], "hashtags": ["safety"]},
        then=[RuleStep(command="PostToFeed", args={"body": "HSE notified of ${subject_key}"})],
        service_actor="svc:rule-hse-notify",
        owner="user:admin",
    )
    assert rule.mode == "propose" and not rule.enabled and rule.access == "user"
    with pytest.raises(ValidationError):
        RuleStep(command="ChangeSetting")
    with pytest.raises(ValidationError):
        RuleStep(command="PostToFeed", args={"correlation_id": "rule:x"})
    with pytest.raises(ValidationError):
        Rule.model_validate({**rule.model_dump(), "service_actor": "svc:inbound-x"})
    with pytest.raises(ValidationError):
        Rule.model_validate({**rule.model_dump(), "access": "admin"})


def test_phase1_action_executors_are_job_and_webhook_only() -> None:
    base: dict[str, Any] = {
        "name": "send_to_nde",
        "label": "Send to NDE contractor",
        "scope": "project:P123",
        "side_effect_class": "external",
        "owner": "user:admin",
    }
    hook = {"kind": "webhook", "url": "https://nde.example/in"}
    ActionDefinition.model_validate({**base, "executor": "webhook", "executor_config": hook})
    ActionDefinition.model_validate(
        {**base, "executor": "job", "executor_config": {"kind": "job", "job": "export.json"}}
    )
    with pytest.raises(ValidationError):
        ActionDefinition.model_validate(
            {**base, "executor": "mcp_tool", "executor_config": {"kind": "job", "job": "x"}}
        )
    with pytest.raises(ValidationError):
        ActionDefinition.model_validate(
            {**base, "executor": "job", "executor_config": {"kind": "webhook", "url": "https://x"}}
        )


def test_an_enrichment_value_stays_in_its_enrichers_layer() -> None:
    target = RecordRef(id="r1", key="ISD-001", record_type="documents.Document", version=3)
    good: dict[str, Any] = {
        "value_id": "v1",
        "target": target,
        "property_path": "enrich.doc_classifier.doc_type",
        "value": "IDX",
        "enricher": "doc_classifier",
        "enricher_version": "1",
        "confidence": 0.8,
        "inputs": [EnrichmentInput(record=target, file_sha256="0" * 64)],
        "produced_at": "2026-10-17T00:00:00Z",
        "acceptance_state": "proposed",
    }
    EnrichmentValue.model_validate(good)
    for path in (
        "valve_data.size_in",
        "enrich.other.doc_type",
        "enrich.doc_classifier.",
        "enrich.doc_classifier.a.b",
    ):
        with pytest.raises(ValidationError):
            EnrichmentValue.model_validate({**good, "property_path": path})
    with pytest.raises(ValidationError):
        EnrichmentValue.model_validate({**good, "confidence": 1.5})
    with pytest.raises(ValidationError):
        EnrichmentValue.model_validate({**good, "inputs": []})
