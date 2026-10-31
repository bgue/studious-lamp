"""The Phase 2 reserved identifiers (W0-B1, contracts section 7).

A correlation or causation id that starts with ``ready:``, ``rollup:`` or ``progress:`` and an event
source that starts with ``job:`` belong to the server's jobs. A client command that carries one is
refused at the body-model check (once, for every route that takes a command body) and the API
answers 422 ``reserved_identifier``.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

_API_TESTS = str(Path(__file__).resolve().parents[2] / "packages" / "tl-api" / "tests")
if _API_TESTS not in sys.path:
    sys.path.insert(1, _API_TESTS)

from fastapi.testclient import TestClient  # noqa: E402
from harness import SCOPE, Harness  # noqa: E402
from tl_api.commands import COMMAND_BODIES  # noqa: E402
from tl_core.auth import accounts, sessions  # noqa: E402
from tl_core.auth.password import prepare_password  # noqa: E402
from tl_core.services.commands import Command  # noqa: E402
from tl_core.services.errors import ReservedIdentifierError  # noqa: E402
from tl_core.services.reserved import (  # noqa: E402
    PHASE2_CORRELATION_PREFIXES,
    PHASE2_SOURCE_PREFIXES,
    RESERVED_CORRELATION_PREFIXES,
    RESERVED_SOURCE_PREFIXES,
    refuse_reserved,
    refuse_reserved_fields,
)

ULID = "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"
PASSWORD = "correct horse battery"
CORRELATION = ("ready:", "rollup:", "progress:")
SOURCES = ("job:awp.readiness", "job:awp.rollup", "job:scaffold.inspections_due", "job:x")
RESERVED_BODIES: list[dict[str, str]] = [
    *({"correlation_id": f"{prefix}{ULID}"} for prefix in CORRELATION),
    *({"causation_id": f"{prefix}{ULID}"} for prefix in CORRELATION),
    *({"source": source} for source in SOURCES),
]


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    built = Harness.build(tmp_path)
    try:
        yield built
    finally:
        built.close()


def test_the_phase_2_prefixes_are_the_contract_ones_and_are_in_the_public_tuples() -> None:
    assert PHASE2_CORRELATION_PREFIXES == CORRELATION
    assert PHASE2_SOURCE_PREFIXES == ("job:",)
    assert set(CORRELATION) <= set(RESERVED_CORRELATION_PREFIXES)
    assert "job:" in RESERVED_SOURCE_PREFIXES
    # the earlier prefixes stay
    assert {"derive:", "load:"} <= set(RESERVED_CORRELATION_PREFIXES)
    assert {"svc:", "compensation:", "legacy:"} <= set(RESERVED_SOURCE_PREFIXES)


@pytest.mark.parametrize("prefix", CORRELATION)
@pytest.mark.parametrize("field", ["correlation_id", "causation_id"])
def test_a_reserved_correlation_or_causation_id_is_refused(prefix: str, field: str) -> None:
    with pytest.raises(ReservedIdentifierError, match=field):
        refuse_reserved_fields(**{field: f"{prefix}{ULID}"})


@pytest.mark.parametrize("source", SOURCES)
def test_a_job_source_is_refused(source: str) -> None:
    with pytest.raises(ReservedIdentifierError, match="source"):
        refuse_reserved_fields(source=source)


def test_the_refusal_names_the_new_prefixes() -> None:
    with pytest.raises(ReservedIdentifierError) as caught:
        refuse_reserved_fields(correlation_id="ready:1")
    assert "'ready:'" in str(caught.value) and "'rollup:'" in str(caught.value)
    assert "'progress:'" in str(caught.value)
    with pytest.raises(ReservedIdentifierError) as caught:
        refuse_reserved_fields(source="job:x")
    assert "'job:'" in str(caught.value)


@pytest.mark.parametrize(
    "fields",
    [
        {"correlation_id": ULID},
        {"correlation_id": "ready"},  # no colon: not the prefix
        {"correlation_id": "xready:1"},  # the prefix must be at the start
        {"correlation_id": "Ready:1"},
        {"causation_id": "progress"},
        {"source": "job"},
        {"source": "jobs:x"},
        {"source": "x-job:y"},
        {"source": "tui"},
    ],
)
def test_ordinary_and_near_miss_identifiers_pass(fields: dict[str, str]) -> None:
    refuse_reserved_fields(**fields)


def test_a_command_carrying_one_is_refused() -> None:
    carrying = [
        Command(actor="user:u", source="test", scope=SCOPE, correlation_id=f"rollup:{ULID}"),
        Command(actor="user:u", source="test", scope=SCOPE, causation_id=f"ready:{ULID}"),
        Command(actor="user:u", source="job:awp.readiness", scope=SCOPE),
    ]
    for command in carrying:
        with pytest.raises(ReservedIdentifierError):
            refuse_reserved(command)
    refuse_reserved(Command(actor="user:u", source="test", scope=SCOPE, correlation_id=ULID))


@pytest.mark.parametrize("extra", RESERVED_BODIES)
def test_every_body_model_refuses_a_reserved_value(extra: dict[str, str]) -> None:
    assert len(COMMAND_BODIES) > 30
    for name, body in COMMAND_BODIES.items():
        with pytest.raises(ReservedIdentifierError):
            body.model_validate(extra)
        assert name.endswith("Body")


def _admin(harness: Harness) -> TestClient:
    with harness.backend() as uow:
        accounts.create_account(
            uow, username="boss", display_name="boss", kind="person", roles=["admin"],
            password=prepare_password(PASSWORD), by="svc:test",
        )  # fmt: skip
    _, token = sessions.sign_in(harness.backend, username="boss", password=PASSWORD)
    client = harness.client_for(None)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _command_routes(harness: Harness) -> list[tuple[str, str]]:
    spec = harness.app.openapi()
    found: list[tuple[str, str]] = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            content = op.get("requestBody", {}).get("content", {}).get("application/json")
            if content is None or "$ref" not in content.get("schema", {}):
                continue
            name = content["schema"]["$ref"].rsplit("/", 1)[-1]
            if name in COMMAND_BODIES or name.replace("-Input", "") in COMMAND_BODIES:
                found.append((method, path))
    return found


@pytest.mark.parametrize("extra", RESERVED_BODIES)
def test_every_route_with_a_command_body_answers_422_reserved_identifier(
    harness: Harness, extra: dict[str, str]
) -> None:
    routes = _command_routes(harness)
    assert len(routes) > 30 and "/uploads" in [p for _, p in routes]
    admin = _admin(harness)
    for method, path in routes:
        refused = admin.request(method, path, json=extra)
        assert refused.status_code == 422, (path, refused.text)
        body: dict[str, Any] = refused.json()
        assert body["error"] == "reserved_identifier", (path, body)
        assert "server sets it" in body["message"], (path, body)


def test_the_422_does_not_repeat_the_value_a_client_sent(harness: Harness) -> None:
    refused = _admin(harness).post(
        "/commands/RegisterDocument",
        json={"scope": SCOPE, "number": "X-1", "title": "t", "source": "job:secret-kind"},
    )
    assert refused.status_code == 422
    assert "secret-kind" not in refused.text


def test_a_document_with_ordinary_identifiers_still_registers(harness: Harness) -> None:
    ok = harness.client.post(
        "/commands/RegisterDocument",
        json={
            "scope": SCOPE,
            "number": "ISO-9001",
            "title": "A document",
            "correlation_id": ULID,
            "source": "tui",
        },
    )
    assert ok.status_code == 200, ok.text
