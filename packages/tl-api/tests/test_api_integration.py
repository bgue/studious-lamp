"""The integration commands over HTTP: who may run them (P1-I7 WS-A, FANOUT D12).

Rules and action authoring are the admin's. ``InvokeAction`` is open to any signed-in person for
an action open to any person; the action's own access (controller, admin) is judged by ``holds``,
which the route builds from the caller's principal and never reads from the body. An agent runs
none of them.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness import Harness
from tl_api.commands import COMMANDS
from tl_api.tokens import add_token
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_core.integration.actions.service import DefineAction, define_action
from tl_core.webhooks.egress import EgressPolicy

PASSWORD = "correct horse battery"
SCOPE = "project:P123"

#: Command to the access it needs. A change here is a decision (ADR-0017), not a refactor.
EXPECTED_ACCESS = {
    "CreateRule": "admin",
    "ReviseRule": "admin",
    "EnableRule": "admin",
    "DisableRule": "admin",
    "InvokeAction": "user",
    "ReviseAction": "admin",
    "RetireAction": "admin",
    "RegisterIntegrationApp": "admin",
    "ReviseIntegrationApp": "admin",
    "SetIntegrationAppEnabled": "admin",
    "ReviseInboundEndpoint": "admin",
    "SetInboundEndpointEnabled": "admin",
    "RetryInboundDelivery": "admin",
    "RegisterEnricher": "admin",
    "ReviseEnricher": "admin",
    "SetEnricherEnabled": "admin",
    "RunEnricher": "user",
    "AcceptEnrichment": "user",
    "RejectEnrichment": "user",
}
RULE = {
    "key": "hse-notify",
    "title": "Notify HSE",
    "when": {"event_types": ["Feed.Posted"], "hashtags": ["safety"]},
    "then": [{"command": "PostToFeed", "args": {"body": "HSE notified"}}],
}


class People:
    def __init__(self, harness: Harness) -> None:
        with harness.backend() as uow:
            for name, roles in (
                ("boss", ["admin"]),
                ("dora", ["user", "document_controller"]),
                ("bob", ["user"]),
            ):
                accounts.create_account(
                    uow, username=name, display_name=name, kind="person", roles=roles,
                    password=prepare_password(PASSWORD), by="svc:test",
                )  # fmt: skip
        self.boss = self._client(harness, "boss")
        self.dora = self._client(harness, "dora")
        self.bob = self._client(harness, "bob")
        self.agent = TestClient(harness.app, raise_server_exceptions=False)
        token = add_token(harness.settings.tokens_path, "agent:triage")
        self.agent.headers.update({"Authorization": f"Bearer {token}"})

    @staticmethod
    def _client(harness: Harness, name: str) -> TestClient:
        _, token = sessions.sign_in(harness.backend, username=name, password=PASSWORD)
        client = harness.client_for(None)
        client.headers.update({"Authorization": f"Bearer {token}"})
        return client


@pytest.fixture
def people(harness: Harness) -> People:
    return People(harness)


def run(client: TestClient, name: str, **body: Any) -> Any:
    return client.post(f"/commands/{name}", json={"scope": SCOPE, **body})


def define(harness: Harness, name: str, access: str) -> None:
    policy = EgressPolicy((), lambda host, port: ["93.184.216.34"])
    with harness.backend() as uow:
        define_action(
            uow,
            DefineAction(
                actor="user:boss", source="test", scope=SCOPE, name=name, label=name,
                executor="webhook", executor_config={"url": "https://nde.example.net/h"},
                side_effect_class="external", access=access,
            ),
            policy=policy,
        )  # fmt: skip


def test_every_integration_command_has_the_access_pinned_here() -> None:
    table = {spec.name: spec.access for spec in COMMANDS if spec.name in EXPECTED_ACCESS}
    assert table == EXPECTED_ACCESS
    assert {spec.name for spec in COMMANDS if spec.needs_holds} == {"InvokeAction"}


def test_an_agent_runs_none_of_them(people: People) -> None:
    for name in EXPECTED_ACCESS:
        refused = run(people.agent, name)
        assert refused.status_code == 403, name
        assert refused.json()["error"] == "agent_must_propose", name


def test_a_rule_is_authored_by_an_admin_only(people: People) -> None:
    for client in (people.bob, people.dora):
        refused = run(client, "CreateRule", **RULE)
        assert refused.status_code == 403, refused.text
    made = run(people.boss, "CreateRule", **RULE)
    assert made.status_code == 200, made.text
    rule_id = made.json()["stream_id"]
    for name in ("EnableRule", "DisableRule"):
        assert run(people.bob, name, rule_id=rule_id).status_code == 403
    revise = {"rule_id": rule_id, "changes": {"mode": "act"}, "reason": "go"}
    assert run(people.dora, "ReviseRule", **revise).status_code == 403
    assert run(people.boss, "ReviseRule", **revise).status_code == 200
    assert run(people.boss, "EnableRule", rule_id=rule_id).status_code == 200


def test_a_rule_with_a_server_field_or_a_bad_placeholder_is_a_422(people: People) -> None:
    bad_args = {**RULE, "then": [{"command": "PostToFeed", "args": {"actor": "user:boss"}}]}
    refused = run(people.boss, "CreateRule", **bad_args)
    assert refused.status_code == 422 and refused.json()["error"] == "invalid_integration"
    bad_binding = {**RULE, "then": [{"command": "PostToFeed", "args": {"body": "${nope}"}}]}
    assert run(people.boss, "CreateRule", **bad_binding).status_code == 422
    assert run(people.boss, "CreateRule", **{**RULE, "when": {}}).status_code == 422


def test_the_access_of_an_action_is_judged_from_the_callers_principal(
    people: People, harness: Harness
) -> None:
    define(harness, "open_one", "user")
    define(harness, "ctl_one", "controller")
    define(harness, "adm_one", "admin")
    expected = {
        ("bob", "open_one"): 200,
        ("bob", "ctl_one"): 403,
        ("bob", "adm_one"): 403,
        ("dora", "ctl_one"): 200,
        ("dora", "adm_one"): 403,
        ("boss", "ctl_one"): 200,
        ("boss", "adm_one"): 200,
    }
    clients = {"bob": people.bob, "dora": people.dora, "boss": people.boss}
    for (who, action), status in expected.items():
        answer = run(clients[who], "InvokeAction", action=action)
        assert answer.status_code == status, (who, action, answer.text)
        if status == 403:
            assert answer.json()["error"] == "action_access"


def test_holds_cannot_be_sent_in_the_body(people: People, harness: Harness) -> None:
    define(harness, "adm_one", "admin")
    refused = run(people.bob, "InvokeAction", action="adm_one", holds=True)
    assert refused.status_code == 422
    assert run(people.bob, "InvokeAction", action="adm_one").status_code == 403


def test_a_client_cannot_name_the_source_or_the_correlation_of_an_action(
    people: People, harness: Harness
) -> None:
    define(harness, "open_one", "user")
    for extra in (
        {"source": "action:open_one@1"},
        {"source": "rule:x@1/d1"},
        {"correlation_id": "action:01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"},
        {"causation_id": "rule:01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"},
    ):
        refused = run(people.bob, "InvokeAction", action="open_one", **extra)
        assert refused.status_code == 422, extra
        assert refused.json()["error"] == "reserved_identifier", extra


def test_an_action_that_does_not_exist_is_a_404(people: People) -> None:
    answer = run(people.bob, "InvokeAction", action="nope")
    assert answer.status_code == 404 and answer.json()["error"] == "integration_not_found"


# --- the routes that are not commands: secrets shown once, dry runs, reads ----------------------

ACTION = {
    "scope": SCOPE,
    "name": "send_to_nde",
    "label": "Send to NDE",
    "executor": "webhook",
    "executor_config": {"url": "https://nde.example.net/hooks/request"},
    "side_effect_class": "external",
}


def test_the_integration_routes_are_the_admins_and_an_agent_has_none(people: People) -> None:
    posts = [
        "/admin/integration/actions",
        "/admin/integration/endpoints",
        "/admin/integration/rules/dry-run",
        "/admin/integration/endpoints/dry-run",
    ]
    for path in posts:
        for client in (people.bob, people.dora):
            assert client.post(path, json={}).status_code == 403, path
        assert people.agent.post(path, json={}).status_code == 403, path
    assert people.bob.get("/admin/integration/deliveries").status_code == 403
    assert people.agent.get("/integration/rules").status_code == 403


def test_the_secret_of_a_new_action_is_in_the_answer_once_and_in_no_read(
    people: People, harness: Harness
) -> None:
    from tl_core.webhooks.egress import SETTING_ALLOWLIST  # noqa: F401

    made = people.boss.post("/admin/integration/actions", json=ACTION)
    if made.status_code != 200:  # the egress check resolves the host; allow it for the test
        from tl_core.services.settings import ChangeSetting, handle_change_setting

        with harness.backend() as uow:
            handle_change_setting(
                uow,
                ChangeSetting(
                    actor="user:boss", source="test", scope="company", key=SETTING_ALLOWLIST,
                    layer="company", value=["nde.example.net"], reason="test", accept_risk=True,
                ),
            )  # fmt: skip
        made = people.boss.post("/admin/integration/actions", json=ACTION)
    assert made.status_code == 200, made.text
    secret = made.json()["secret"]
    assert secret.startswith("whsec_") and len(made.json()["id"]) == 26
    for client in (people.boss, people.bob):
        listed = client.get("/integration/actions")
        assert listed.status_code == 200 and secret not in listed.text
        assert "nde.example.net" not in listed.text  # the executor's configuration is not shown
    rotated = people.boss.post(
        "/admin/integration/actions/rotate-secret",
        json={"scope": SCOPE, "definition_id": made.json()["id"]},
    )
    assert rotated.status_code == 200 and rotated.json()["secret"] != secret


def test_a_person_reads_the_registry_and_the_error_queue_is_the_admins(people: People) -> None:
    run(people.boss, "CreateRule", **RULE)
    rows = people.bob.get("/integration/rules").json()
    assert rows["kind"] == "rules" and rows["rows"][0]["key"] == "hse-notify"
    assert rows["rows"][0]["then"][0]["command"] == "PostToFeed"
    assert people.bob.get("/integration/nonsense").status_code == 404
    assert people.bob.get("/integration/deliveries").status_code == 404
    assert people.boss.get("/admin/integration/deliveries").json() == {
        "kind": "deliveries",
        "rows": [],
    }
    assert (
        people.bob.get("/integration/enrichments", params={"state": "proposed"}).json()["rows"]
        == []
    )


def test_a_rule_can_be_dry_run_from_a_stored_id_or_a_draft(people: People) -> None:
    made = run(people.boss, "CreateRule", **RULE).json()
    stored = people.boss.post(
        "/admin/integration/rules/dry-run", json={"rule_id": made["stream_id"]}
    )
    assert stored.status_code == 200 and stored.json()["rule"] == "hse-notify"
    draft = {"key": "draft-one", "title": "Draft", "scope": SCOPE, "when": RULE["when"],
             "then": RULE["then"]}  # fmt: skip
    drafted = people.boss.post("/admin/integration/rules/dry-run", json={"draft": draft})
    assert drafted.status_code == 200 and drafted.json()["rule"] == "draft-one"
    bad = people.boss.post(
        "/admin/integration/rules/dry-run", json={"draft": {**draft, "when": {}}}
    )
    assert bad.status_code == 422
    assert people.boss.post("/admin/integration/rules/dry-run", json={}).status_code == 422
    missing = people.boss.post("/admin/integration/rules/dry-run", json={"rule_id": "nope"})
    assert missing.status_code == 404
