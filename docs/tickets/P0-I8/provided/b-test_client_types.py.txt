"""ApiClient extension type methods against a real app (P0-I8-T23)."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from harness import SCOPE, Harness
from tl_api.client import ApiClient
from tl_api.errors import ApiError
from tl_api.tokens import add_token
from tl_core.extypes import registry
from tl_core.extypes.errors import (
    BodyHashMismatchError,
    BodyNotAllowedError,
    BodyNotFoundError,
    BodyQuarantinedError,
    BodyRequiredError,
    BodyValidationError,
    UnknownTypeError,
)
from tl_core.extypes.lock import write_lock
from tl_core.extypes.service import BodyStoredOut, BodyView, TypeDetail, TypeSummary
from tl_core.ledger import ConcurrencyError
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import CommandResult

TYPES = Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "types"
LIFT = "co.acme.LiftPlan"
OBSERVATION = "co.acme.SafetyObservation"
OBSERVATION_PSET = "co_acme_safety_observation"
LIFT_BODY: dict[str, Any] = {
    "crane": "CR-12",
    "lift_date": "2026-11-03",
    "load_tonnes": 42.5,
    "risk_class": "medium",
}
OBSERVED: dict[str, Any] = {
    "observed_on": "2026-10-02",
    "category": "near_miss",
    "severity": "high",
    "location": "Unit 3 pipe rack",
}


class Env:
    def __init__(self, harness: Harness, root: Path) -> None:
        self.h, self.root = harness, root
        self.api: ApiClient = harness.api()

    def sync(self) -> None:
        registry.sync(self.h.backend, self.root, actor="user:ops", source="test")


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    root = tmp_path / "types"
    shutil.copytree(TYPES, root)
    with use_provider(DirectorySchemaProvider()):
        (tmp_path / "h").mkdir()
        harness = Harness.build(tmp_path / "h")
        try:
            yield Env(harness, root)
        finally:
            harness.close()


def test_list_types_returns_summaries_and_filters_by_status(env: Env) -> None:
    assert env.api.list_types() == []
    (env.root / "co.acme" / "LiftPlan" / "1.0.0" / "examples" / "bad.json").write_text("{}")
    write_lock(env.root / "co.acme" / "LiftPlan" / "1.0.0")
    env.sync()
    rows = env.api.list_types()
    assert all(isinstance(row, TypeSummary) for row in rows)
    assert [(r.type_ref, r.status) for r in rows] == [
        (f"{LIFT}@1.0.0", "quarantined"),
        (f"{OBSERVATION}@1.0.0", "active"),
    ]
    assert [r.type_ref for r in env.api.list_types("active")] == [f"{OBSERVATION}@1.0.0"]
    assert env.api.list_types("deprecated") == []


def test_get_type_returns_the_detail_with_its_form(env: Env) -> None:
    env.sync()
    detail = env.api.get_type(f"{OBSERVATION}@1.0.0")
    assert isinstance(detail, TypeDetail)
    assert detail.registration.storage_mode == "managed" and detail.unavailable is None
    assert detail.form is not None and detail.form.pset == OBSERVATION_PSET
    assert [f.name for f in detail.form.fields()][:2] == ["observed_on", "category"]


def test_get_type_of_an_unknown_ref_raises_the_embedded_error(env: Env) -> None:
    with pytest.raises(UnknownTypeError):
        env.api.get_type("co.acme.Nope@1.0.0")


def test_create_instance_of_a_managed_type(env: Env) -> None:
    env.sync()
    made = env.api.create_instance(
        OBSERVATION,
        scope=SCOPE,
        title="Shackle pin",
        key="SO-1",
        psets={OBSERVATION_PSET: OBSERVED},
    )
    assert isinstance(made, CommandResult) and made.key == "SO-1"
    assert [e.event_type for e in made.events] == ["Record.Created", "Pset.ValuesSet"]
    rows = env.api.list_records(SCOPE, record_type=OBSERVATION)
    assert [r["key"] for r in rows] == ["SO-1"]


def test_create_instance_of_an_object_backed_type_stores_the_body(env: Env) -> None:
    env.sync()
    made = env.api.create_instance(
        LIFT, scope=SCOPE, title="Lift", key="LP-1", description="A lift", body=LIFT_BODY
    )
    assert [e.event_type for e in made.events] == [
        "Record.Created",
        "Record.BodyStored",
        "Pset.ValuesSet",
    ]
    stored = env.api.get_record_body(made.stream_id)
    assert isinstance(stored, BodyView)
    assert stored.record_id == made.stream_id and stored.body == LIFT_BODY
    assert env.api.get_record_by_id(made.stream_id)["description"] == "A lift"


def test_create_instance_errors_raise_the_embedded_classes(env: Env) -> None:
    env.sync()
    with pytest.raises(BodyRequiredError):
        env.api.create_instance(LIFT, scope=SCOPE, title="x", key="K-1")
    with pytest.raises(BodyNotAllowedError):
        env.api.create_instance(OBSERVATION, scope=SCOPE, title="x", key="K-2", body={"a": 1})
    with pytest.raises(BodyValidationError) as caught:
        env.api.create_instance(
            LIFT, scope=SCOPE, title="x", key="K-3", body={**LIFT_BODY, "risk_class": "extreme"}
        )
    assert any("risk_class" in issue for issue in caught.value.issues)


def test_put_record_body_returns_the_pointer_and_version(env: Env) -> None:
    env.sync()
    made = env.api.create_instance(LIFT, scope=SCOPE, title="Lift", key="LP-1", body=LIFT_BODY)
    changed = {**LIFT_BODY, "risk_class": "high"}
    out = env.api.put_record_body(
        made.stream_id, scope=SCOPE, body=changed, expected_version=made.version
    )
    assert isinstance(out, BodyStoredOut) and out.version == made.version + 2
    assert env.api.get_record_body(made.stream_id).body == changed
    with pytest.raises(ConcurrencyError):
        env.api.put_record_body(
            made.stream_id, scope=SCOPE, body=LIFT_BODY, expected_version=made.version
        )


def test_body_errors_raise_the_embedded_classes(env: Env) -> None:
    env.sync()
    plain = env.api.create_instance(
        OBSERVATION, scope=SCOPE, title="x", key="SO-1", psets={OBSERVATION_PSET: OBSERVED}
    )
    with pytest.raises(BodyNotFoundError):
        env.api.get_record_body(plain.stream_id)
    made = env.api.create_instance(LIFT, scope=SCOPE, title="Lift", key="LP-1", body=LIFT_BODY)
    pointer = env.api.get_record_body(made.stream_id).pointer
    env.h.store.path_for(pointer.uri).write_bytes(b'{"crane":"CR-99"}')
    with pytest.raises(BodyHashMismatchError):
        env.api.get_record_body(made.stream_id)
    with pytest.raises(BodyQuarantinedError):
        env.api.get_record_body(made.stream_id)
    env.api.put_record_body(made.stream_id, scope=SCOPE, body=LIFT_BODY)  # heals
    assert env.api.get_record_body(made.stream_id).body == LIFT_BODY


def test_an_agent_token_can_read_but_its_writes_are_refused(env: Env) -> None:
    env.sync()
    made = env.api.create_instance(LIFT, scope=SCOPE, title="Lift", key="LP-1", body=LIFT_BODY)
    token = add_token(env.h.settings.tokens_path, "agent:triage")
    agent = ApiClient("http://testserver", token, http=env.h.client_for(None))
    assert len(agent.list_types()) == 2
    assert agent.get_record_body(made.stream_id).body == LIFT_BODY
    with pytest.raises(ApiError) as caught:
        agent.put_record_body(made.stream_id, scope=SCOPE, body=LIFT_BODY)
    assert caught.value.error == "agent_must_propose"
