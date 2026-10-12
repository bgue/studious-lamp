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


# --- the security review of the HTTP commands (P1-I1) -----------------------------------------


@pytest.fixture
def agent(harness: Harness) -> TestClient:
    from datetime import UTC, datetime, timedelta

    with harness.backend() as uow:
        bot = accounts.create_account(
            uow, username="triage", display_name="Triage", kind="agent", roles=["user"],
            password=None, by="svc:test",
        )  # fmt: skip
        _, token = accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="t",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    client = harness.client_for(None)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def define_class(people: People) -> str:
    made = run(
        people.boss,
        "DefineTagClass",
        code="Pump",
        label="Pump",
        family="pump",
        edition=EDITION,
        definition="A pump.",
    )
    assert made.status_code == 200, made.text
    return str(made.json()["stream_id"])


def test_a_person_cannot_change_a_registry_record_through_the_generic_commands(
    people: People,
) -> None:
    """The repro of the review: UpdateRecord on a tag class and on a code list."""
    class_id = define_class(people)
    listed = register_area(people.boss)
    assert listed.status_code == 200
    for stream_id in (class_id, str(listed.json()["stream_id"])):
        refused = run(
            people.bob,
            "UpdateRecord",
            stream_id=stream_id,
            expected_version=2,
            changes={"description": "user-edited", "title": "hijacked"},
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"] == "unsupported_record_type"
        assert "UpdateRecord cannot change a engineering." in refused.json()["message"]
        for name, body in (
            ("SetPsetValues", {"pset": "valve_data", "layer": "standard", "values": {"a": 1}}),
            ("TransitionWorkflow", {"transition": "submit"}),
        ):
            other = run(people.bob, name, stream_id=stream_id, expected_version=2, **body)
            assert other.status_code == 422 and other.json()["error"] == "unsupported_record_type"
        link = run(people.bob, "AddLink", from_id=stream_id, to_id=class_id)
        assert link.status_code == 422 and link.json()["error"] == "unsupported_record_type"
    # an admin does not get the generic commands either: the registry has its own
    admin = run(
        people.boss, "UpdateRecord", stream_id=class_id, expected_version=2, changes={"title": "x"}
    )
    assert admin.status_code == 422 and admin.json()["error"] == "unsupported_record_type"


def test_origin_and_pattern_policy_are_not_in_the_request(harness: Harness, people: People) -> None:
    seed_registry(harness.db)
    for extra in ({"origin": "import"}, {"pattern_policy": "record"}):
        refused = people.bob.post(
            "/commands/CreateTag", json={"scope": PROJECT, "number": "LEGACY-1", **extra}
        )
        assert refused.status_code == 422 and refused.json()["error"] == "validation_error"
    plain = people.bob.post("/commands/CreateTag", json={"scope": PROJECT, "number": "LEGACY-1"})
    assert plain.status_code == 422 and plain.json()["error"] == "invalid_tag_number"


def test_only_an_admin_can_record_a_number_that_breaks_the_pattern(
    harness: Harness, people: People
) -> None:
    seed_registry(harness.db)
    body = {"scope": PROJECT, "number": "LEGACY-1"}
    assert people.bob.post("/commands/RecordTag", json=body).status_code == 403
    done = people.boss.post("/commands/RecordTag", json=body)
    assert done.status_code == 200, done.text
    assert done.json()["key"] == "LEGACY-1"
    with harness.backend(True) as uow:
        from tl_mod_engineering import registry

        row = registry.find_tag(uow.conn(), PROJECT, "LEGACY-1")
    assert row is not None and (row.number_status, row.origin) == ("violation", "created")


def test_a_user_is_refused_every_registry_command_and_an_agent_every_command(
    people: People, agent: TestClient
) -> None:
    class_id = define_class(people)
    registry_commands: dict[str, dict[str, Any]] = {
        "RegisterCodeList": {"code": "X", "label": "X", "edition": EDITION},
        "RegisterMnemonic": {"code": "XX", "label": "X", "edition": EDITION},
        "RegisterNumberingPattern": {
            "code": "p",
            "label": "p",
            "edition": EDITION,
            "record_type": "engineering.Tag",
            "template": "{seq:4}",
            "segments": {"seq": {"role": "sequence"}},
        },
        "CloseStandard": {"stream_id": "x", "reason": "r"},
        "DefineTagClass": {"code": "Y", "label": "Y", "family": "pump", "edition": EDITION},
        "ReviseTagClass": {"stream_id": class_id, "changes": {"label": "Z"}, "reason": "r"},
        "CloseTagClass": {"stream_id": class_id, "reason": "r"},
    }
    for name, body in registry_commands.items():
        refused = run(people.bob, name, **body)
        assert refused.status_code == 403 and refused.json()["error"] == "forbidden", name
        assert f"admin.command.{name}" in refused.json()["message"]
    everything: dict[str, dict[str, Any]] = {
        **registry_commands,
        "AddCodeValue": {"code_list": "Area", "code": "1", "label": "One"},
        "CloseCodeValue": {"stream_id": "x", "reason": "r"},
        "CreateTag": {"number": "47-FV-1001"},
        "RecordTag": {"number": "LEGACY-1"},
        "ReclassifyTag": {"stream_id": "x", "class_code": "Pump", "reason": "r"},
        "RenameTag": {"stream_id": "x", "new_number": "47-FV-1002", "reason": "r"},
        "MergeTags": {"stream_ids": ["a", "b"], "new_number": "47-FV-1003", "reason": "r"},
    }
    for name, body in everything.items():
        scope = (
            PROJECT if name in ("CreateTag", "RecordTag", "RenameTag", "MergeTags") else "company"
        )
        refused = agent.post(f"/commands/{name}", json={"scope": scope, **body})
        assert refused.status_code == 403, (name, refused.text)
        assert refused.json()["error"] == "agent_must_propose", name


def test_the_access_of_every_engineering_command_is_pinned() -> None:
    from tl_mod_engineering.commands import API_COMMANDS

    assert {c.model.__name__: c.access for c in API_COMMANDS} == {
        "RegisterCodeList": "admin",
        "RegisterMnemonic": "admin",
        "RegisterNumberingPattern": "admin",
        "CloseStandard": "admin",
        "AddCodeValue": "company",
        "CloseCodeValue": "company",
        "DefineTagClass": "admin",
        "ReviseTagClass": "admin",
        "CloseTagClass": "admin",
        "CreateTag": "user",
        "RecordTag": "admin",
        "ReclassifyTag": "user",
        "RenameTag": "user",
        "MergeTags": "user",
    }


def test_a_command_body_over_the_limit_is_a_413_before_it_is_parsed(people: People) -> None:
    big = {"scope": PROJECT, "number": "47-FV-1001", "service": "x" * (2 * 1024 * 1024)}
    refused = people.bob.post("/commands/CreateTag", json=big)
    assert refused.status_code == 413 and refused.json()["error"] == "payload_too_large"
    ids = [f"{n:026d}" for n in range(200_000)]
    huge = people.bob.post(
        "/commands/MergeTags",
        json={"scope": PROJECT, "stream_ids": ids, "new_number": "47-FV-1003", "reason": "r"},
    )
    assert huge.status_code == 413
    small = people.bob.post("/commands/CreateTag", json={"scope": PROJECT, "number": "x"})
    assert small.status_code != 413


def test_the_lists_and_mappings_of_a_command_are_bounded(people: People) -> None:
    too_many = people.bob.post(
        "/commands/MergeTags",
        json={
            "scope": PROJECT,
            "stream_ids": [f"id{n}" for n in range(501)],
            "new_number": "47-FV-1003",
            "reason": "r",
        },
    )
    assert too_many.status_code == 422 and "at most 500" in too_many.json()["message"]
    psets = people.bob.post(
        "/commands/CreateTag",
        json={"scope": PROJECT, "number": "47-FV-1001", "psets": {f"p{n}": {} for n in range(51)}},
    )
    assert psets.status_code == 422 and "at most 50" in psets.json()["message"]
    wide = people.bob.post(
        "/commands/CreateTag",
        json={
            "scope": PROJECT,
            "number": "47-FV-1001",
            "psets": {"valve_data": {f"k{n}": 1 for n in range(201)}},
        },
    )
    assert wide.status_code == 422 and "200 properties" in wide.json()["message"]
    attrs = run(
        people.boss,
        "AddCodeValue",
        code_list="Area",
        code="1",
        label="One",
        attributes={f"k{n}": 1 for n in range(201)},
    )
    assert attrs.status_code == 422 and "at most 200" in attrs.json()["message"]
    segments = run(
        people.boss,
        "RegisterNumberingPattern",
        code="p",
        label="p",
        edition=EDITION,
        record_type="engineering.Tag",
        template="{seq:4}",
        segments={f"s{n}": {"role": "other"} for n in range(21)},
    )
    assert segments.status_code == 422 and "at most 20" in segments.json()["message"]
