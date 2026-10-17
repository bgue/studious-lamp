"""A client cannot pose as a publication: reserved correlation ids and sources (ADR-0014)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from harness import SCOPE, Harness
from tl_api.commands import COMMAND_BODIES
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_core.services import proposals
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import ReservedIdentifierError

BODY = {"scope": SCOPE, "number": "ISO-9001", "title": "A document"}


@pytest.mark.parametrize(
    "extra",
    [
        {"correlation_id": "derive:01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"},
        {"causation_id": "derive:anything"},
        {"source": "import:derived-01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"},
        {"source": "compensation:01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"},
    ],
)
def test_a_client_command_with_a_reserved_identifier_is_refused_and_writes_nothing(
    harness: Harness, extra: dict[str, str]
) -> None:
    refused = harness.client.post("/commands/RegisterDocument", json={**BODY, **extra})
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "reserved_identifier"
    listed = harness.client.get("/projects/P123/documents").json()
    assert listed == []


def test_ordinary_identifiers_still_pass(harness: Harness) -> None:
    ok = harness.client.post(
        "/commands/RegisterDocument",
        json={**BODY, "correlation_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB", "source": "tui"},
    )
    assert ok.status_code == 200, ok.text


def test_a_proposal_cannot_carry_one_either(harness: Harness) -> None:
    command = CreateRecord(
        actor="agent:triage",
        source="mcp:triage",
        scope=SCOPE,
        correlation_id="derive:x",
        record_type="core.Record",
        title="t",
        key="P123-REC-1",
    )
    with pytest.raises(ReservedIdentifierError):
        proposals.submit(
            harness.backend,
            tool="create_record",
            agent="agent:triage",
            command=command,
            summary="s",
        )


RESERVED_VALUES = [
    {"correlation_id": "derive:01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"},
    {"causation_id": "derive:anything"},
    {"source": "import:derived-01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"},
    {"source": "compensation:01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"},
]


def _admin(harness: Harness) -> TestClient:
    """An admin session: the body is checked after the access, so the walk must pass the access."""
    with harness.backend() as uow:
        accounts.create_account(
            uow, username="boss", display_name="boss", kind="person", roles=["admin"],
            password=prepare_password("correct horse battery"), by="svc:test",
        )  # fmt: skip
    _, token = sessions.sign_in(harness.backend, username="boss", password="correct horse battery")
    client = harness.client_for(None)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _body_routes(harness: Harness) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Walk the published API: (routes whose body is a command's model, routes with a ``source``).

    The first list is every POST/PUT whose request body is one ``request_model`` made. The second
    is every route whose body *looks like* a command (it has a ``source`` field), so a route that
    builds its own body model instead of using ``request_model`` shows up as a difference.
    """
    spec = harness.app.openapi()
    schemas = spec["components"]["schemas"]
    command: list[tuple[str, str]] = []
    sourced: list[tuple[str, str]] = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            content = op.get("requestBody", {}).get("content", {}).get("application/json")
            if content is None or "$ref" not in content.get("schema", {}):
                continue
            name = content["schema"]["$ref"].rsplit("/", 1)[-1]
            if name in COMMAND_BODIES or name.replace("-Input", "") in COMMAND_BODIES:
                command.append((method, path))
            if "source" in schemas[name].get("properties", {}):
                sourced.append((method, path))
    return command, sourced


def test_the_walk_finds_the_command_routes_and_the_upload_routes(harness: Harness) -> None:
    command, sourced = _body_routes(harness)
    paths = [p for _, p in command]
    assert "/uploads" in paths
    assert "/files/attach" in paths
    assert "/commands/RegisterDocument" in paths
    assert len(paths) > 30
    assert sorted(sourced) == sorted(command), "a route builds its own command body"


@pytest.mark.parametrize("extra", RESERVED_VALUES)
def test_every_route_with_a_command_body_refuses_a_reserved_value(
    harness: Harness, extra: dict[str, str]
) -> None:
    """One check in the body model covers each route, and a new route cannot forget it."""
    command, _ = _body_routes(harness)
    admin = _admin(harness)
    for method, path in command:
        refused = admin.request(method, path, json=extra)
        assert refused.status_code == 422, (path, refused.text)
        assert refused.json()["error"] == "reserved_identifier", (path, refused.text)


def test_the_upload_routes_refuse_a_full_valid_body_with_a_reserved_source(
    harness: Harness,
) -> None:
    body = {
        "scope": SCOPE,
        "record_id": "R",
        "slot": "native",
        "filename": "a.txt",
        "content_type": "text/plain",
        "sha256": "0" * 64,
        "size": 1,
        "source": "compensation:x",
    }
    for path in ("/uploads", "/files/attach"):
        refused = harness.client.post(path, json=body)
        assert refused.status_code == 422, (path, refused.text)
        assert refused.json()["error"] == "reserved_identifier"
