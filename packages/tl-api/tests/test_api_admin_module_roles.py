"""The module role admin routes (RM-S3.md "Routes and actions") and ``GET /auth/me/roles``.

Five routes: grant (201) and revoke, the list of explicit grants, the effective roles of an account
on a project, and the caller's own roles. The four admin routes are for an active human admin; the
fifth answers any signed-in caller, bound to the principal (it takes no account id). Runs on every
adapter. Expectations come from the role table and the spec, never from the code under test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from harness import Harness
from tl_api.tokens import add_token
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_core.modules import load_modules

PASSWORD = "correct horse battery"
P1, P2 = "project:P1", "project:P2"
TABLE = yaml.safe_load(
    (Path(__file__).resolve().parents[3] / "schema" / "settings" / "module-roles.yaml").read_text(
        encoding="utf-8"
    )
)
MODULES = [spec.name for spec in load_modules()]


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


class Cast:
    def __init__(self, harness: Harness) -> None:
        self.harness = harness
        self.clients: dict[str, TestClient] = {}
        self.ids: dict[str, str] = {}
        for name, roles, kind in (
            ("ada", ("admin",), "person"),
            ("uma", ("user",), "person"),
            ("dora", ("user", "document_controller"), "person"),
            ("triage", ("user",), "agent"),
        ):
            self.person(name, roles, kind)
        token = add_token(harness.settings.tokens_path, "agent:triage")
        self.clients["agent:triage"] = self._client(token)

    def _client(self, token: str) -> TestClient:
        client = self.harness.client_for(None)
        client.headers.update({"Authorization": f"Bearer {token}"})
        return client

    def person(self, name: str, roles: tuple[str, ...], kind: str = "person") -> None:
        password = None if kind == "agent" else prepare_password(PASSWORD, username=name)
        with self.harness.backend() as uow:
            view = accounts.create_account(
                uow, username=name, display_name=name.title(), kind=kind,  # type: ignore[arg-type]
                roles=list(roles), password=password, by="svc:test",
            )  # fmt: skip
        self.ids[name] = view.account_id
        if kind != "agent":
            _, token = sessions.sign_in(self.harness.backend, username=name, password=PASSWORD)
            self.clients[name] = self._client(token)

    def url(self, who: str) -> str:
        return f"/admin/accounts/{self.ids[who]}/module-roles"

    @staticmethod
    def body(role: str, module: str = "documents", project: str = P1) -> dict[str, str]:
        return {"project": project, "module": module, "role": role, "reason": "test"}


@pytest.fixture
def cast(harness: Harness) -> Cast:
    return Cast(harness)


def code(response) -> str:  # type: ignore[no-untyped-def]
    return str(response.json()["error"])


# --- grant and revoke --------------------------------------------------------------------------


def test_a_grant_answers_201_changed_true_and_a_repeat_changed_false(cast: Cast) -> None:
    ada = cast.clients["ada"]
    first = ada.post(cast.url("uma"), json=cast.body("superuser"))
    assert first.status_code == 201 and first.json()["changed"] is True, first.text
    again = ada.post(cast.url("uma"), json=cast.body("superuser"))
    assert again.status_code == 201 and again.json()["changed"] is False, again.text


def test_a_revoke_answers_200_and_a_second_revoke_is_404_no_such_grant(cast: Cast) -> None:
    ada = cast.clients["ada"]
    ada.post(cast.url("uma"), json=cast.body("superuser"))
    done = ada.post(f"{cast.url('uma')}/revoke", json=cast.body("superuser"))
    assert done.status_code == 200 and done.json()["changed"] is True, done.text
    gone = ada.post(f"{cast.url('uma')}/revoke", json=cast.body("superuser"))
    assert gone.status_code == 404 and code(gone) == "no_such_grant", gone.text


def test_an_unknown_role_is_422_unknown_role(cast: Cast) -> None:
    response = cast.clients["ada"].post(cast.url("uma"), json=cast.body("overlord"))
    assert response.status_code == 422 and code(response) == "unknown_role", response.text


def test_an_unknown_module_is_422_unknown_module(cast: Cast) -> None:
    response = cast.clients["ada"].post(cast.url("uma"), json=cast.body("user", module="nowhere"))
    assert response.status_code == 422 and code(response) == "unknown_module", response.text


def test_a_company_grant_for_a_module_without_company_roles_is_422_no_company_roles(
    cast: Cast,
) -> None:
    assert not next(s for s in load_modules() if s.name == "documents").company_roles
    response = cast.clients["ada"].post(cast.url("uma"), json=cast.body("user", project="company"))
    assert response.status_code == 422 and code(response) == "no_company_roles", response.text


def test_an_agent_account_cannot_be_granted_superuser(cast: Cast) -> None:
    ada = cast.clients["ada"]
    refused = ada.post(cast.url("triage"), json=cast.body("superuser"))
    assert refused.status_code == 422 and code(refused) == "invalid_account", refused.text
    assert ada.post(cast.url("triage"), json=cast.body("user")).status_code == 201


def test_an_unknown_account_is_404(cast: Cast) -> None:
    response = cast.clients["ada"].post(
        "/admin/accounts/NOSUCH/module-roles", json=cast.body("user")
    )
    assert response.status_code == 404 and code(response) == "account_not_found"


def test_a_project_that_is_not_a_project_scope_is_a_422(cast: Cast) -> None:
    ada = cast.clients["ada"]
    assert ada.post(cast.url("uma"), json=cast.body("user", project="P1")).status_code == 422
    assert ada.get("/admin/module-roles", params={"project": "P1"}).status_code == 422


def test_a_missing_reason_is_a_422_and_writes_nothing(cast: Cast) -> None:
    ada = cast.clients["ada"]
    bad = {"project": P1, "module": "documents", "role": "user"}
    assert ada.post(cast.url("uma"), json=bad).status_code == 422
    assert ada.get("/admin/module-roles").json() == []


@pytest.mark.parametrize("who", ["uma", "dora", "agent:triage"])
def test_every_admin_route_is_403_for_a_plain_user_a_controller_and_an_agent(
    cast: Cast, who: str
) -> None:
    client = cast.clients[who]
    url = cast.url("uma")
    assert client.post(url, json=cast.body("user")).status_code == 403
    assert client.post(f"{url}/revoke", json=cast.body("user")).status_code == 403
    assert client.get("/admin/module-roles").status_code == 403
    path = f"/admin/accounts/{cast.ids['uma']}/effective-roles"
    assert client.get(path, params={"project": P1}).status_code == 403
    assert cast.clients["ada"].get("/admin/module-roles").json() == []  # nothing was written


def test_a_refused_caller_changes_no_grant(cast: Cast) -> None:
    cast.clients["uma"].post(cast.url("uma"), json=cast.body("superuser"))
    rows = cast.clients["ada"].get("/admin/module-roles").json()
    assert rows == []
    effective = cast.clients["uma"].get("/auth/me/roles", params={"project": P1}).json()
    assert all(v["roles"] == ["user"] for v in effective)


# --- the list and the effective roles -----------------------------------------------------------


def test_the_list_filters_by_project_module_and_account(cast: Cast) -> None:
    ada = cast.clients["ada"]
    for who, project, module, role in (
        ("uma", P1, "documents", "viewer"),
        ("uma", P2, "schedule", "superuser"),
        ("dora", P1, "documents", "user"),
    ):
        assert ada.post(cast.url(who), json=cast.body(role, module, project)).status_code == 201
    everything = ada.get("/admin/module-roles").json()
    assert len(everything) == 3
    assert set(everything[0]) == {
        "account_id", "username", "project", "module", "role", "granted_by", "granted_at",
    }  # fmt: skip
    by_project = ada.get("/admin/module-roles", params={"project": P1}).json()
    assert [(g["username"], g["project"]) for g in by_project] == [("dora", P1), ("uma", P1)]
    by_module = ada.get("/admin/module-roles", params={"module": "schedule"}).json()
    assert [(g["username"], g["module"]) for g in by_module] == [("uma", "schedule")]
    by_account = ada.get("/admin/module-roles", params={"account_id": cast.ids["dora"]}).json()
    assert [(g["username"], g["role"]) for g in by_account] == [("dora", "user")]
    both = ada.get("/admin/module-roles", params={"project": P1, "module": "documents"}).json()
    assert len(both) == 2
    assert {g["granted_by"] for g in everything} == {"user:ada"}


def test_a_revoked_grant_leaves_the_list(cast: Cast) -> None:
    ada = cast.clients["ada"]
    ada.post(cast.url("uma"), json=cast.body("viewer"))
    ada.post(f"{cast.url('uma')}/revoke", json=cast.body("viewer"))
    assert ada.get("/admin/module-roles").json() == []


def test_effective_roles_list_every_loaded_module_with_the_resolvers_source(cast: Cast) -> None:
    ada = cast.clients["ada"]
    ada.post(cast.url("uma"), json=cast.body("viewer"))
    ada.post(cast.url("uma"), json=cast.body("superuser", "schedule", P2))
    path = f"/admin/accounts/{cast.ids['uma']}/effective-roles"
    views = ada.get(path, params={"project": P1}).json()
    assert [v["module"] for v in views] == MODULES
    assert set(views[0]) == {"module", "roles", "source"}
    by_name = {v["module"]: v for v in views}
    assert by_name["documents"] == {"module": "documents", "roles": ["viewer"], "source": "granted"}
    assert by_name["cost"] == {"module": "cost", "roles": ["user"], "source": "derived"}
    other = ada.get(path, params={"project": P2}).json()
    assert {v["module"]: v["source"] for v in other}["schedule"] == "granted"
    assert {v["module"]: v["source"] for v in other}["documents"] == "derived"


def test_an_admin_account_holds_every_role_with_the_admin_source(cast: Cast) -> None:
    path = f"/admin/accounts/{cast.ids['ada']}/effective-roles"
    views = cast.clients["ada"].get(path, params={"project": P1}).json()
    assert {v["source"] for v in views} == {"admin"}
    assert all(v["roles"] == list(TABLE["roles"]) for v in views)


# --- /auth/me/roles -----------------------------------------------------------------------------


def test_my_roles_are_derived_for_a_plain_user_in_every_module(cast: Cast) -> None:
    mine = cast.clients["uma"].get("/auth/me/roles", params={"project": P1})
    assert mine.status_code == 200, mine.text
    assert {v["module"]: (v["roles"], v["source"]) for v in mine.json()} == {
        m: (["user"], "derived") for m in MODULES
    }


def test_a_document_controller_reads_superuser_in_three_modules(cast: Cast) -> None:
    views = cast.clients["dora"].get("/auth/me/roles", params={"project": P1}).json()
    superuser = {v["module"] for v in views if "superuser" in v["roles"]}
    assert superuser == {"documents", "correspondence", "schedule"}


def test_my_roles_follow_a_grant_on_that_project_only(cast: Cast) -> None:
    cast.clients["ada"].post(cast.url("uma"), json=cast.body("viewer"))
    p1 = cast.clients["uma"].get("/auth/me/roles", params={"project": P1}).json()
    p2 = cast.clients["uma"].get("/auth/me/roles", params={"project": P2}).json()
    assert {v["module"]: v["roles"] for v in p1}["documents"] == ["viewer"]
    assert {v["module"]: v["roles"] for v in p2}["documents"] == ["user"]


def test_my_roles_are_bound_to_the_principal_and_take_no_account_id(cast: Cast) -> None:
    ada = cast.clients["ada"]
    ada.post(cast.url("dora"), json=cast.body("viewer"))
    uma = cast.clients["uma"]
    spoofed = uma.get(
        "/auth/me/roles", params={"project": P1, "account_id": cast.ids["dora"]}
    ).json()
    assert {v["module"]: v["roles"] for v in spoofed}["documents"] == ["user"]  # uma's own
    assert uma.get("/auth/me/roles").status_code == 422  # the project is required
    other_path = f"/auth/me/roles/{cast.ids['dora']}"
    assert uma.get(other_path, params={"project": P1}).status_code in (404, 405)


def test_an_agent_may_read_its_own_roles_and_not_the_admin_routes(cast: Cast) -> None:
    agent = cast.clients["agent:triage"]
    assert agent.get("/auth/me/roles", params={"project": P1}).status_code == 200
    assert agent.get("/admin/module-roles").status_code == 403


def test_a_caller_with_no_token_is_401_on_every_route(harness: Harness, cast: Cast) -> None:
    anon = harness.client_for(None)
    assert anon.get("/auth/me/roles", params={"project": P1}).status_code == 401
    assert anon.get("/admin/module-roles").status_code == 401
    assert anon.post(cast.url("uma"), json=cast.body("user")).status_code == 401


# --- the events ---------------------------------------------------------------------------------


def types_of(client: TestClient) -> set[str]:
    body = client.get("/events", params={"limit": 1000}).json()
    return {e["event_type"] for e in body["events"]}


def test_an_admin_sees_the_grant_events_in_events_and_a_plain_user_sees_no_account_event(
    cast: Cast,
) -> None:
    ada = cast.clients["ada"]
    ada.post(cast.url("uma"), json=cast.body("superuser"))
    ada.post(f"{cast.url('uma')}/revoke", json=cast.body("superuser"))
    admin_types = types_of(ada)
    assert {"Account.ModuleRoleGranted", "Account.ModuleRoleRevoked"} <= admin_types
    for who in ("uma", "dora", "agent:triage"):
        seen = types_of(cast.clients[who])
        assert not {t for t in seen if t.startswith("Account.")}, (who, seen)
