"""Workflow roles over HTTP come from the signed-in account, never from the request (P1-SEC1).

The fixture workflow `core.review` lets only a document controller (or an admin) `issue`. These
tests prove, on every adapter, that a signed-in user cannot pass that guard by claiming a role
(in a command body, in the accept body or in a query), that a person who really holds the role
passes, that the walk of the published API finds no route that takes roles, and that the guard
depends on the derivation (take it away and the controller is refused). ADR-0013, addendum P1-SEC1.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness import SCOPE, Harness
from tl_api.commands import COMMAND_BODIES
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_core.services import proposals
from tl_core.services.workflow import TransitionWorkflow

PASSWORD = "correct horse battery"
AGENT = "agent:triage"
PEOPLE = (
    ("boss", "person", ["admin"]),
    ("dora", "person", ["user", "document_controller"]),
    ("solo", "person", ["document_controller"]),
    ("simdc", "sim", ["user", "document_controller"]),
    ("bob", "person", ["user"]),
)


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


class Cast:
    """Signed-in people with different roles, and records waiting in `Approved`."""

    def __init__(self, harness: Harness) -> None:
        self.harness = harness
        with harness.backend() as uow:
            for name, kind, roles in PEOPLE:
                accounts.create_account(
                    uow, username=name, display_name=name, kind=kind, roles=roles,  # type: ignore[arg-type]
                    password=prepare_password(PASSWORD), by="svc:test",
                )  # fmt: skip
        self.clients = {name: self._client(name) for name, _, _ in PEOPLE}
        self.count = 0

    def _client(self, name: str) -> TestClient:
        _, token = sessions.sign_in(self.harness.backend, username=name, password=PASSWORD)
        client = self.harness.client_for(None)
        client.headers.update({"Authorization": f"Bearer {token}"})
        return client

    def approved(self) -> tuple[str, int]:
        """A new record in `Approved`: ``(record id, version)``; its `issue` is role-guarded."""
        self.count += 1
        record = self.harness.create_record(f"WR-{self.count}A")
        other = self.harness.create_record(f"WR-{self.count}B")
        sid = record.stream_id
        bob = self.clients["bob"]
        link = bob.post(
            "/commands/AddLink",
            json={
                "scope": SCOPE,
                "from_id": sid,
                "to_id": other.stream_id,
                "relation": "references",
            },
        )
        assert link.status_code == 200, link.text
        version = 1
        for transition in ("submit", "approve"):
            done = bob.post("/commands/TransitionWorkflow", json=body(sid, version, transition))
            assert done.status_code == 200, done.text
            version = done.json()["version"]
        return sid, version

    def state(self, record_id: str) -> str:
        found = self.clients["boss"].get(f"/records/{record_id}/workflow").json()
        return str(found["state"])


@pytest.fixture
def cast(harness: Harness) -> Cast:
    return Cast(harness)


def body(sid: str, version: int, transition: str, **extra: Any) -> dict[str, Any]:
    return {
        "scope": SCOPE,
        "stream_id": sid,
        "expected_version": version,
        "transition": transition,
        **extra,
    }


def issue(client: TestClient, sid: str, version: int, **extra: Any) -> Any:
    return client.post("/commands/TransitionWorkflow", json=body(sid, version, "issue", **extra))


# --- a claim does nothing --------------------------------------------------------------------


@pytest.mark.parametrize("claim", [["document_controller"], ["admin"], ["manager"], []])
def test_a_user_cannot_pass_a_roles_guard_by_claiming_a_role(cast: Cast, claim: list[str]) -> None:
    sid, version = cast.approved()
    refused = issue(cast.clients["bob"], sid, version, actor_roles=claim)
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "role_claim_refused"
    assert "document_controller" not in refused.text and "manager" not in refused.text
    assert cast.state(sid) == "Approved"


def test_a_user_without_a_claim_is_blocked_by_the_roles_guard(cast: Cast) -> None:
    sid, version = cast.approved()
    blocked = issue(cast.clients["bob"], sid, version)
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"] == "guard_failed"
    assert "needs one of the roles: document_controller" in blocked.json()["message"]
    assert cast.state(sid) == "Approved"


def test_a_dev_token_is_a_user_and_cannot_issue_either(harness: Harness, cast: Cast) -> None:
    sid, version = cast.approved()
    blocked = issue(harness.client, sid, version)  # user:alice, a dev token
    assert blocked.status_code == 409 and blocked.json()["error"] == "guard_failed"
    claimed = issue(harness.client, sid, version, actor_roles=["document_controller"])
    assert claimed.status_code == 422 and claimed.json()["error"] == "role_claim_refused"


def test_the_status_of_a_record_is_judged_for_the_account_not_the_query(cast: Cast) -> None:
    sid, _ = cast.approved()

    def allowed(client: TestClient, **params: str) -> bool:
        found = client.get(f"/records/{sid}/workflow", params=params)
        assert found.status_code == 200, found.text
        return next(o for o in found.json()["options"] if o["transition"] == "issue")["allowed"]

    assert allowed(cast.clients["bob"]) is False
    assert allowed(cast.clients["bob"], role="document_controller") is False
    assert allowed(cast.clients["dora"]) is True
    assert allowed(cast.clients["dora"], role="nothing") is True


# --- a person who holds the role passes --------------------------------------------------------


@pytest.mark.parametrize("who", ["boss", "dora", "solo", "simdc"])
def test_a_person_who_really_holds_the_role_passes(cast: Cast, who: str) -> None:
    sid, version = cast.approved()
    done = issue(cast.clients[who], sid, version)
    assert done.status_code == 200, done.text
    assert cast.state(sid) == "Issued"
    event = done.json()["events"][0]
    assert event["actor"] == f"user:{who}"
    guards = {g["kind"]: g for g in event["payload"]["guards_evaluated"]}
    assert guards["roles"]["passed"] is True


# --- accepting a proposal uses the accepting person's roles --------------------------------------


def propose_issue(harness: Harness, sid: str, version: int) -> str:
    command = TransitionWorkflow(
        actor=AGENT, source="mcp:triage", scope=SCOPE, stream_id=sid,
        expected_version=version, transition="issue",
    )  # fmt: skip
    made = proposals.submit(
        harness.backend, tool="transition_workflow", agent=AGENT, command=command, summary="Issue"
    )
    assert "actor_roles" not in made.command
    return made.proposal_id


def test_a_user_accepting_a_proposal_cannot_lend_it_a_role(harness: Harness, cast: Cast) -> None:
    sid, version = cast.approved()
    pid = propose_issue(harness, sid, version)
    path = f"/proposals/{pid}/accept"
    refused = cast.clients["bob"].post(path, json={"roles": ["document_controller"]})
    assert refused.status_code == 422 and refused.json()["error"] == "role_claim_refused"
    refused = cast.clients["bob"].post(path, json={"actor_roles": ["document_controller"]})
    assert refused.status_code == 422 and refused.json()["error"] == "role_claim_refused"
    failed = cast.clients["bob"].post(path)
    assert failed.status_code == 200 and failed.json()["status"] == "failed", failed.text
    assert failed.json()["reason"].startswith("GuardFailedError")
    assert cast.state(sid) == "Approved"


def test_a_controller_accepting_a_proposal_brings_her_own_roles(
    harness: Harness, cast: Cast
) -> None:
    sid, version = cast.approved()
    pid = propose_issue(harness, sid, version)
    done = cast.clients["dora"].post(f"/proposals/{pid}/accept")
    assert done.status_code == 200 and done.json()["status"] == "accepted", done.text
    assert cast.state(sid) == "Issued"


# --- the walk of the published API --------------------------------------------------------------


def _properties(schemas: dict[str, Any], node: Any, seen: set[str] | None = None) -> set[str]:
    """Every property name reachable from a schema node, following references."""
    seen = set() if seen is None else seen
    found: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            name = ref.rsplit("/", 1)[-1]
            if name not in seen:
                seen.add(name)
                found |= _properties(schemas, schemas[name], seen)
        found |= set(node.get("properties", {}))
        for value in node.values():
            found |= _properties(schemas, value, seen)
    elif isinstance(node, list):
        for item in node:
            found |= _properties(schemas, item, seen)
    return found


def _written(harness: Harness) -> Iterator[tuple[str, str, set[str]]]:
    spec = harness.app.openapi()
    schemas = spec["components"]["schemas"]
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            content = op.get("requestBody", {}).get("content", {})
            if content:
                yield method, path, _properties(schemas, content)


def test_the_walk_finds_the_bodies_and_none_takes_workflow_roles(harness: Harness) -> None:
    found = list(_written(harness))
    paths = [path for _, path, _ in found]
    assert len(found) > 40 and len(COMMAND_BODIES) > 30
    assert "/commands/TransitionWorkflow" in paths and "/proposals/{proposal_id}/accept" in paths
    assert "/admin/accounts/{account_id}/roles" in paths  # the walk reaches the admin routes
    for method, path, names in found:
        assert "actor_roles" not in names, (method, path)
        if not path.startswith("/admin/"):  # an admin sets account roles; that is not a claim
            assert "roles" not in names, (method, path)


def test_no_read_route_takes_a_role_parameter(harness: Harness) -> None:
    spec = harness.app.openapi()
    checked = 0
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            for parameter in op.get("parameters", []):
                checked += 1
                assert parameter["name"] not in ("role", "roles", "actor_roles"), (method, path)
    assert checked > 50


def test_every_command_route_refuses_actor_roles_with_the_fixed_error(
    harness: Harness, cast: Cast
) -> None:
    """One check in the body model covers each route, so a new route cannot forget it."""
    admin = cast.clients["boss"]
    routes = [
        (method, path)
        for method, path, _ in _written(harness)
        if path.startswith("/commands/") or path in ("/uploads", "/files/attach")
    ]
    assert len(routes) > 30
    for method, path in routes:
        refused = admin.request(method, path, json={"actor_roles": ["admin"]})
        assert refused.status_code == 422, (path, refused.text)
        assert refused.json()["error"] == "role_claim_refused", (path, refused.text)
        assert refused.json()["message"] == (
            "workflow roles cannot be claimed; the server derives them from the signed-in account"
        )


# --- the guard: take the derivation away and the controller is refused ---------------------------


def test_the_derivation_is_what_lets_a_controller_pass(
    cast: Cast, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If `workflow_roles` stopped deriving roles (or an entry point stopped calling it), a real
    controller would be blocked on every route. That is the failure this test pins."""
    import tl_api.commands as commands
    import tl_api.routes.proposals as proposal_routes
    import tl_api.routes.reference as reference

    sid, version = cast.approved()
    for module in (commands, proposal_routes, reference):
        monkeypatch.setattr(module, "workflow_roles", lambda _who: ())
    blocked = issue(cast.clients["boss"], sid, version)
    assert blocked.status_code == 409 and blocked.json()["error"] == "guard_failed"
    status = cast.clients["boss"].get(f"/records/{sid}/workflow").json()
    assert next(o for o in status["options"] if o["transition"] == "issue")["allowed"] is False
    monkeypatch.undo()
    assert issue(cast.clients["boss"], sid, version).status_code == 200
