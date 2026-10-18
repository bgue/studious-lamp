"""Inbound deliveries: accept, map, apply and fail (FANOUT D4, D5, D11; ADR-0017)."""

from __future__ import annotations

import io
import json
from datetime import timedelta
from typing import Any

import pytest
from intworld import ADMIN, SCOPE, World
from sqlalchemy import text
from tl_core.integration.apps import SetIntegrationAppEnabled, handle_set_app_enabled
from tl_core.integration.contract import INBOUND_REPLAY_RETENTION_S
from tl_core.integration.inbound import store as body_store
from tl_core.integration.inbound.gate import (
    InvalidPayload,
    PendingFull,
    ReplayError,
    accept_delivery,
    check_pending,
    endpoint_view,
    find_open_endpoint,
    parse_payload,
    verify_request,
)
from tl_core.integration.inbound.service import (
    ReviseInboundEndpoint,
    SetInboundEndpointEnabled,
    handle_revise_endpoint,
    handle_set_endpoint_enabled,
)
from tl_core.integration.inbound.verify import VerifyError
from tl_core.util import new_ulid, utcnow
from tl_core.webhooks.rows import as_object, load_json
from tl_core.webhooks.signing import SigningSecret, sign_headers

POST = '{"command": "PostToFeed", "args": {"body": $.text}}'


def run(world: World) -> list[Any]:
    return world.inbound_runner().run_until_idle()


def only(world: World) -> dict[str, Any]:
    [row] = world.deliveries()
    return row


def revise(world: World, endpoint_id: str, changes: dict[str, Any]) -> None:
    with world.factory() as uow:
        handle_revise_endpoint(
            uow,
            ReviseInboundEndpoint(
                actor=ADMIN, source="test", scope=SCOPE, endpoint_id=endpoint_id,
                changes=changes, reason="test",
            ),
        )  # fmt: skip


# --- applied -------------------------------------------------------------------------------------


def test_a_delivery_is_mapped_and_applied_as_the_service_actor(world: World) -> None:
    made = world.endpoint()
    delivery_id = world.deliver(made.endpoint_id, {"text": "pump 7 tripped"})
    assert only(world)["state"] == "queued"
    run(world)
    row = only(world)
    assert (row["state"], row["command_count"], row["attempts"]) == ("applied", 1, 1)
    [post] = world.posts()
    assert post["body"] == "pump 7 tripped"
    assert post["actor"] == "svc:inbound-erp-orders" and post["source"] == "inbound:erp/orders"
    assert post["correlation_id"] == f"inbound:{delivery_id}" and post["causation_id"] is None
    received, applied = world.events("Inbound.Received"), world.events("Inbound.Applied")
    assert [e["stream_id"] for e in (received[0], applied[0])] == [delivery_id, delivery_id]
    assert as_object(load_json(applied[0]["payload"])) == {
        "delivery_id": delivery_id, "command_count": 1, "dry_run": False
    }  # fmt: skip


def test_the_events_hold_no_payload_and_no_header(world: World) -> None:
    made = world.endpoint()
    world.deliver(made.endpoint_id, {"text": "TOPSECRETPAYLOAD"})
    run(world)
    for name in ("Inbound.Received", "Inbound.Applied"):
        assert "TOPSECRETPAYLOAD" not in json.dumps(world.events(name), default=str)
    received = as_object(load_json(world.events("Inbound.Received")[0]["payload"]))
    assert set(received) == {
        "delivery_id", "endpoint_id", "endpoint_version", "payload_sha256", "payload_size"
    }  # fmt: skip


def test_a_dry_run_endpoint_plans_and_writes_nothing_but_the_delivery(world: World) -> None:
    made = world.endpoint(live=False)
    world.deliver(made.endpoint_id, {"text": "hello"})
    run(world)
    assert only(world)["state"] == "dry_run" and world.posts() == []
    assert as_object(load_json(world.events("Inbound.Applied")[0]["payload"]))["dry_run"] is True


def test_a_mapping_that_gives_nothing_is_applied_with_no_commands(world: World) -> None:
    made = world.endpoint(
        mapping='$.text = "go" ? {"command": "PostToFeed", "args": {"body": "x"}}'
    )
    world.deliver(made.endpoint_id, {"text": "stop"})
    run(world)
    assert (only(world)["state"], only(world)["command_count"]) == ("applied", 0)


