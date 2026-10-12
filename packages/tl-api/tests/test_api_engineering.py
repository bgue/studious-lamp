"""The engineering commands over HTTP: who may run them, and how their failures are answered."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness import Harness
from tl_api.client import ApiClient
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_mod_engineering.errors import InvalidTagNumberError
from tl_mod_engineering.testing import seed_registry

PASSWORD = "correct horse battery"
EDITION = "co.acme.standards@1.0.0"
PROJECT = "project:P123"


class People:
    """An admin (`boss`) and an ordinary person (`bob`), each with a session on the harness."""

    def __init__(self, harness: Harness) -> None:
        with harness.backend() as uow:
            for name, roles in (("boss", ["admin"]), ("bob", ["user"])):
                accounts.create_account(
                    uow, username=name, display_name=name, kind="person", roles=roles,
                    password=prepare_password(PASSWORD), by="svc:test",
                )  # fmt: skip
        self.boss = self._client(harness, "boss")
        self.bob = self._client(harness, "bob")

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
    return client.post(f"/commands/{name}", json={"scope": "company", **body})


def register_area(client: TestClient) -> Any:
    return run(
        client,
        "RegisterCodeList",
        code="Area",
        label="Area",
        edition=EDITION,
        value_list_policy="extensible",
    )


def test_an_admin_runs_the_registry_commands_and_the_result_is_the_usual_one(
    people: People,
) -> None:
    made = register_area(people.boss)
    assert made.status_code == 200, made.text
    assert made.json()["key"] == "CL:Area@1.0.0" and made.json()["version"] == 2
    value = run(people.boss, "AddCodeValue", code_list="Area", code="47", label="Unit 47")
    assert value.status_code == 200 and value.json()["key"] == "CV:Area.47@1.0.0"


def test_a_person_without_the_admin_role_is_refused_the_registry(people: People) -> None:
    refused = register_area(people.bob)
    assert refused.status_code == 403 and refused.json()["error"] == "forbidden"
    assert "admin.command.RegisterCodeList" in refused.json()["message"]
    assert (
        run(
            people.bob, "DefineTagClass", code="X", label="X", family="valve", edition=EDITION
        ).status_code
        == 403
    )
    assert register_area(people.boss).status_code == 200


def test_a_company_value_needs_an_admin_and_a_project_value_does_not(people: People) -> None:
    register_area(people.boss)
    run(people.boss, "AddCodeValue", code_list="Area", code="47", label="Unit 47")
    company = run(people.bob, "AddCodeValue", code_list="Area", code="48", label="Unit 48")
    assert company.status_code == 403 and company.json()["error"] == "forbidden"
    own = people.bob.post(
        "/commands/AddCodeValue",
        json={
            "scope": PROJECT,
            "code_list": "Area",
            "code": "T1",
            "label": "Temporary",
            "crosswalk": "47",
        },
    )
    assert own.status_code == 200, own.text
    no_map = people.bob.post(
        "/commands/AddCodeValue",
        json={"scope": PROJECT, "code_list": "Area", "code": "T2", "label": "No map"},
    )
    assert no_map.status_code == 422 and no_map.json()["error"] == "crosswalk_required"


def test_the_body_never_carries_the_actor(people: People) -> None:
    refused = run(
        people.boss,
        "RegisterCodeList",
        code="Area",
        label="Area",
        edition=EDITION,
        actor="user:someone",
    )
    assert refused.status_code == 422 and refused.json()["error"] == "validation_error"


def test_a_person_creates_and_renames_a_tag_and_a_bad_number_is_a_422_with_every_problem(
    harness: Harness, people: People
) -> None:
    seed_registry(harness.db)
    made = people.bob.post(
        "/commands/CreateTag",
        json={"scope": PROJECT, "number": "47-FV-1001", "class_code": "ControlValve"},
    )
    assert made.status_code == 200, made.text
    bad = people.bob.post("/commands/CreateTag", json={"scope": PROJECT, "number": "47-XX-1"})
    assert bad.status_code == 422 and bad.json()["error"] == "invalid_tag_number"
    issues = bad.json()["issues"]
    assert {i["segment"] for i in issues} >= {"mnemonic", "seq"}
    renamed = people.bob.post(
        "/commands/RenameTag",
        json={
            "scope": PROJECT,
            "stream_id": made.json()["stream_id"],
            "new_number": "47-FV-1002",
            "reason": "renumbered",
        },
    )
    assert renamed.status_code == 200 and renamed.json()["key"] == "47-FV-1002"
    missing = people.bob.post(
        "/commands/ReclassifyTag",
        json={"scope": PROJECT, "stream_id": "nope", "class_code": "ManualValve", "reason": "r"},
    )
    assert missing.status_code == 404 and missing.json()["error"] == "tag_not_found"


def test_the_client_rebuilds_the_module_error_with_its_issues(
    harness: Harness, people: People
) -> None:
    seed_registry(harness.db)
    bad = people.bob.post("/commands/CreateTag", json={"scope": PROJECT, "number": "47-XX-1"})
    rebuilt = ApiClient.error_from(bad)  # type: ignore[arg-type]
    assert isinstance(rebuilt, InvalidTagNumberError)
    assert {i["segment"] for i in rebuilt.issues} >= {"mnemonic", "seq"}
