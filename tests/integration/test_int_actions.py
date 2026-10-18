"""Actions: define, invoke, run through the job kind, and what the ledger shows (FANOUT D8, D11).

The webhook goes to a scripted transport and a resolver table; the job executor runs the example
job ``echo``. Nothing leaves the machine.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from intworld import ADMIN, PERSON, SCOPE, World
from tl_core.integration.action_jobs import EchoJob
from tl_core.integration.actions.service import (
    DefineAction,
    RetireAction,
    ReviseAction,
    RotateActionSecret,
    define_action,
    handle_retire_action,
    handle_revise_action,
    rotate_action_secret,
)
from tl_core.integration.errors import (
    ActionAccessError,
    DuplicateIntegrationError,
    IntegrationNotFoundError,
    IntegrationStateError,
    InvalidIntegrationError,
)
from tl_core.integration.executors.job import use_jobs
from tl_core.services import proposals
from tl_core.services.errors import ProposalAccessError, ProposalDeciderError
from tl_core.webhooks.rows import as_list, as_object, load_json
from tl_core.webhooks.signing import SigningSecret, verify
from tl_core.webhooks.testing import ScriptedTransport
from tl_core.webhooks.transport import TransportResult

OTHER = "user:mlee"


def payload(event: dict[str, Any]) -> dict[str, Any]:
    return as_object(load_json(event["payload"]))


def kinds(world: World) -> list[str]:
    return [
        r["event_type"]
        for r in world.rows(
            "SELECT event_type FROM events WHERE stream_type = 'core.ActionInvocation' ORDER BY seq"
        )
    ]


def target(world: World, key: str = "47-1234-W012") -> str:
    return world.record(key)


# --- defining ----------------------------------------------------------------------------------


def test_a_webhook_action_is_defined_and_its_secret_is_shown_once(world: World) -> None:
    made = world.define_action()
    assert made.secret is not None and made.secret.secret.startswith("whsec_")
    assert "whsec_" not in repr(made) and "whsec_" not in repr(made.secret)
    row = world.rows("SELECT * FROM cur_action_definition")[0]
    assert (row["name"], row["version"], row["executor"]) == ("send_to_nde", 1, "webhook")
    assert row["secret_id"] == made.secret_id and not bool(row["retired"])
    config = as_object(load_json(row["executor_config_json"]))
    assert config["secret_id"] == made.secret_id and "secret" not in config
    stored = world.rows("SELECT secret, owner_kind FROM int_secret")
    assert [(r["owner_kind"], r["secret"]) for r in stored] == [("action", made.secret.secret)]


def test_the_secret_is_in_no_event_and_no_projection(world: World) -> None:
    made = world.define_action()
    world.invoke(targets=[target(world)])
    assert made.secret is not None
    needle = made.secret.secret
    for table in ("events", "outbox_events", "cur_action_definition", "cur_action_invocation"):
        dump = json.dumps(world.rows(f"SELECT * FROM {table}"), default=str)  # noqa: S608
        assert needle not in dump, table


def test_a_job_action_has_no_secret(world: World) -> None:
    with use_jobs({"echo": EchoJob}):
        made = world.define_action(
            name="echo_it",
            executor="job",
            executor_config={"job": "echo"},
            side_effect_class="read",
        )
    assert made.secret is None and made.secret_id is None
    assert world.rows("SELECT * FROM int_secret") == []


@pytest.mark.parametrize(
    ("fields", "wanted"),
    [
        ({"executor": "mcp_tool", "executor_config": {"tool": "x"}}, "executor"),
        ({"executor": "connector", "executor_config": {}}, "executor"),
        ({"executor": "agent", "executor_config": {}}, "executor"),
        ({"executor": "job", "executor_config": {"job": "no_such_job"}}, "no job is installed"),
        ({"executor_config": {"url": "https://10.0.0.1/h"}}, "not allowed"),
        ({"executor_config": {"url": "https://169.254.169.254/h"}}, "not allowed"),
        ({"executor_config": {"url": "http://nde.example.net/h"}}, "not allowed"),
        ({"executor_config": {"url": "https://u:p@nde.example.net/h"}}, "not allowed|http"),
        ({"executor_config": {"url": "ftp://nde.example.net/h"}}, "not allowed|http"),
        (
            {"executor_config": {"url": "https://nde.example.net/h", "secret_id": "X" * 26}},
            "secret",
        ),
        ({"side_effect_class": "nuclear"}, "side_effect_class"),
        ({"access": "root"}, "access"),
        ({"name": "Bad Name"}, "name"),
        ({"applies_to": {"condition": "status:("}}, "applies_to"),
        (
            {"parameters": [{"name": "a", "label": "A"}, {"name": "a", "label": "B"}]},
            "twice",
        ),
        ({"integration_app": "no-such-app"}, "no integration app"),
    ],
)
def test_a_definition_that_cannot_run_is_not_stored(
    world: World, fields: dict[str, Any], wanted: str
) -> None:
    import re

    with pytest.raises(InvalidIntegrationError) as caught:
        world.define_action(**fields)
    assert re.search(wanted, str(caught.value), re.IGNORECASE), str(caught.value)
    assert world.rows("SELECT * FROM cur_action_definition") == []
    assert world.rows("SELECT * FROM int_secret") == []


def test_a_name_is_unique(world: World) -> None:
    world.define_action()
    with pytest.raises(DuplicateIntegrationError):
        world.define_action()


def test_an_unresolvable_name_may_be_defined_but_a_private_one_may_not(world: World) -> None:
    world.define_action(executor_config={"url": "https://not-yet.example.net/h"})
    with pytest.raises(InvalidIntegrationError):
        world.define_action(name="b", executor_config={"url": "https://127.0.0.1/h"})


# --- invoking ----------------------------------------------------------------------------------


def test_an_invocation_is_requested_and_queued(world: World) -> None:
    world.define_action(parameters=[{"name": "method", "label": "Method", "required": True}])
    record = target(world)
    made = world.invoke(targets=[record], parameters={"method": "RT"})
    event = made.events[0]
    assert event.event_type == "Action.Requested" and event.actor == PERSON
    assert event.source == "test" and event.stream_version == 1
    row = world.invocations()[0]
    assert (row["status"], row["action"], row["action_version"], row["invoked_by"]) == (
        "requested",
        "send_to_nde",
        1,
        PERSON,
    )
    refs = as_list(load_json(row["targets_json"]))
    assert refs[0]["id"] == record and refs[0]["key"] == "47-1234-W012"
    linked = world.rows("SELECT record_id FROM cur_action_invocation_target")
    assert [r["record_id"] for r in linked] == [record]
    queued = world.rows("SELECT kind, state, scope, max_attempts FROM job_queue")
    assert queued == [{"kind": "action", "state": "queued", "scope": SCOPE, "max_attempts": 3}]


def test_an_action_that_does_not_exist_or_is_retired_is_not_found(world: World) -> None:
    with pytest.raises(IntegrationNotFoundError):
        world.invoke("nope")
    made = world.define_action()
    with world.factory() as uow:
        handle_retire_action(
            uow,
            RetireAction(
                actor=ADMIN,
                source="t",
                scope=SCOPE,
                definition_id=made.definition_id,
                reason="gone",
            ),
        )
    with pytest.raises(IntegrationNotFoundError):
        world.invoke()
    with world.factory() as uow, pytest.raises(IntegrationStateError):
        handle_retire_action(
            uow,
            RetireAction(
                actor=ADMIN, source="t", scope=SCOPE, definition_id=made.definition_id, reason="x"
            ),
        )


def test_a_project_action_is_not_visible_in_another_project(world: World) -> None:
    world.define_action()
    with pytest.raises(IntegrationNotFoundError):
        world.invoke(scope="project:OTHER")


def test_a_company_action_can_be_invoked_in_a_project(world: World) -> None:
    world.define_action(scope="company")
    record = target(world)
    assert world.invoke(targets=[record]).events[0].scope == SCOPE


def test_the_access_of_the_action_decides_who_may_invoke(world: World) -> None:
    world.define_action(access="controller")
    record = target(world)
    with pytest.raises(ActionAccessError):
        world.invoke(targets=[record])
    with pytest.raises(ActionAccessError):
        world.invoke(targets=[record], holds=lambda level: level == "user")
    assert world.invoke(targets=[record], holds=lambda level: level in ("user", "controller"))
    assert world.invocations()[0]["invoked_by"] == PERSON
    world.define_action(name="admin_only", access="admin")
    with pytest.raises(ActionAccessError):
        world.invoke("admin_only", holds=lambda level: level in ("user", "controller"))


def test_the_message_of_a_refusal_names_the_role_not_the_caller(world: World) -> None:
    world.define_action(access="admin")
    with pytest.raises(ActionAccessError, match="admin"):
        world.invoke()


def test_the_targets_must_be_records_of_the_scope_that_the_action_applies_to(world: World) -> None:
    world.define_action(applies_to={"record_types": ["core.Record"]})
    world.define_action(name="docs_only", applies_to={"record_types": ["documents.*"]})
    record = target(world)
    other = world.record("OTHER-1", scope="project:OTHER")
    with pytest.raises(InvalidIntegrationError, match="does not apply"):
        world.invoke("docs_only", targets=[record])
    unknown = IntegrationNotFoundError
    with pytest.raises(unknown):
        world.invoke(targets=[other])
    with pytest.raises(unknown):
        world.invoke(targets=["01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"])
    first = pytest.raises(unknown, match="a target is not a record of this scope")
    with first:
        world.invoke(targets=[other])
    with pytest.raises(InvalidIntegrationError, match="different targets"):
        world.invoke(targets=[record, record])


def test_the_condition_of_applies_to_is_checked_on_each_target(world: World) -> None:
    world.define_action(applies_to={"record_types": ["*"], "condition": "key:W-1"})
    good, bad = world.record("W-1"), world.record("W-2")
    assert world.invoke(targets=[good])
    with pytest.raises(InvalidIntegrationError, match="does not apply"):
        world.invoke(targets=[good, bad])


def test_too_many_targets_are_refused_by_the_command_itself(world: World) -> None:
    from pydantic import ValidationError

    world.define_action()
    with pytest.raises(ValidationError):
        world.invoke(targets=[f"id{n}" for n in range(101)])


@pytest.mark.parametrize(
    ("values", "wanted"),
    [
        ({}, "method is required"),
        ({"method": "RT", "extra": 1}, "No parameter extra"),
        ({"method": 5}, "must be text"),
        ({"method": "XX"}, "one of the choices"),
        ({"method": "RT", "count": "x"}, "whole number"),
        ({"method": "RT", "count": True}, "whole number"),
        ({"method": "RT", "flag": "yes"}, "true or false"),
        ({"method": "RT", "when": "someday"}, "date"),
        ({"method": "RT", "note": "n" * 11}, "at most 10"),
    ],
)
def test_the_parameters_must_fit_the_definition(
    world: World, values: dict[str, Any], wanted: str
) -> None:
    world.define_action(
        parameters=[
            {"name": "method", "label": "M", "required": True, "choices": ["RT", "UT"]},
            {"name": "count", "label": "C", "kind": "int"},
            {"name": "flag", "label": "F", "kind": "bool"},
            {"name": "when", "label": "W", "kind": "date"},
            {"name": "note", "label": "N", "max_length": 10},
        ]
    )
    with pytest.raises(InvalidIntegrationError, match=wanted):
        world.invoke(parameters=values)
    assert world.invocations() == []


def test_valid_parameters_of_every_kind_are_kept(world: World) -> None:
    world.define_action(
        parameters=[
            {"name": "method", "label": "M", "choices": ["RT"]},
            {"name": "count", "label": "C", "kind": "int"},
            {"name": "ratio", "label": "R", "kind": "decimal"},
            {"name": "flag", "label": "F", "kind": "bool"},
            {"name": "when", "label": "W", "kind": "date"},
        ]
    )
    values = {"method": "RT", "count": 3, "ratio": "1.5", "flag": False, "when": "2026-10-17"}
    world.invoke(parameters=values)
    assert as_object(load_json(world.invocations()[0]["parameters_json"])) == values


def test_parameters_over_the_limit_are_refused(world: World) -> None:
    world.define_action(parameters=[{"name": "note", "label": "N"}])
    with pytest.raises(InvalidIntegrationError, match="too large"):
        world.invoke(parameters={"note": "x" * 20_000})


# --- approval ----------------------------------------------------------------------------------


def test_an_action_that_needs_approval_waits_for_another_person(world: World) -> None:
    world.define_action(requires_approval=True, access="controller")
    record = target(world)
    held = world.invoke(targets=[record], holds=lambda level: level in ("user", "controller"))
    assert held.events == [] and world.invocations() == []
    with world.factory(readonly=True) as uow:
        pending = proposals.list_proposals(uow.conn(), SCOPE, status="pending")
    assert [(p.tool, p.agent, p.command_type) for p in pending] == [
        ("action", PERSON, "InvokeAction")
    ]
    pid = pending[0].proposal_id
    with world.factory() as uow, pytest.raises(ProposalDeciderError):
        proposals.accept_proposal(uow, proposal_id=pid, by=PERSON, holds=lambda level: True)
    with world.factory() as uow, pytest.raises(ProposalAccessError):
        proposals.accept_proposal(uow, proposal_id=pid, by=OTHER)  # a user, the action needs more
    done = proposals.accept_or_fail(
        world.factory, proposal_id=pid, by=OTHER, holds=lambda level: level != "admin"
    )
    assert done.status == "accepted"
    row = world.invocations()[0]
    assert (row["status"], row["invoked_by"], row["proposal_id"]) == ("requested", PERSON, pid)
    requested = world.events("Action.Requested")[0]
    assert requested["actor"] == OTHER, "the approver's act; the requester stays in the payload"
    assert payload(requested)["invoked_by"] == PERSON


def test_the_requester_must_hold_the_access_before_a_proposal_is_made(world: World) -> None:
    world.define_action(requires_approval=True, access="controller")
    with pytest.raises(ActionAccessError):
        world.invoke()
    assert world.rows("SELECT proposal_id FROM cur_proposals") == []


def test_the_approver_needs_the_access_of_the_action(world: World) -> None:
    world.define_action(requires_approval=True, access="admin")
    world.invoke(holds=lambda level: True)
    with world.factory(readonly=True) as uow:
        pid = proposals.list_proposals(uow.conn(), SCOPE, status="pending")[0].proposal_id
    with pytest.raises(ProposalAccessError):
        proposals.accept_or_fail(
            world.factory, proposal_id=pid, by=OTHER, holds=lambda level: level == "controller"
        )
    with world.factory(readonly=True) as uow:
        assert proposals.get_proposal(uow.conn(), pid).status == "pending", "a refusal of access"
    assert world.invocations() == []


# --- running -----------------------------------------------------------------------------------


def secret_of(made: Any) -> SigningSecret:
    return SigningSecret(made.secret.secret)


def test_a_webhook_action_runs_and_the_ledger_tells_the_story(world: World) -> None:
    made = world.define_action(result_handling=["store"])
    record = target(world)
    world.transport.default = TransportResult(
        status=200, latency_ms=3, excerpt='{"accepted": true, "ticket": "NDE-9"}'
    )
    requested = world.invoke(targets=[record], parameters={}).events[0]
    results = world.run_jobs()
    assert [r.outcome for r in results] == ["done"]
    assert kinds(world) == ["Action.Requested", "Action.Running", "Action.Completed"]
    row = world.invocations()[0]
    assert (row["status"], row["attempt"], row["http_status"]) == ("completed", 1, 200)
    assert as_object(load_json(row["result_json"])) == {"accepted": True, "ticket": "NDE-9"}
    for name in ("Action.Running", "Action.Completed"):
        event = world.events(name)[0]
        assert event["actor"] == "svc:action-send_to_nde"
        assert event["source"] == "action:send_to_nde@1"
        assert event["correlation_id"] == f"action:{requested.stream_id}"
        assert event["causation_id"] == requested.event_id
    sent = world.transport.sent[0]
    assert verify(sent.headers, sent.body, [secret_of(made)], now=None, tolerance_s=10**9)
    assert json.loads(sent.body)["invocation_id"] == requested.stream_id


def test_a_retryable_answer_is_tried_again_and_only_the_end_is_recorded(world: World) -> None:
    world.define_action()
    world.transport.script = [503, 502, 200]
    world.invoke()
    results = world.run_jobs()
    assert [r.outcome for r in results] == ["retry", "retry", "done"]
    assert kinds(world) == [
        "Action.Requested",
        "Action.Running",
        "Action.Running",
        "Action.Running",
        "Action.Completed",
    ]
    assert len(world.transport.sent) == 3
    assert world.invocations()[0]["attempt"] == 3


def test_a_receiver_that_keeps_failing_ends_in_one_failed_event(world: World) -> None:
    world.define_action()
    world.transport.default = TransportResult(status=503, latency_ms=1, excerpt="down")
    world.invoke()
    world.run_jobs()
    assert kinds(world).count("Action.Failed") == 1 and kinds(world).count("Action.Running") == 3
    row = world.invocations()[0]
    assert (row["status"], row["http_status"]) == ("failed", 503)
    problems = as_list(load_json(row["problems_json"]))
    assert problems[0]["code"] == "http_error"


def test_a_final_answer_is_not_retried(world: World) -> None:
    world.define_action()
    world.transport.default = TransportResult(status=400, latency_ms=1, excerpt="no")
    world.invoke()
    world.run_jobs()
    assert len(world.transport.sent) == 1
    assert kinds(world) == ["Action.Requested", "Action.Running", "Action.Failed"]


def test_an_address_that_became_private_is_refused_at_the_attempt(world: World) -> None:
    world.define_action()
    world.invoke()
    from intworld import HOSTS

    HOSTS["nde.example.net"] = ["10.9.9.9"]
    try:
        world.run_jobs()
    finally:
        HOSTS["nde.example.net"] = ["93.184.216.34"]
    assert world.transport.sent == []
    problems = as_list(load_json(world.invocations()[0]["problems_json"]))
    assert problems[0]["code"] == "egress_denied"
    assert kinds(world).count("Action.Running") == 1, "not retried"


def test_the_kill_switch_fails_the_job_and_nothing_is_sent(world: World) -> None:
    world.define_action()
    world.invoke()
    world.setting("integration.kill_switch", True)
    world.run_jobs()
    assert world.transport.sent == []
    problems = as_list(load_json(world.invocations()[0]["problems_json"]))
    assert problems[0]["code"] == "killed"
    assert kinds(world).count("Action.Running") == 1, "killed is final, not retried"


def test_a_retired_action_or_a_switched_off_app_stops_a_queued_invocation(world: World) -> None:
    made = world.define_action()
    world.invoke()
    with world.factory() as uow:
        handle_retire_action(
            uow,
            RetireAction(
                actor=ADMIN, source="t", scope=SCOPE, definition_id=made.definition_id, reason="r"
            ),
        )
    world.run_jobs()
    assert world.transport.sent == []
    problems = as_list(load_json(world.invocations()[0]["problems_json"]))
    assert problems[0]["code"] == "action_disabled"


def test_post_to_feed_makes_a_post_that_the_completion_caused(world: World) -> None:
    world.define_action(result_handling=["store", "post_to_feed"])
    world.invoke()
    world.run_jobs()
    post = world.posts()[0]
    completed = world.events("Action.Completed")[0]
    assert post["actor"] == "svc:action-send_to_nde" and post["source"] == "action:send_to_nde@1"
    assert post["causation_id"] == completed["event_id"]
    assert post["body"].startswith("Send to NDE: done")


def test_a_job_action_runs_the_example_job(world: World) -> None:
    with use_jobs({"echo": EchoJob}):
        world.define_action(
            name="echo_it",
            executor="job",
            executor_config={"job": "echo"},
            side_effect_class="read",
        )
        record = target(world)
        world.invoke("echo_it", targets=[record])
        world.run_jobs()
    row = world.invocations()[0]
    assert row["status"] == "completed"
    assert as_object(load_json(row["result_json"]))["targets"] == ["47-1234-W012"]
    assert world.transport.sent == []


def test_a_job_that_is_gone_at_run_time_fails_the_invocation(world: World) -> None:
    with use_jobs({"echo": EchoJob}):
        world.define_action(
            name="echo_it",
            executor="job",
            executor_config={"job": "echo"},
            side_effect_class="read",
        )
        world.invoke("echo_it")
    with use_jobs({}):
        world.run_jobs()
    problems = as_list(load_json(world.invocations()[0]["problems_json"]))
    assert problems[0]["code"] == "unknown_job"


# --- revising, rotating --------------------------------------------------------------------------


def test_a_revision_is_a_new_version_and_an_invocation_remembers_the_one_it_ran(
    world: World,
) -> None:
    made = world.define_action()
    world.invoke()
    with world.factory() as uow:
        handle_revise_action(
            uow,
            ReviseAction(
                actor=ADMIN, source="t", scope=SCOPE, definition_id=made.definition_id,
                changes={"label": "Send to the NDE contractor"}, reason="clearer",
            ),
        )  # fmt: skip
    row = world.rows("SELECT * FROM cur_action_definition")[0]
    assert (row["version"], row["label"], row["secret_id"]) == (
        2,
        "Send to the NDE contractor",
        made.secret_id,
    )
    config = as_object(load_json(row["executor_config_json"]))
    assert config["secret_id"] == made.secret_id
    world.invoke()
    assert [i["action_version"] for i in world.invocations()] == [1, 2]


def test_a_revision_cannot_change_the_identity_or_the_secret(world: World) -> None:
    made = world.define_action()
    for changes in (
        {"name": "other"},
        {"executor": "job"},
        {"scope": "company"},
        {"secret_id": "X" * 26},
        {"executor_config": {"url": "https://nde.example.net/h", "secret_id": "X" * 26}},
        {"executor_config": {"url": "https://10.0.0.1/h"}},
        {},
    ):
        with world.factory() as uow, pytest.raises(InvalidIntegrationError):
            handle_revise_action(
                uow,
                ReviseAction(
                    actor=ADMIN, source="t", scope=SCOPE, definition_id=made.definition_id,
                    changes=changes, reason="r",
                ),
            )  # fmt: skip
    assert world.rows("SELECT version FROM cur_action_definition")[0]["version"] == 1


def test_rotating_the_secret_lets_the_old_one_sign_for_the_overlap(world: World) -> None:
    made = world.define_action()
    with world.factory() as uow:
        rotated = rotate_action_secret(
            uow,
            RotateActionSecret(
                actor=ADMIN, source="t", scope=SCOPE, definition_id=made.definition_id
            ),
        )
    assert rotated.secret is not None and made.secret is not None
    assert rotated.secret.secret != made.secret.secret
    world.invoke()
    world.run_jobs()
    sent = world.transport.sent[0]
    assert len(sent.headers["webhook-signature"].split()) == 2
    for issued in (made, rotated):
        verify(sent.headers, sent.body, [secret_of(issued)], now=None, tolerance_s=10**9)
    event = payload(world.events("ActionDefinition.SecretRotated")[0])
    assert event["secret_id"] == rotated.secret_id and event["previous_secret_id"] == made.secret_id
    assert rotated.secret.secret not in json.dumps(world.rows("SELECT * FROM events"), default=str)


def test_a_job_action_has_no_secret_to_rotate(world: World) -> None:
    with use_jobs({"echo": EchoJob}):
        made = world.define_action(
            name="echo_it",
            executor="job",
            executor_config={"job": "echo"},
            side_effect_class="read",
        )
    with world.factory() as uow, pytest.raises(IntegrationStateError):
        rotate_action_secret(
            uow,
            RotateActionSecret(
                actor=ADMIN, source="t", scope=SCOPE, definition_id=made.definition_id
            ),
        )


def test_define_refuses_a_second_secret_from_the_client(world: World) -> None:
    with world.factory() as uow, pytest.raises(InvalidIntegrationError):
        define_action(
            uow,
            DefineAction(
                actor=ADMIN, source="t", scope=SCOPE, name="x", label="X", executor="webhook",
                executor_config={"url": "https://nde.example.net/h", "secret_id": "S" * 26},
                side_effect_class="external",
            ),
            policy=world.policy,
        )  # fmt: skip


def test_an_executor_that_is_not_installed_fails_the_invocation(world: World) -> None:
    world.define_action()
    world.invoke()
    kind = world.job_runner()
    kind._kinds["action"]._executors.clear()  # type: ignore[attr-defined]
    kind.run_until_idle()
    problems = as_list(load_json(world.invocations()[0]["problems_json"]))
    assert problems[0]["code"] == "executor_unavailable"


def test_the_transport_is_the_only_way_out(world: World) -> None:
    """A guard on the test itself: the world's transport is the scripted one."""
    assert isinstance(world.transport, ScriptedTransport)


def test_nothing_is_requested_while_the_kill_switch_is_on(world: World) -> None:
    world.define_action()
    record = target(world)
    world.setting("integration.kill_switch", True)
    with pytest.raises(IntegrationStateError, match="stopped"):
        world.invoke(targets=[record])
    assert world.invocations() == []
    world.setting("integration.kill_switch", False)
    assert world.invoke(targets=[record]).events
