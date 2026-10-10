"""Contract: what webhooks deliver is what the generated event catalog promises (brief 18.3).

One scenario produces every event type of the catalog, through the real command handlers where
they exist and as raw ledger appends otherwise. Three subscriptions (thin, delta, full) receive
them; each delivered body is validated against the catalog's JSON Schema of that event type, and
the delivered facts are compared with the ledger.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from scenario import run_scenario
from tl_core.webhooks.signing import SigningSecret, verify
from tl_schema import catalog
from world import World


@pytest.fixture
def delivered(world: World) -> dict[str, list[dict[str, Any]]]:
    return run_scenario(world)


def validator(event_type: str) -> Draft202012Validator:
    schema = catalog.envelope_schema(event_type)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def event_type_of(body: dict[str, Any]) -> str:
    return body["type"].removeprefix("tl.core.").rsplit(".v", 1)[0]


def test_the_scenario_delivers_every_event_type_of_the_catalog(
    delivered: dict[str, list[dict[str, Any]]],
) -> None:
    # The thin subscription is never disabled, so it hears every event type. (The delta one is
    # disabled and re-enabled in the scenario and, by design, does not receive its own `Enabled`.)
    seen = {event_type_of(body) for body in delivered["thin"]}
    assert seen == set(catalog.event_types())


def test_every_delivered_body_validates_against_the_catalog_schema_of_its_type(
    delivered: dict[str, list[dict[str, Any]]],
) -> None:
    checked = 0
    for mode, bodies in delivered.items():
        for body in bodies:
            event_type = event_type_of(body)
            errors = list(validator(event_type).iter_errors(body))
            assert not errors, (mode, event_type, errors[0].message, list(errors[0].path))
            assert body["dataschema"] == catalog.envelope_schema(event_type)["$id"]
            checked += 1
    assert checked >= 3 * len(catalog.event_types())


def test_the_three_modes_carry_the_same_events_with_the_documented_members(
    delivered: dict[str, list[dict[str, Any]]],
) -> None:
    ids = {mode: sorted(body["id"] for body in bodies) for mode, bodies in delivered.items()}
    assert ids["thin"] and ids["delta"] and ids["full"]
    assert len(ids["thin"]) == len(set(ids["thin"]))
    for body in delivered["thin"]:
        assert set(body["data"]) == {"origin"}
    for body in delivered["delta"]:
        assert set(body["data"]) == {"origin", "changes", "links", "detail"}
    for body in delivered["full"]:
        assert set(body["data"]) == {"origin", "changes", "links", "detail", "record"}


def test_delivered_facts_match_the_ledger(world: World) -> None:
    delivered = run_scenario(world)
    ledger = {
        row["event_id"]: row
        for row in world.query(
            "SELECT event_id, seq, stream_version, actor, event_type, payload FROM events"
        )
    }
    for body in delivered["delta"]:
        row = ledger[body["id"]]
        assert body["tlseq"] == row["seq"]
        assert body["tlstreamversion"] == row["stream_version"]
        assert body["tlactor"] == row["actor"]
        assert event_type_of(body) == row["event_type"]
        assert body["data"]["detail"] == json.loads(row["payload"])
        assert body["subject"] == body["data"]["origin"]["id"]
        assert body["data"]["origin"]["uri"].startswith(body["source"])


def test_handler_written_payloads_match_the_catalog_payload_schemas(world: World) -> None:
    """Events written by real command handlers (not samples) validate against the payload class."""
    run_scenario(world)
    real = {"Record.Created", "Record.Updated", "Record.Voided"} | {
        t for t in catalog.event_types() if t.startswith("WebhookSubscription.")
    }
    for row in world.query("SELECT event_type, payload FROM events"):
        if row["event_type"] in real:
            schema = catalog.envelope_schema(row["event_type"])["properties"]["data"]["properties"]
            errors = list(
                Draft202012Validator(schema["detail"]).iter_errors(json.loads(row["payload"]))
            )
            assert not errors, (row["event_type"], errors[0].message)


def test_every_delivery_is_signed_and_the_id_header_is_the_event_id(world: World) -> None:
    issued = world.subscribe(mode="thin", name="verify")
    world.record("P1-S")
    world.dispatcher().run_until_idle()
    world.engine().run_cycle()
    for request in world.transport.sent:
        body = json.loads(request.body)
        assert request.headers["webhook-id"] == body["id"]
        verify(
            request.headers,
            request.body,
            [SigningSecret(issued.secret)],
            now=int(world.clock().timestamp()),
        )
