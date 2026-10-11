"""Extension types over HTTP: /types, instance creation and the body routes (P0-I8-T21)."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from harness import ALICE, Harness
from tl_api.tokens import add_token
from tl_core.extypes import registry
from tl_core.extypes.lock import write_lock
from tl_core.schema_provider import DirectorySchemaProvider, use_provider

SCOPE = "project:P123"
TYPES = Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "types"
LIFT = "co.acme.LiftPlan"
OBSERVATION = "co.acme.SafetyObservation"
LIFT_PSET = "co_acme_lift_plan"
OBSERVATION_PSET = "co_acme_safety_observation"
LIFT_BODY: dict[str, Any] = {
    "crane": "CR-12",
    "crew": ["A. Okafor"],
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
        self.h = harness
        self.root = root

    def sync(self) -> None:
        registry.sync(self.h.backend, self.root, actor="user:ops", source="test")

    def post(self, path: str, body: dict[str, Any], actor: str = ALICE) -> Any:
        return self.h.client_for(actor).post(path, json=body)

    def object_file(self, body_response: dict[str, Any]) -> Path:
        return self.h.store.path_for(body_response["pointer"]["uri"])


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


def create_lift(env: Env, key: str = "LP-1", body: dict[str, Any] | None = None) -> dict[str, Any]:
    response = env.post(
        f"/types/{LIFT}/records",
        {"scope": SCOPE, "title": "Lift", "key": key, "body": body or LIFT_BODY},
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- the registry ------------------------------------------------------------------------------


def test_types_is_empty_until_something_is_registered(env: Env) -> None:
    response = env.h.client.get("/types")
    assert response.status_code == 200 and response.json() == []


def test_types_lists_the_registered_versions(env: Env) -> None:
    env.sync()
    rows = env.h.client.get("/types").json()
    assert [r["type_ref"] for r in rows] == [f"{LIFT}@1.0.0", f"{OBSERVATION}@1.0.0"]
    lift = rows[0]
    assert (
        lift["type_name"] == LIFT and lift["namespace"] == "co.acme" and lift["name"] == "LiftPlan"
    )
    assert lift["status"] == "active" and lift["storage_mode"] == "object-backed"
    assert lift["index_fields"] == ["lift_date", "crane", "load_tonnes", "risk_class"]
    assert lift["owner"] == "user:ops" and lift["seq"] >= 1
    assert len(lift["schema_hash"]) == 64 and len(lift["content_hash"]) == 64


def test_types_filters_by_status_and_refuses_an_unknown_one(env: Env) -> None:
    (env.root / "co.acme" / "LiftPlan" / "1.0.0" / "examples" / "bad.json").write_text("{}")
    write_lock(env.root / "co.acme" / "LiftPlan" / "1.0.0")
    env.sync()
    active = env.h.client.get("/types", params={"status": "active"}).json()
    assert [r["type_ref"] for r in active] == [f"{OBSERVATION}@1.0.0"]
    quarantined = env.h.client.get("/types", params={"status": "quarantined"}).json()
    assert [r["type_ref"] for r in quarantined] == [f"{LIFT}@1.0.0"]
    assert env.h.client.get("/types", params={"status": "bogus"}).status_code == 422


def test_get_type_returns_the_form(env: Env) -> None:
    env.sync()
    response = env.h.client.get(f"/types/{LIFT}@1.0.0")
    assert response.status_code == 200
    detail = response.json()
    assert detail["registration"]["type_ref"] == f"{LIFT}@1.0.0"
    assert detail["report"] == [] and detail["unavailable"] is None
    form = detail["form"]
    assert form["pset"] == LIFT_PSET and form["storage_mode"] == "object-backed"
    assert [g["name"] for g in form["groups"]] == ["plan", "method"]
    assert form["grid_columns"] == ["lift_date", "crane", "load_tonnes", "risk_class"]
    paths = {f["name"]: f["path"] for g in form["groups"] for f in g["fields"]}
    assert paths["crane"] == f"psets.{LIFT_PSET}.crane" and paths["crew"] == "body.crew"


def test_get_type_of_a_quarantined_version_has_the_report_and_no_form(env: Env) -> None:
    (env.root / "co.acme" / "LiftPlan" / "1.0.0" / "examples" / "bad.json").write_text("{}")
    write_lock(env.root / "co.acme" / "LiftPlan" / "1.0.0")
    env.sync()
    detail = env.h.client.get(f"/types/{LIFT}@1.0.0").json()
    assert detail["registration"]["status"] == "quarantined" and detail["form"] is None
    assert {i["kind"] for i in detail["report"]} == {"example"}


def test_get_type_unknown_is_404(env: Env) -> None:
    response = env.h.client.get("/types/co.acme.Nope@1.0.0")
    assert response.status_code == 404 and response.json()["error"] == "type_not_found"


def test_types_need_a_token(env: Env) -> None:
    assert env.h.client_for(None).get("/types").status_code == 401


# --- instances ---------------------------------------------------------------------------------


def test_a_managed_instance_is_created_with_its_psets(env: Env) -> None:
    env.sync()
    response = env.post(
        f"/types/{OBSERVATION}/records",
        {
            "scope": SCOPE,
            "title": "Shackle pin",
            "key": "SO-1",
            "psets": {OBSERVATION_PSET: OBSERVED},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert [e["event_type"] for e in result["events"]] == ["Record.Created", "Pset.ValuesSet"]
    assert result["key"] == "SO-1" and result["events"][0]["actor"] == ALICE
    assert result["events"][0]["source"] == "api"
    rows = env.h.client.get("/records", params={"scope": SCOPE, "record_type": OBSERVATION}).json()
    assert [r["key"] for r in rows] == ["SO-1"]
    filtered = env.h.client.get(
        "/records", params={"scope": SCOPE, "q": f"psets.{OBSERVATION_PSET}.severity:high"}
    ).json()
    assert [r["key"] for r in filtered] == ["SO-1"]


def test_an_object_backed_instance_is_created_with_its_body(env: Env) -> None:
    env.sync()
    result = create_lift(env)
    assert [e["event_type"] for e in result["events"]] == [
        "Record.Created",
        "Record.BodyStored",
        "Pset.ValuesSet",
    ]
    rows = env.h.client.get(
        "/records", params={"scope": SCOPE, "q": f"psets.{LIFT_PSET}.risk_class:medium"}
    ).json()
    assert [r["key"] for r in rows] == ["LP-1"]


def test_creating_with_the_wrong_kind_of_content_is_refused(env: Env) -> None:
    env.sync()
    base = {"scope": SCOPE, "title": "x", "key": "K-1"}
    missing = env.post(f"/types/{LIFT}/records", base)
    assert missing.status_code == 422 and missing.json()["error"] == "body_required"
    managed = env.post(f"/types/{OBSERVATION}/records", {**base, "body": {"a": 1}})
    assert managed.status_code == 422 and managed.json()["error"] == "body_not_allowed"
    both = env.post(f"/types/{LIFT}/records", {**base, "body": LIFT_BODY, "psets": {LIFT_PSET: {}}})
    assert both.status_code == 422 and both.json()["error"] == "body_not_allowed"
    unknown = env.post("/types/co.acme.Nope/records", {**base, "psets": {}})
    assert unknown.status_code == 422 and unknown.json()["error"] == "unsupported_record_type"


def test_an_invalid_body_is_a_422_that_lists_the_problems(env: Env) -> None:
    env.sync()
    response = env.post(
        f"/types/{LIFT}/records",
        {
            "scope": SCOPE,
            "title": "x",
            "key": "K-1",
            "body": {**LIFT_BODY, "risk_class": "extreme"},
        },
    )
    assert response.status_code == 422
    error = response.json()
    assert error["error"] == "body_invalid"
    assert any("risk_class" in issue for issue in error["issues"])
    assert env.h.client.get("/records", params={"scope": SCOPE}).json() == []


def test_an_unknown_field_in_the_request_is_a_validation_error(env: Env) -> None:
    env.sync()
    response = env.post(
        f"/types/{LIFT}/records", {"scope": SCOPE, "title": "x", "actor": "user:eve"}
    )
    assert response.status_code == 422 and response.json()["error"] == "validation_error"


# --- bodies --------------------------------------------------------------------------------------


def test_get_body_returns_the_verified_body_and_its_pointer(env: Env) -> None:
    env.sync()
    record_id = create_lift(env)["stream_id"]
    response = env.h.client.get(f"/records/{record_id}/body")
    assert response.status_code == 200
    out = response.json()
    assert out["record_id"] == record_id and out["body"] == LIFT_BODY
    assert out["pointer"]["uri"].startswith(f"records/{LIFT}/{record_id}/")
    assert out["pointer"]["uri"].endswith(".json") and len(out["pointer"]["hash"]) == 64


def test_get_body_of_a_record_without_one_is_404(env: Env) -> None:
    env.sync()
    managed = env.post(
        f"/types/{OBSERVATION}/records",
        {"scope": SCOPE, "title": "x", "key": "SO-1", "psets": {OBSERVATION_PSET: OBSERVED}},
    ).json()
    response = env.h.client.get(f"/records/{managed['stream_id']}/body")
    assert response.status_code == 404 and response.json()["error"] == "body_not_found"


def test_put_body_stores_a_new_version_and_returns_the_etag(env: Env) -> None:
    env.sync()
    made = create_lift(env)
    record_id = made["stream_id"]
    changed = {**LIFT_BODY, "risk_class": "high", "load_tonnes": 99}
    response = env.h.client.put(
        f"/records/{record_id}/body",
        json={"scope": SCOPE, "body": changed, "expected_version": made["version"]},
    )
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["version"] == made["version"] + 2  # BodyStored, then the index values
    assert response.headers["etag"] == f'"{out["version"]}"'
    assert env.h.client.get(f"/records/{record_id}/body").json()["body"] == changed
    rows = env.h.client.get(
        "/records", params={"scope": SCOPE, "q": f"psets.{LIFT_PSET}.risk_class:high"}
    ).json()
    assert [r["key"] for r in rows] == ["LP-1"]


def test_put_body_with_a_stale_version_is_409(env: Env) -> None:
    env.sync()
    made = create_lift(env)
    first = env.h.client.put(
        f"/records/{made['stream_id']}/body",
        json={"scope": SCOPE, "body": {**LIFT_BODY, "load_tonnes": 50}},
    )
    assert first.status_code == 200
    stale = env.h.client.put(
        f"/records/{made['stream_id']}/body",
        json={
            "scope": SCOPE,
            "body": {**LIFT_BODY, "load_tonnes": 60},
            "expected_version": made["version"],
        },
    )
    assert stale.status_code == 409 and stale.json()["error"] == "concurrency_conflict"


def test_put_body_refuses_a_bad_body_a_wrong_scope_and_an_unknown_record(env: Env) -> None:
    env.sync()
    record_id = create_lift(env)["stream_id"]
    bad = env.h.client.put(
        f"/records/{record_id}/body", json={"scope": SCOPE, "body": {"crane": "CR-1"}}
    )
    assert bad.status_code == 422 and bad.json()["error"] == "body_invalid"
    elsewhere = env.h.client.put(
        f"/records/{record_id}/body", json={"scope": "project:P9", "body": LIFT_BODY}
    )
    assert elsewhere.status_code == 404 and elsewhere.json()["error"] == "record_not_found"
    unknown = env.h.client.put(
        "/records/01J9Z6Q4W3X2Y1V0T9S8R7Q6P5/body", json={"scope": SCOPE, "body": LIFT_BODY}
    )
    assert unknown.status_code == 404


def test_a_damaged_object_is_a_502_then_quarantined_then_healed_by_storing_it_again(
    env: Env,
) -> None:
    env.sync()
    record_id = create_lift(env)["stream_id"]
    good = env.h.client.get(f"/records/{record_id}/body").json()
    env.object_file(good).write_bytes(b'{"crane":"CR-99"}')
    first = env.h.client.get(f"/records/{record_id}/body")
    assert first.status_code == 502 and first.json()["error"] == "body_hash_mismatch"
    second = env.h.client.get(f"/records/{record_id}/body")
    assert second.status_code == 403 and second.json()["error"] == "body_quarantined"
    healed = env.h.client.put(
        f"/records/{record_id}/body", json={"scope": SCOPE, "body": LIFT_BODY}
    )
    assert healed.status_code == 200
    assert env.h.client.get(f"/records/{record_id}/body").json()["body"] == LIFT_BODY


def test_the_body_routes_answer_503_without_an_object_store(env: Env) -> None:
    env.sync()
    record_id = create_lift(env)["stream_id"]
    env.h.app.state.ctx.objects = None
    assert env.h.client.get(f"/records/{record_id}/body").status_code == 503
    put = env.h.client.put(f"/records/{record_id}/body", json={"scope": SCOPE, "body": LIFT_BODY})
    assert put.status_code == 503 and put.json()["error"] == "unavailable"
    made = env.post(
        f"/types/{LIFT}/records", {"scope": SCOPE, "title": "x", "key": "K-2", "body": LIFT_BODY}
    )
    assert made.status_code == 503


# --- agents propose ---------------------------------------------------------------------------


def test_an_agent_token_can_read_but_not_write(env: Env) -> None:
    env.sync()
    record_id = create_lift(env)["stream_id"]
    token = add_token(env.h.settings.tokens_path, "agent:triage")
    agent = env.h.client_for(None)
    agent.headers.update({"Authorization": f"Bearer {token}"})
    assert agent.get("/types").status_code == 200
    assert agent.get(f"/records/{record_id}/body").status_code == 200
    created = agent.post(
        f"/types/{OBSERVATION}/records", json={"scope": SCOPE, "title": "x", "key": "SO-9"}
    )
    assert created.status_code == 403 and created.json()["error"] == "agent_must_propose"
    put = agent.put(f"/records/{record_id}/body", json={"scope": SCOPE, "body": LIFT_BODY})
    assert put.status_code == 403 and put.json()["error"] == "agent_must_propose"
