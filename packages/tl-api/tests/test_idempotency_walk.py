"""Idempotency keys are per actor at the HTTP edge (P2-X1-T07).

The same key value sent by another actor neither replays the first answer nor collides with it:
each actor gets its own record, with its own ids. The record key differs in the second body, so
the duplicate-record-key rule is not what is tested here.

Not here yet: the walk as five kinds of reader (a keyed replay after the viewer's clearance drops).
A ``core.Record`` made by ``CreateRecord`` cannot be made confidential through a ``use_modules``
extension type: the API refuses a record type that is not registered in the extension-type service
(``unsupported_record_type``). See the report's Blocked section.
"""

from __future__ import annotations

from typing import Any

import pytest
from harness import ALICE, BOB, SCOPE, Harness
from sqlalchemy import text

KEY = "walk-key-5e2b91"


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


def test_another_actor_with_the_same_key_and_other_body_gets_its_own_record_not_a_409(
    harness: Harness,
) -> None:
    alice = post(harness, body(key="REC-A"), KEY, actor=ALICE)
    assert alice.status_code == 200, alice.text
    bobs = post(harness, body(key="REC-OTHER", title="Pump"), KEY, actor=BOB)
    assert bobs.status_code != 409, bobs.text
    assert bobs.status_code == 200, bobs.text
    assert bobs.json()["stream_id"] != alice.json()["stream_id"]
    assert scalar(harness, "SELECT COUNT(*) FROM idempotency_key") == 2
