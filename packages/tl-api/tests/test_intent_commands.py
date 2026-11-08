"""Intent at the command boundary (ADR-0025 d4, d7): accepted, checked, stored, returned."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness import SCOPE, Harness
from sqlalchemy import text
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password

PASSWORD = "correct horse battery"
EDITION = "co.acme.standards@1.0.0"
FIXED = "intent reference not found"


def count(harness: Harness) -> int:
    with harness.backend(True) as uow:
        return int(uow.conn().execute(text("SELECT COUNT(*) FROM events")).scalar_one())


def stored_intents(harness: Harness) -> list[str | None]:
    with harness.backend(True) as uow:
        rows = uow.conn().execute(text("SELECT intent FROM events ORDER BY seq")).all()
    return [r[0] for r in rows]


def create(client: TestClient, key: str, **extra: Any) -> Any:
    return client.post(
        "/commands/CreateRecord",
        json={
            "scope": SCOPE,
            "record_type": "core.Record",
            "title": "T " + key,
            "key": key,
            **extra,
        },
    )


def person(harness: Harness, name: str, roles: list[str]) -> TestClient:
    with harness.backend() as uow:
        accounts.create_account(
            uow, username=name, display_name=name, kind="person", roles=roles,
            password=prepare_password(PASSWORD), by="svc:test",
        )  # fmt: skip
    _, token = sessions.sign_in(harness.backend, username=name, password=PASSWORD)
    client = harness.client_for(None)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def register(client: TestClient, **extra: Any) -> Any:
    return client.post(
        "/commands/RegisterCodeList",
        json={
            "scope": "company", "code": "Area", "label": "Area", "edition": EDITION,
            "value_list_policy": "extensible", **extra,
        },
    )  # fmt: skip


def test_a_core_command_stores_the_intent_with_keys_as_ids(harness: Harness) -> None:
    first = create(harness.client, "R-1").json()["stream_id"]
    done = create(
        harness.client,
        "R-2",
        intent={
            "why": "Needed before the pour",
            "next": [{"command": "UpdateRecord", "target": "R-1"}, {"text": "call the vendor"}],
            "toward": {"target": "R-1", "condition": "inspected"},
            "goal_ref": "pour-1",
        },
    )
    assert done.status_code == 200, done.text
    history = harness.client.get(f"/records/{done.json()['stream_id']}/history").json()
    intent = history[0]["intent"]
    assert intent["why"] == "Needed before the pour" and intent["goal_ref"] == "pour-1"
    assert intent["next"][0] == {"command": "UpdateRecord", "target": first, "text": None}
    assert intent["toward"]["target"] == first
    assert "R-1" not in str(stored_intents(harness)[-1])  # ids are stored, never the key


def test_a_module_command_stores_it_too_with_no_handler_change(harness: Harness) -> None:
    boss = person(harness, "boss", ["admin"])
    made = register(boss, intent={"why": "Areas first", "next": [{"command": "AddCodeValue"}]})
    assert made.status_code == 200, made.text
    events = harness.client.get("/events").json()["events"]
    assert events and all(e["intent"]["why"] == "Areas first" for e in events)
    assert made.json()["events"][0]["intent"]["next"][0]["command"] == "AddCodeValue"


def test_events_listing_returns_the_intent(harness: Harness) -> None:
    create(harness.client, "R-1", intent={"why": "listed"})
    events = harness.client.get("/events").json()["events"]
    assert [e["intent"] and e["intent"]["why"] for e in events] == ["listed"]


@pytest.mark.parametrize(
    "intent",
    [
        {"why": "x" * 501},
        {"next": [{"command": "NoSuchCommand"}]},
        {"goal_ref": "Bad Ref"},
        {"why": "bell\x07"},
    ],
)
def test_an_invalid_intent_refuses_the_whole_command(harness: Harness, intent: Any) -> None:
    before = count(harness)
    refused = create(harness.client, "R-1", intent=intent)
    assert refused.status_code == 422 and refused.json()["error"] == "intent_invalid"
    assert count(harness) == before  # nothing appended
    assert (
        harness.client.get("/records/lookup", params={"scope": SCOPE, "key": "R-1"}).status_code
        == 404
    )


def test_an_unknown_reference_has_its_own_code_and_a_fixed_message(harness: Harness) -> None:
    before = count(harness)
    refused = create(
        harness.client, "R-1", intent={"toward": {"target": "NOPE-9", "condition": "SECRET"}}
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"] == "intent_reference_unknown"
    assert refused.json()["message"] == FIXED
    assert "NOPE-9" not in refused.text and "SECRET" not in refused.text
    assert count(harness) == before


def test_an_empty_intent_is_stored_as_null(harness: Harness) -> None:
    create(harness.client, "R-1", intent={})
    create(harness.client, "R-2", intent={"why": None, "next": []})
    assert stored_intents(harness) == [None, None]


def test_an_intent_changes_no_access_decision(harness: Harness) -> None:
    bob = person(harness, "bob", ["user"])
    plain = register(bob)
    with_intent = register(bob, intent={"why": "please"})
    bad_intent = register(bob, intent={"why": "x" * 501})  # access answers before the intent does
    assert plain.status_code == with_intent.status_code == bad_intent.status_code == 403
    assert plain.text == with_intent.text == bad_intent.text


def test_the_carrier_is_cleared_after_the_command(harness: Harness) -> None:
    create(harness.client, "R-1", intent={"why": "only this command"})
    harness.create_record("R-2")  # a handler called outside the dispatcher
    create(harness.client, "R-3")
    assert [i is not None for i in stored_intents(harness)] == [True, False, False]


def test_the_stream_of_events_and_history_show_the_same_intent(harness: Harness) -> None:
    rid = create(harness.client, "R-1", intent={"why": "same"}).json()["stream_id"]
    history = harness.client.get(f"/records/{rid}/history").json()[0]["intent"]
    listed = harness.client.get("/events").json()["events"][0]["intent"]
    assert history == listed
