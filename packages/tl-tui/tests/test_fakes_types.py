"""The fake client's extension type support follows the real client's rules (P0-I8)."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import FakeClient
from tl_core.extypes.errors import (
    BodyHashMismatchError,
    BodyNotAllowedError,
    BodyNotFoundError,
    BodyRequiredError,
    BodyValidationError,
    UnknownTypeError,
)
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import RecordNotFoundError, UnsupportedRecordTypeError
from tl_tui.client import ClientInterface

SCOPE = "project:P1"
LIFT = "co.acme.LiftPlan"
OBSERVATION = "co.acme.SafetyObservation"
LIFT_BODY: dict[str, Any] = {
    "crane": "CR-12",
    "crew": ["A. Okafor"],
    "exclusion_zone_m": 8.5,
    "lift_date": "2026-11-03",
    "load_tonnes": 42.5,
    "method_statement": "Lift the skid to the pad.",
    "risk_class": "medium",
}


@pytest.fixture
def fake() -> FakeClient:
    client = FakeClient()
    client.add_example_type(LIFT)
    client.add_example_type(OBSERVATION)
    return client


def test_the_fake_still_satisfies_the_protocol(fake: FakeClient) -> None:
    as_protocol: ClientInterface = fake
    assert len(as_protocol.list_types()) == 2


def test_types_list_filter_and_detail(fake: FakeClient) -> None:
    fake.add_example_type("co.acme.LiftPlan", status="deprecated", version="0.9.0")
    assert [t.type_ref for t in fake.list_types("active")] == [
        "co.acme.LiftPlan@1.0.0",
        "co.acme.SafetyObservation@1.0.0",
    ]
    assert [t.type_ref for t in fake.list_types("deprecated")] == ["co.acme.LiftPlan@0.9.0"]
    detail = fake.get_type("co.acme.LiftPlan@1.0.0")
    assert detail.form is not None and detail.registration.storage_mode == "object-backed"
    with pytest.raises(UnknownTypeError):
        fake.get_type("co.acme.Nope@1.0.0")


def test_an_object_backed_instance_needs_a_valid_body(fake: FakeClient) -> None:
    with pytest.raises(BodyRequiredError):
        fake.create_instance(LIFT, scope=SCOPE, title="t", key="LP-1")
    with pytest.raises(BodyNotAllowedError):
        fake.create_instance(
            LIFT, scope=SCOPE, title="t", key="LP-1", body=LIFT_BODY, psets={"x": {}}
        )
    with pytest.raises(BodyValidationError) as caught:
        fake.create_instance(
            LIFT, scope=SCOPE, title="t", key="LP-1", body={**LIFT_BODY, "risk_class": "enormous"}
        )
    assert caught.value.issues
    result = fake.create_instance(LIFT, scope=SCOPE, title="t", key="LP-1", body=LIFT_BODY)
    assert fake.get_record_body(result.stream_id).body == LIFT_BODY
    record = fake.get_record_by_id(result.stream_id)
    assert record is not None and record["psets"]["co_acme_lift_plan"]["risk_class"] == "medium"


def test_a_managed_instance_takes_psets_and_no_body(fake: FakeClient) -> None:
    with pytest.raises(BodyNotAllowedError):
        fake.create_instance(OBSERVATION, scope=SCOPE, title="t", key="SO-1", body={"a": 1})
    result = fake.create_instance(
        OBSERVATION, scope=SCOPE, title="t", key="SO-1", psets={"co_acme_safety_observation": {}}
    )
    with pytest.raises(BodyNotFoundError):
        fake.get_record_body(result.stream_id)


def test_unknown_and_deprecated_types_take_no_instances(fake: FakeClient) -> None:
    with pytest.raises(UnsupportedRecordTypeError):
        fake.create_instance("co.acme.Nope", scope=SCOPE, title="t", key="N-1")
    gone = FakeClient()
    gone.add_example_type(LIFT, status="deprecated")
    with pytest.raises(UnsupportedRecordTypeError):
        gone.create_instance(LIFT, scope=SCOPE, title="t", key="LP-1", body=LIFT_BODY)


def test_put_body_validates_versions_and_heals(fake: FakeClient) -> None:
    created = fake.create_instance(LIFT, scope=SCOPE, title="t", key="LP-1", body=LIFT_BODY)
    changed = {**LIFT_BODY, "risk_class": "high"}
    stored = fake.put_record_body(created.stream_id, scope=SCOPE, body=changed)
    assert fake.get_record_body(created.stream_id).body == changed
    record = fake.get_record_by_id(created.stream_id)
    assert record is not None and record["psets"]["co_acme_lift_plan"]["risk_class"] == "high"
    with pytest.raises(BodyValidationError):
        fake.put_record_body(created.stream_id, scope=SCOPE, body={"crane": 1})
    with pytest.raises(ConcurrencyError):
        fake.put_record_body(
            created.stream_id, scope=SCOPE, body=changed, expected_version=stored.version + 5
        )
    with pytest.raises(RecordNotFoundError):
        fake.put_record_body("missing", scope=SCOPE, body=changed)
    with pytest.raises(RecordNotFoundError):
        fake.put_record_body(created.stream_id, scope="project:other", body=changed)

    fake.damage(created.stream_id)
    with pytest.raises(BodyHashMismatchError):
        fake.get_record_body(created.stream_id)
    fake.put_record_body(created.stream_id, scope=SCOPE, body=changed)
    assert fake.get_record_body(created.stream_id).body == changed
