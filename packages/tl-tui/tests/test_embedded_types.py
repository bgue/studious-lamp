"""EmbeddedClient extension type methods on a real SQLite ledger and object store (P0-I8)."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tl_adapters.objectstore.fs import FsObjectStore
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_core.extypes import registry
from tl_core.extypes.errors import (
    BodyNotAllowedError,
    BodyNotFoundError,
    BodyRequiredError,
    BodyStoreUnavailableError,
    BodyValidationError,
    UnknownTypeError,
)
from tl_core.ledger import ConcurrencyError
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.errors import RecordNotFoundError, ServiceError
from tl_tui.embedded import EmbeddedClient
from tl_tui.errors import describe_error

FIXTURE_TYPES = Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "types"
SCOPE = "project:P1"
LIFT = "co.acme.LiftPlan"
LIFT_REF = "co.acme.LiftPlan@1.0.0"
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
OBSERVATION_VALUES: dict[str, Any] = {
    "observed_on": "2026-10-02",
    "category": "near_miss",
    "severity": "high",
    "location": "Unit 3 pipe rack",
}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[EmbeddedClient]:
    db = tmp_path / "tl.db"
    create_schema(db)
    root = tmp_path / "types"
    shutil.copytree(FIXTURE_TYPES, root)
    with use_provider(DirectorySchemaProvider()):
        built = EmbeddedClient.for_sqlite(
            db, object_store=FsObjectStore(tmp_path / "objects", secret=b"s")
        )
        registry.sync(SqliteUowFactory(db), root, actor="user:ops", source="test")
        yield built


def test_list_and_get_types(client: EmbeddedClient) -> None:
    refs = [t.type_ref for t in client.list_types()]
    assert refs == [LIFT_REF, f"{OBSERVATION}@1.0.0"]
    assert client.list_types("deprecated") == []
    detail = client.get_type(LIFT_REF)
    assert detail.registration.storage_mode == "object-backed"
    assert detail.form is not None and detail.form.groups
    with pytest.raises(UnknownTypeError):
        client.get_type("co.acme.Nope@1.0.0")


def test_a_managed_instance_takes_psets(client: EmbeddedClient) -> None:
    result = client.create_instance(
        OBSERVATION,
        scope=SCOPE,
        title="Spill",
        key="SO-1",
        psets={"co_acme_safety_observation": OBSERVATION_VALUES},
    )
    row = client.get_record_by_id(result.stream_id)
    assert row is not None and row["type"] == OBSERVATION
    with pytest.raises(BodyNotAllowedError):
        client.create_instance(OBSERVATION, scope=SCOPE, title="x", body={"a": 1})


def test_an_object_backed_instance_takes_a_body(client: EmbeddedClient) -> None:
    with pytest.raises(BodyRequiredError):
        client.create_instance(LIFT, scope=SCOPE, title="No body")
    result = client.create_instance(LIFT, scope=SCOPE, title="Lift", key="LP-1", body=LIFT_BODY)
    view = client.get_record_body(result.stream_id)
    assert view.body == LIFT_BODY
    row = client.get_record_by_id(result.stream_id)
    assert row is not None and row["psets"]["co_acme_lift_plan"]["risk_class"] == "medium"


def test_an_invalid_body_lists_its_issues(client: EmbeddedClient) -> None:
    with pytest.raises(BodyValidationError) as caught:
        client.create_instance(
            LIFT, scope=SCOPE, title="Bad", key="LP-9", body={**LIFT_BODY, "risk_class": "enormous"}
        )
    assert caught.value.issues
    assert "risk_class" in describe_error(caught.value)


def test_put_body_creates_a_new_version_and_honours_expected_version(
    client: EmbeddedClient,
) -> None:
    created = client.create_instance(LIFT, scope=SCOPE, title="Lift", key="LP-2", body=LIFT_BODY)
    changed = {**LIFT_BODY, "risk_class": "high"}
    out = client.put_record_body(created.stream_id, scope=SCOPE, body=changed)
    assert client.get_record_body(created.stream_id).body == changed
    assert out.pointer.hash == client.get_record_body(created.stream_id).pointer.hash
    with pytest.raises(ConcurrencyError):
        client.put_record_body(created.stream_id, scope=SCOPE, body=LIFT_BODY, expected_version=1)
    client.put_record_body(
        created.stream_id, scope=SCOPE, body=LIFT_BODY, expected_version=out.version
    )
    with pytest.raises(RecordNotFoundError):
        client.put_record_body("missing", scope=SCOPE, body=LIFT_BODY)


def test_a_record_without_a_body_has_none(client: EmbeddedClient) -> None:
    result = client.create_instance(
        OBSERVATION,
        scope=SCOPE,
        title="Spill",
        key="SO-2",
        psets={"co_acme_safety_observation": OBSERVATION_VALUES},
    )
    with pytest.raises(BodyNotFoundError):
        client.get_record_body(result.stream_id)


def test_the_client_own_writes_are_noted(client: EmbeddedClient) -> None:
    result = client.create_instance(LIFT, scope=SCOPE, title="Lift", key="LP-2", body=LIFT_BODY)
    assert result.events
    assert all(event.event_id in client.own_writes for event in result.events)


def test_without_an_object_store_body_calls_say_so(tmp_path: Path) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    with use_provider(DirectorySchemaProvider()):
        bare = EmbeddedClient(SqliteUowFactory(db))
        with pytest.raises(BodyStoreUnavailableError):
            bare.get_record_body("x")
        with pytest.raises(BodyStoreUnavailableError):
            bare.put_record_body("x", scope=SCOPE, body={})
        with pytest.raises(BodyStoreUnavailableError):
            bare.create_instance(LIFT, scope=SCOPE, title="t", body={})


def test_an_agent_cannot_use_the_embedded_client(tmp_path: Path) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    with pytest.raises(ValueError, match="agent_must_propose"):
        EmbeddedClient(SqliteUowFactory(db), actor="agent:helper")
    with pytest.raises(ValueError, match="agent_must_propose"):
        EmbeddedClient.for_sqlite(db, actor="agent:helper")
    EmbeddedClient(SqliteUowFactory(db), actor="user:ana")  # a person is fine


def test_put_body_in_another_scope_is_not_found(client: EmbeddedClient) -> None:
    created = client.create_instance(LIFT, scope=SCOPE, title="Lift", key="LP-3", body=LIFT_BODY)
    with pytest.raises(RecordNotFoundError):
        client.put_record_body(created.stream_id, scope="project:other", body=LIFT_BODY)
    assert client.get_record_body(created.stream_id).body == LIFT_BODY


def test_a_failing_object_store_is_a_service_error_without_a_path(tmp_path: Path) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    root = tmp_path / "types"
    shutil.copytree(FIXTURE_TYPES, root)
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("a file where the store's root should be", encoding="utf-8")
    with use_provider(DirectorySchemaProvider()):
        broken = EmbeddedClient.for_sqlite(
            db, object_store=FsObjectStore(blocked / "objects", secret=b"s")
        )
        registry.sync(SqliteUowFactory(db), root, actor="user:ops", source="test")
        with pytest.raises(BodyStoreUnavailableError) as caught:
            broken.create_instance(LIFT, scope=SCOPE, title="Lift", key="LP-1", body=LIFT_BODY)
        assert str(blocked) not in str(caught.value) and str(tmp_path) not in str(caught.value)
        assert broken.get_record(SCOPE, "LP-1") is None  # nothing was created
        assert isinstance(caught.value, ServiceError)