def test_keys_resolve_inside_the_scope_and_links_carry_the_mapping_source(world: World) -> None:
    world.record("47-1", title="Pump")
    world.record("47-2", title="Valve")
    mapping = (
        '{"command": "AddLink", "args": {"from_id": {"$key": $.a}, "to_id": {"$key": $.b}, '
        '"relation": "references"}}'
    )
    made = world.endpoint(mapping=mapping, allowed_commands=["AddLink"])
    world.deliver(made.endpoint_id, {"a": "47-1", "b": "47-2"})
    run(world)
    assert only(world)["state"] == "applied"
    [link] = world.rows("SELECT * FROM cur_links")
    assert link["source"] == "mapping"


# --- failures ------------------------------------------------------------------------------------


def failed(world: World) -> tuple[str, str]:
    row = only(world)
    assert row["state"] == "failed", row
    return row["error_code"], row["error_message"]


def test_a_key_that_names_no_record_fails_the_delivery(world: World) -> None:
    mapping = (
        '{"command": "AddLink", "args": {"from_id": {"$key": "NO-1"}, "to_id": {"$key": "NO-2"}}}'
    )
    made = world.endpoint(mapping=mapping, allowed_commands=["AddLink"])
    world.deliver(made.endpoint_id, {})
    run(world)
    assert failed(world)[0] == "key_not_found"
    assert world.events("Inbound.Failed")[0]["stream_id"] == only(world)["delivery_id"]


def test_a_key_of_another_scope_is_not_found(world: World) -> None:
    world.record("47-1", scope="project:OTHER")
    world.record("47-2")
    mapping = (
        '{"command": "AddLink", "args": {"from_id": {"$key": "47-1"}, "to_id": {"$key": "47-2"}}}'
    )
    made = world.endpoint(mapping=mapping, allowed_commands=["AddLink"])
    world.deliver(made.endpoint_id, {})
    run(world)
    assert failed(world)[0] == "key_not_found" and world.rows("SELECT 1 FROM cur_links") == []


def test_a_command_outside_the_endpoints_list_fails_and_nothing_is_written(world: World) -> None:
    mapping = (
        '[{"command": "PostToFeed", "args": {"body": "first"}}, '
        '{"command": "CreateRecord", "args": {"record_type": "core.Record", '
        '"title": "T", "key": "X-1"}}]'
    )
    made = world.endpoint(mapping=mapping)
    world.deliver(made.endpoint_id, {})
    run(world)
    assert failed(world)[0] == "command_not_allowed"
    assert world.posts() == [] and world.rows("SELECT 1 FROM cur_core_record") == []


def test_one_refused_command_rolls_back_the_whole_delivery(world: World) -> None:
    mapping = (
        '[{"command": "PostToFeed", "args": {"body": "first"}}, '
        '{"command": "AddLink", "args": {"from_id": "nope", "to_id": "nada"}}]'
    )
    made = world.endpoint(mapping=mapping, allowed_commands=["PostToFeed", "AddLink"])
    world.deliver(made.endpoint_id, {})
    run(world)
    assert failed(world)[0] in ("command_refused", "command_failed")
    assert world.posts() == []
    assert world.events("Inbound.Applied") == []


def test_server_fields_in_a_mapped_command_are_refused(world: World) -> None:
    mapping = '{"command": "PostToFeed", "args": {"body": "x", "actor": "user:boss"}}'
    made = world.endpoint(mapping=mapping)
    world.deliver(made.endpoint_id, {})
    run(world)
    assert failed(world)[0].startswith("mapping_")
    assert world.posts() == []


@pytest.mark.parametrize(
    ("body", "code"),
    [(b"not json", "invalid_payload"), (b'{"text": NaN}', "invalid_payload")],
)
def test_a_body_that_is_not_json_fails(world: World, body: bytes, code: str) -> None:
    made = world.endpoint()
    world.deliver(made.endpoint_id, body)
    run(world)
    assert failed(world)[0] == code


def test_a_mapping_error_fails_with_its_code_and_never_the_payload(world: World) -> None:
    made = world.endpoint(mapping='{"command": "PostToFeed", "args": {"body": $number($.text)}}')
    world.deliver(made.endpoint_id, {"text": "LEAKYVALUE"})
    run(world)
    code, message = failed(world)
    assert code.startswith("mapping_")
    for place in (message, json.dumps(world.events("Inbound.Failed"), default=str)):
        assert "LEAKYVALUE" not in place


def test_a_refused_command_message_holds_no_value_of_the_payload(world: World) -> None:
    made = world.endpoint(
        mapping='{"command": "AddLink", "args": {"from_id": $.text, "to_id": $.text}}',
        allowed_commands=["AddLink"],
    )
    world.deliver(made.endpoint_id, {"text": "LEAKYVALUE"})
    run(world)
    assert "LEAKYVALUE" not in failed(world)[1]
    assert "LEAKYVALUE" not in json.dumps(world.events("Inbound.Failed"), default=str)


