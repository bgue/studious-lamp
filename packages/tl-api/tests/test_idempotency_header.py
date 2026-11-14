"""``POST /commands/{Name}`` honours an ``Idempotency-Key`` header (P2-X1-T01).

The header is copied onto the command, so the door that S1 added (``run_command``) replays or
refuses. The body field ``idempotency_key`` still works; both given and different is a 422.
"""

from __future__ import annotations

from typing import Any

import pytest
from harness import ALICE, BOB, SCOPE, Harness
from sqlalchemy import text

KEY = "hdr-key-7c1a9e"
MISMATCH_TEXT = "Idempotency-Key header and body idempotency_key differ"


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


def body(title: str = "Valve", key: str = "REC-1", **extra: Any) -> dict[str, Any]:
    return {"scope": SCOPE, "record_type": "core.Record", "title": title, "key": key, **extra}


def post(h: Harness, body_: dict[str, Any], header: str | None = None, actor: str = ALICE) -> Any:
    headers = {} if header is None else {"Idempotency-Key": header}
    return h.client_for(actor).post("/commands/CreateRecord", json=body_, headers=headers)


def scalar(harness: Harness, sql: str) -> int:
    with harness.backend(True) as uow:
        return int(uow.conn().execute(text(sql)).scalar_one())


def events(harness: Harness) -> int:
    return scalar(harness, "SELECT COUNT(*) FROM events")


def test_same_header_and_body_twice_writes_once_and_replays(harness: Harness) -> None:
    first = post(harness, body(), KEY)
    assert first.status_code == 200, first.text
    count = events(harness)
    second = post(harness, body(), KEY)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert events(harness) == count
    assert scalar(harness, "SELECT COUNT(*) FROM idempotency_key") == 1


def test_same_header_other_body_is_409_and_writes_nothing(harness: Harness) -> None:
    assert post(harness, body(), KEY).status_code == 200
    count = events(harness)
    response = post(harness, body(key="REC-2"), KEY)
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "idempotency_mismatch"
    assert KEY not in response.text
    assert events(harness) == count


def test_header_only_and_body_only_have_the_same_effect(harness: Harness) -> None:
    header_only = post(harness, body(key="REC-H"), KEY)
    assert header_only.status_code == 200, header_only.text
    body_only = post(harness, body(key="REC-B", idempotency_key="body-key-3f8d1a"))
    assert body_only.status_code == 200, body_only.text
    assert scalar(harness, "SELECT COUNT(*) FROM idempotency_key") == 2
    # the stored key is the one the client sent, whichever way it came
    with harness.backend(True) as uow:
        keys = {
            row[0] for row in uow.conn().execute(text("SELECT idem_key FROM idempotency_key")).all()
        }
    assert keys == {KEY, "body-key-3f8d1a"}


def test_header_and_body_equal_is_accepted(harness: Harness) -> None:
    response = post(harness, body(idempotency_key=KEY), KEY)
    assert response.status_code == 200, response.text


def test_header_and_body_differing_is_422_and_writes_nothing(harness: Harness) -> None:
    count = events(harness)
    response = post(harness, body(idempotency_key="body-key-3f8d1a"), KEY)
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "invalid_idempotency_key"
    assert response.json()["message"] == MISMATCH_TEXT
    assert KEY not in response.text and "body-key-3f8d1a" not in response.text
    assert events(harness) == count
    assert scalar(harness, "SELECT COUNT(*) FROM idempotency_key") == 0


@pytest.mark.parametrize(
    "bad",
    ["k" * 129, "has a space", ""],
    ids=["129-chars", "space", "empty"],
)
def test_a_bad_header_is_422_and_never_echoed(harness: Harness, bad: str) -> None:
    count = events(harness)
    response = post(harness, body(), bad)
    assert response.status_code == 422, response.text
    # the command model's own validator refuses it (pydantic, input hidden), so the code is the
    # generic validation_error rather than invalid_idempotency_key
    assert response.json()["error"] == "validation_error"
    if bad:
        assert bad not in response.text
    assert events(harness) == count


def test_another_actor_with_the_same_header_gets_its_own_record(harness: Harness) -> None:
    alice = post(harness, body(key="REC-A"), KEY, actor=ALICE)
    assert alice.status_code == 200, alice.text
    bobs = post(harness, body(key="REC-B"), KEY, actor=BOB)
    assert bobs.status_code == 200, bobs.text
    assert bobs.json()["stream_id"] != alice.json()["stream_id"]
    assert scalar(harness, "SELECT COUNT(*) FROM idempotency_key") == 2


def test_no_header_is_unchanged(harness: Harness) -> None:
    assert post(harness, body(key="REC-1")).status_code == 200
    assert post(harness, body(key="REC-2")).status_code == 200
    assert scalar(harness, "SELECT COUNT(*) FROM idempotency_key") == 0


def test_openapi_lists_the_header_as_optional_on_create_record(harness: Harness) -> None:
    operation = harness.app.openapi()["paths"]["/commands/CreateRecord"]["post"]
    headers = [p for p in operation["parameters"] if p["in"] == "header"]
    match = [p for p in headers if p["name"] == "Idempotency-Key"]
    assert len(match) == 1
    assert match[0]["required"] is False
