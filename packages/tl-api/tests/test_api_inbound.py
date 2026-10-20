"""``POST /in/{app}/{endpoint}``: the order of its answers and what each one leaks (D4).

The route has no session. Every refusal before a valid signature is a fixed answer; the order is
fixed: not accepting (404), rate (429), body cap (413), verification (401), parse (422), accept.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from harness import Harness
from tl_core.integration.apps import RegisterIntegrationApp, handle_register_app
from tl_core.integration.contract import INBOUND_NOT_FOUND_BODY, INBOUND_UNAUTHORIZED_BODY
from tl_core.integration.inbound.service import (
    CreateInboundEndpoint,
    SetInboundEndpointEnabled,
    create_endpoint,
    handle_set_endpoint_enabled,
)
from tl_core.services.settings import ChangeSetting, handle_change_setting
from tl_core.webhooks.rows import load_json
from tl_core.webhooks.signing import SigningSecret, sign_headers

SCOPE = "project:P123"
BODY = b'{"text": "pump 7 tripped"}'
MAPPING = '{"command": "PostToFeed", "args": {"body": $.text}}'


class Endpoint:
    def __init__(self, harness: Harness, name: str, *, auth: Any = "hmac_sha256", **over: Any):
        with harness.backend() as uow:
            if uow.conn().exec_driver_sql("SELECT 1 FROM cur_integration_app").first() is None:
                handle_register_app(
                    uow,
                    RegisterIntegrationApp(
                        actor="user:boss", source="test", scope=SCOPE, name="erp", label="ERP"
                    ),
                )
        with harness.backend() as uow:
            made = create_endpoint(
                uow,
                CreateInboundEndpoint(
                    actor="user:boss",
                    source="test",
                    scope=SCOPE,
                    app="erp",
                    name=name,
                    mapping=MAPPING,
                    allowed_commands=["PostToFeed"],
                    auth=auth,
                    **over,
                ),  # fmt: skip
            )
        assert made.secret is not None
        self.id = made.endpoint_id
        self.secret = SigningSecret(made.secret.secret)
        self.path = f"/in/erp/{name}"
        self.harness = harness
        self.switch(True)

    def switch(self, on: bool) -> None:
        with self.harness.backend() as uow:
            handle_set_endpoint_enabled(
                uow,
                SetInboundEndpointEnabled(
                    actor="user:boss", source="test", scope=SCOPE, endpoint_id=self.id, enabled=on
                ),
            )

    def hmac(
        self, body: bytes = BODY, message_id: str = "msg_1", ts: float | None = None
    ) -> dict[str, str]:
        stamp = int(ts if ts is not None else time.time())
        return sign_headers(message_id, stamp, body.decode(), [self.secret])

    def bearer(self, body: bytes = BODY, jti: str = "j1", **claims: Any) -> dict[str, str]:
        now = int(time.time())
        data = {
            "iat": now, "exp": now + 60, "aud": self.path, "jti": jti,
            "body_sha256": hashlib.sha256(body).hexdigest(),
        }  # fmt: skip
        data.update(claims)
        token = jwt.encode(data, self.secret.key(), algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(harness: Harness) -> TestClient:
    return harness.client_for(None)  # no token: the route has no session


@pytest.fixture
def endpoint(harness: Harness) -> Endpoint:
    return Endpoint(harness, "orders")


def rows(harness: Harness, sql: str) -> list[dict[str, Any]]:
    with harness.backend(True) as uow:
        return [dict(r) for r in uow.conn().exec_driver_sql(sql).mappings()]


def post(
    client: TestClient, path: str, body: bytes = BODY, headers: dict[str, str] | None = None
) -> Any:
    return client.post(path, content=body, headers=headers or {})


# --- 1. not accepting ----------------------------------------------------------------------------


def test_every_reason_for_not_accepting_is_the_same_404(
    harness: Harness, client: TestClient, endpoint: Endpoint
) -> None:
    off = Endpoint(harness, "off")
    off.switch(False)
    answers = [
        post(client, "/in/erp/nope", headers=endpoint.hmac()),
        post(client, "/in/nope/orders", headers=endpoint.hmac()),
        post(client, off.path, headers=off.hmac()),
        post(client, "/in/erp", headers=endpoint.hmac()),
        post(client, "/in/erp/orders/extra", headers=endpoint.hmac()),
        post(client, "/in/erp//", headers=endpoint.hmac()),
        client.get(endpoint.path),
        client.put(endpoint.path, content=BODY, headers=endpoint.hmac()),
    ]
    with harness.backend() as uow:
        handle_change_setting(
            uow,
            ChangeSetting(
                actor="user:boss", source="test", scope="company", key="integration.kill_switch",
                layer="company", value=True, reason="test", accept_risk=True,
            ),
        )  # fmt: skip
    answers.append(post(client, endpoint.path, headers=endpoint.hmac(message_id="m2")))
    for answer in answers:
        assert answer.status_code == 404 and answer.content == INBOUND_NOT_FOUND_BODY
    assert len({tuple(sorted(a.headers.items())) for a in answers}) == 1  # even the headers


# --- 2 to 6. the order ---------------------------------------------------------------------------


def test_a_signed_request_is_accepted_and_queued(
    harness: Harness, client: TestClient, endpoint: Endpoint
) -> None:
    answer = post(client, endpoint.path, headers=endpoint.hmac())
    assert answer.status_code == 202
    delivery_id = answer.json()["delivery_id"]
    [delivery] = rows(harness, "SELECT * FROM int_delivery")
    assert delivery["delivery_id"] == delivery_id and delivery["state"] == "queued"
    assert delivery["payload_sha256"] == hashlib.sha256(BODY).hexdigest()
    assert delivery["payload_size"] == len(BODY)
    assert harness.store.exists(delivery["object_key"])
    assert rows(harness, "SELECT kind, state FROM job_queue") == [
        {"kind": "inbound.map", "state": "queued"}
    ]
    [event] = rows(harness, "SELECT * FROM events WHERE event_type = 'Inbound.Received'")
    assert event["stream_id"] == delivery_id and event["source"] == "inbound:erp/orders"
    assert BODY.decode() not in json.dumps(event, default=str)
    assert load_json(event["payload"])["payload_size"] == len(BODY)


def test_a_jwt_endpoint_accepts_a_bound_token(harness: Harness, client: TestClient) -> None:
    jwt_endpoint = Endpoint(harness, "tokens", auth="jwt_hs256")
    assert post(client, jwt_endpoint.path, headers=jwt_endpoint.bearer()).status_code == 202
    for bad in (
        jwt_endpoint.bearer(jti="j2", body_sha256="0" * 64),  # another body
        jwt_endpoint.bearer(jti="j3", aud="/in/erp/other"),
        jwt_endpoint.hmac(),  # the wrong scheme for this endpoint
        {},
    ):
        refused = post(client, jwt_endpoint.path, headers=bad)
        assert refused.status_code == 401 and refused.content == INBOUND_UNAUTHORIZED_BODY


def test_every_verification_failure_is_the_same_401_and_is_counted(
    harness: Harness, client: TestClient, endpoint: Endpoint
) -> None:
    stale = endpoint.hmac(message_id="old", ts=time.time() - 3_600)
    wrong = {**endpoint.hmac(message_id="m9"), "webhook-signature": "v1,AAAA"}
    other = post(client, endpoint.path, headers=endpoint.hmac(message_id="m8"))  # accepted
    assert other.status_code == 202
    replay = post(client, endpoint.path, headers=endpoint.hmac(message_id="m8"))
    answers = [
        post(client, endpoint.path),
        post(client, endpoint.path, headers=stale),
        post(client, endpoint.path, headers=wrong),
        post(
            client, endpoint.path, body=b'{"text": "other"}', headers=endpoint.hmac(message_id="m7")
        ),
        replay,
    ]
    for answer in answers[:-1] + [replay]:
        assert answer.status_code == 401 and answer.content == INBOUND_UNAUTHORIZED_BODY
    assert len({tuple(sorted(a.headers.items())) for a in answers}) == 1
    counted = {r["code"]: r["count"] for r in rows(harness, "SELECT code, count FROM int_counter")}
    assert counted["replay"] == 1 and counted["bad_signature"] >= 3
    assert len(rows(harness, "SELECT 1 FROM int_delivery")) == 1  # the replay left nothing behind
    # nor an object: a replay is refused before the body is stored (second security review)
    assert len(list(harness.store.iter_keys())) == 1


def test_the_body_cap_is_checked_before_verification(harness: Harness, client: TestClient) -> None:
    small = Endpoint(harness, "small", max_body_bytes=64)
    big = b'{"text": "' + b"x" * 200 + b'"}'
    unsigned = post(client, small.path, body=big)
    assert unsigned.status_code == 413  # not 401: nothing past the cap is read or verified
    signed = post(client, small.path, body=big, headers=small.hmac(big))
    assert signed.status_code == 413

    def chunks() -> Any:
        for _ in range(10):
            yield b"x" * 30

    chunked = client.post(small.path, content=chunks())
    assert chunked.status_code == 413
    assert rows(harness, "SELECT 1 FROM int_delivery") == []


def test_verification_comes_before_the_parse(
    harness: Harness, client: TestClient, endpoint: Endpoint
) -> None:
    bad = b"{not json"
    assert post(client, endpoint.path, body=bad).status_code == 401  # unsigned: not a 422
    refused = post(client, endpoint.path, body=bad, headers=endpoint.hmac(bad))
    assert refused.status_code == 422 and refused.json()["error"] == "invalid_payload"
    deep = b"[" * 40 + b"]" * 40
    assert (
        post(client, endpoint.path, body=deep, headers=endpoint.hmac(deep, "m2")).status_code == 422
    )
    assert rows(harness, "SELECT 1 FROM int_delivery") == []
    # a refused body does not use up its message id
    assert post(client, endpoint.path, headers=endpoint.hmac(bad, "m1")).status_code == 401


def test_the_endpoint_rate_bound_answers_429_with_retry_after(
    harness: Harness, client: TestClient
) -> None:
    slow = Endpoint(harness, "slow", rate_per_minute=2)
    assert post(client, slow.path, headers=slow.hmac(message_id="a")).status_code == 202
    assert post(client, slow.path, headers=slow.hmac(message_id="b")).status_code == 202
    limited = post(client, slow.path, headers=slow.hmac(message_id="c"))
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
    assert limited.json()["error"] == "rate_limited"


def test_a_source_that_keeps_failing_is_limited_before_the_body_is_read(
    harness: Harness, client: TestClient, endpoint: Endpoint
) -> None:
    for _ in range(harness.settings.rate_limit_failures):
        assert post(client, endpoint.path).status_code == 401
    limited = post(client, endpoint.path, headers=endpoint.hmac())
    assert limited.status_code == 429  # even a good request waits: the source is the problem


def test_deliveries_over_the_pending_bound_are_refused(
    harness: Harness, client: TestClient, endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tl_core.integration.inbound import gate

    monkeypatch.setattr(gate, "INBOUND_MAX_PENDING_PER_ENDPOINT", 1)
    assert post(client, endpoint.path, headers=endpoint.hmac(message_id="a")).status_code == 202
    assert post(client, endpoint.path, headers=endpoint.hmac(message_id="b")).status_code == 429


# --- the walkers ---------------------------------------------------------------------------------


def test_no_fastapi_route_sits_under_the_inbound_prefix(harness: Harness) -> None:
    """The route family is the middleware's alone; a FastAPI route there would be unguarded."""
    paths = [getattr(route, "path", "") for route in harness.app.routes]
    assert not [p for p in paths if p.startswith("/in/")]
    assert not [p for p in harness.app.openapi()["paths"] if p.startswith("/in/")]


def test_the_rest_of_the_api_still_needs_a_token(client: TestClient, endpoint: Endpoint) -> None:
    assert client.get("/events").status_code == 401
    assert client.post("/commands/PostToFeed", json={}).status_code == 401
    assert client.get("/inx/erp/orders").status_code == 401  # only the exact prefix is the route's


def test_a_response_never_holds_the_secret_or_the_payload(
    harness: Harness, client: TestClient, endpoint: Endpoint
) -> None:
    answers = [
        post(client, endpoint.path, headers=endpoint.hmac(message_id="x1")),
        post(client, endpoint.path),
        post(client, endpoint.path, body=b"{bad", headers=endpoint.hmac(b"{bad", "x2")),
    ]
    for answer in answers:
        text = answer.text + json.dumps(dict(answer.headers))
        assert endpoint.secret.value not in text and "pump 7" not in text