def test_a_missing_stored_body_fails_the_delivery(world: World) -> None:
    made = world.endpoint()
    world.deliver(made.endpoint_id, {"text": "x"})
    world.store.objects.clear()
    run(world)
    assert failed(world)[0] == "payload_missing"


# --- the state of the endpoint, the app and the switch -------------------------------------------


def test_the_kill_switch_stops_a_queued_delivery_and_marks_it_killed(world: World) -> None:
    made = world.endpoint()
    world.deliver(made.endpoint_id, {"text": "x"})
    world.setting("integration.kill_switch", True)
    run(world)
    row = only(world)
    assert (row["state"], row["error_code"]) == ("killed", "killed") and world.posts() == []


def test_an_endpoint_switched_off_after_receipt_does_not_apply(world: World) -> None:
    made = world.endpoint()
    world.deliver(made.endpoint_id, {"text": "x"})
    with world.factory() as uow:
        handle_set_endpoint_enabled(
            uow,
            SetInboundEndpointEnabled(
                actor=ADMIN, source="test", scope=SCOPE, endpoint_id=made.endpoint_id, enabled=False
            ),
        )
    run(world)
    assert failed(world)[0] == "endpoint_off" and world.posts() == []


def test_a_disabled_app_stops_its_endpoints(world: World) -> None:
    made = world.endpoint()
    app_id = world.rows("SELECT app_id FROM cur_integration_app")[0]["app_id"]
    with world.factory() as uow:
        handle_set_app_enabled(
            uow,
            SetIntegrationAppEnabled(
                actor=ADMIN, source="test", scope=SCOPE, app_id=app_id, enabled=False
            ),
        )
    with world.factory() as uow:
        assert find_open_endpoint(uow.conn(), "erp", "orders") is None
    world.deliver(made.endpoint_id, {"text": "x"})
    run(world)
    assert failed(world)[0] == "endpoint_off"


def test_a_delivery_is_mapped_by_the_version_it_was_received_under(world: World) -> None:
    made = world.endpoint()
    world.deliver(made.endpoint_id, {"text": "hello"})
    revise(
        world, made.endpoint_id, {"mapping": '{"command": "PostToFeed", "args": {"body": "NEW"}}'}
    )
    run(world)
    assert [p["body"] for p in world.posts()] == ["hello"]
    world.deliver(made.endpoint_id, {"text": "hello"})
    run(world)
    assert [p["body"] for p in world.posts()] == ["hello", "NEW"]


def test_a_finished_delivery_is_not_run_twice(world: World) -> None:
    made = world.endpoint()
    world.deliver(made.endpoint_id, {"text": "x"})
    run(world)
    assert run(world) == []
    assert len(world.posts()) == 1


# --- the gate ------------------------------------------------------------------------------------


def test_only_an_open_endpoint_is_found(world: World) -> None:
    with world.factory() as uow:
        assert find_open_endpoint(uow.conn(), "erp", "orders") is None
    made = world.endpoint(on=False)
    with world.factory() as uow:
        assert find_open_endpoint(uow.conn(), "erp", "orders") is None
        assert endpoint_view(uow.conn(), made.endpoint_id) is not None
    world.switch_endpoint(made.endpoint_id, True)
    with world.factory() as uow:
        found = find_open_endpoint(uow.conn(), "erp", "orders")
        assert found is not None and found.path == "/in/erp/orders"
        assert find_open_endpoint(uow.conn(), "erp", "x" * 300) is None
    world.setting("integration.kill_switch", True)
    with world.factory() as uow:
        assert find_open_endpoint(uow.conn(), "erp", "orders") is None


@pytest.mark.parametrize(
    "body",
    [b"\xff\xfe", b"{", b'{"a": NaN}', b'{"a": Infinity}', b"1" * 50, b"[" * 40 + b"]" * 40,
     b"1e999", b"[1." + b"0" * 60 + b"]", b""],
)  # fmt: skip
def test_a_body_that_is_not_acceptable_json_is_refused(body: bytes) -> None:
    with pytest.raises(InvalidPayload):
        parse_payload(body)


def test_ordinary_json_parses() -> None:
    assert parse_payload(b'{"a": [1, 2.5, "x", null, true], "b": {"c": 1}}') == {
        "a": [1, 2.5, "x", None, True],
        "b": {"c": 1},
    }
    assert parse_payload(b"[" * 31 + b"]" * 31) is not None


def test_verification_uses_the_live_secrets_of_the_endpoint(world: World) -> None:
    made = world.endpoint()
    assert made.secret is not None
    secret = SigningSecret(made.secret.secret)
    now = utcnow()
    body = b'{"text": "x"}'
    headers = sign_headers("msg_1", int(now.timestamp()), body.decode(), [secret])
    with world.factory(readonly=True) as uow:
        view = endpoint_view(uow.conn(), made.endpoint_id)
        assert view is not None
        assert verify_request(uow.conn(), view, headers, body, now=now) == "msg_1"
        other = sign_headers(
            "msg_2",
            int(now.timestamp()),
            body.decode(),
            [
                SigningSecret(
                    made.secret.secret.replace("A", "B", 1)
                    if "A" in made.secret.secret[6:]
                    else made.secret.secret[:-4] + "AAAA"
                )
            ],
        )
        with pytest.raises(VerifyError):
            verify_request(uow.conn(), view, other, body, now=now)
        with pytest.raises(VerifyError):
            verify_request(uow.conn(), view, headers, b"{}", now=now)


def accept_again(world: World, endpoint_id: str, message_id: str, *, now: Any = None) -> None:
    delivery_id = new_ulid()
    key = body_store.body_key(endpoint_id, delivery_id)
    digest = body_store.put_body(world.store, key, b"{}")
    with world.factory() as uow:
        view = endpoint_view(uow.conn(), endpoint_id)
        assert view is not None
        accept_delivery(
            uow, view, message_id=message_id, delivery_id=delivery_id, object_key=key,
            payload_sha256=digest, payload_size=2, now=now or utcnow(),
        )  # fmt: skip


def test_a_message_id_is_accepted_once_within_the_retention_window(world: World) -> None:
    made = world.endpoint()
    accept_again(world, made.endpoint_id, "m1")
    with pytest.raises(ReplayError):
        accept_again(world, made.endpoint_id, "m1")
    assert len(world.deliveries()) == 1  # the refused one left no delivery, no job, no event
    assert len(world.events("Inbound.Received")) == 1
    accept_again(world, made.endpoint_id, "m2")
    other = world.endpoint("other")
    accept_again(world, other.endpoint_id, "m1")  # replay ids are per endpoint


def test_an_old_replay_row_is_pruned_and_the_id_may_come_again(world: World) -> None:
    made = world.endpoint()
    long_ago = utcnow() - timedelta(seconds=INBOUND_REPLAY_RETENTION_S + 60)
    accept_again(world, made.endpoint_id, "m1", now=long_ago)
    accept_again(world, made.endpoint_id, "m1")
    assert len(world.deliveries()) == 2


def test_a_bad_message_id_is_refused(world: World) -> None:
    made = world.endpoint()
    for bad in ("", "x" * 200):
        with pytest.raises(ReplayError):
            accept_again(world, made.endpoint_id, bad)


def test_too_many_waiting_deliveries_refuse_more(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tl_core.integration.inbound import gate

    made = world.endpoint()
    monkeypatch.setattr(gate, "INBOUND_MAX_PENDING_PER_ENDPOINT", 2)
    world.deliver(made.endpoint_id, {})
    with world.factory(readonly=True) as uow:
        check_pending(uow.conn(), made.endpoint_id)
    world.deliver(made.endpoint_id, {})
    with world.factory(readonly=True) as uow, pytest.raises(PendingFull):
        check_pending(uow.conn(), made.endpoint_id)


def test_the_orphans_of_a_failed_transaction_are_listed(world: World) -> None:
    made = world.endpoint()
    world.deliver(made.endpoint_id, {})
    stray = body_store.body_key(made.endpoint_id, new_ulid())
    body_store.put_body(world.store, stray, b"{}")
    body_store.put_body(world.store, f"{stray}.corrected.abcd1234", b"{}")
    with world.factory(readonly=True) as uow:
        assert body_store.orphans(uow, world.store) == [stray, f"{stray}.corrected.abcd1234"]
        assert body_store.orphans(uow, _NoListing()) is None  # type: ignore[arg-type]


class _NoListing:
    def get(self, key: str) -> io.BytesIO:  # pragma: no cover - never read
        raise KeyError(key)


def test_the_counter_counts_by_fixed_code(world: World) -> None:
    from tl_core.integration.inbound.gate import count_failure

    made = world.endpoint()
    for _ in range(3):
        with world.factory() as uow:
            count_failure(uow.conn(), made.endpoint_id, "bad_signature", utcnow())
    rows = world.rows("SELECT code, count FROM int_counter")
    assert [(r["code"], r["count"]) for r in rows] == [("bad_signature", 3)]
    assert world.rows("SELECT 1 FROM int_counter WHERE endpoint_id = :e", e=made.endpoint_id)
    assert text  # the module-level import is used by the queries above
