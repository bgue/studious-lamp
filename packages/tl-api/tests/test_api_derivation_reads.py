"""The derivation reads over HTTP: schemas, derived documents, jobs, rows, reports, diffs."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from harness import Harness
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_mod_documents.derivation import store
from tl_mod_documents.testing import DocumentsWorld, index_csv

P = "/projects/P123"
ONE = [("47-FV-1001", "Feed", "CV", "4"), ("47-FV-1002", "Return", "HV", "6")]
TWO = [*ONE[:1], ("47-FV-1002", "Return", "HV", "8"), ("47-HV-2001", "Vent", "PSV", "2")]


@pytest.fixture
def world(harness: Harness) -> Iterator[DocumentsWorld]:
    """The documents world over the harness ledger and its file service (the app configured it)."""
    found = DocumentsWorld(harness.db, harness.root / "unused")
    found.store, found.files = harness.store, harness.service
    with use_extractors(make_extractors()):
        found.register("ISD-001", doc_type="IDX")
        found.create_revision("ISD-001")
        found.attach("ISD-001", "A")
        found.register_schema()
        yield found


def test_the_app_configures_the_derivation_file_service(harness: Harness) -> None:
    assert store.configured() is harness.service


def test_the_reads_answer_what_the_pipeline_stored(harness: Harness, world: DocumentsWorld) -> None:
    derived = world.valid_derived(ONE)
    client = harness.client
    schemas = client.get(f"{P}/document-schemas").json()
    assert [s["code"] for s in schemas] == ["instrument-index"] and "json_schema" not in schemas[0]
    one = client.get(f"{P}/document-schemas/instrument-index@1.0.0").json()
    assert one["json_schema"]["required"] == ["tag", "type"]
    assert client.get(f"{P}/document-schemas/nope").json()["error"] == "schema_not_found"

    listed = client.get(f"{P}/derived-documents", params={"state": "Valid"}).json()
    assert [d["key"] for d in listed] == [derived.key]
    by_key = client.get(f"{P}/derived-documents/{derived.key}")  # the key holds `/` and `@`
    assert by_key.status_code == 200, by_key.text
    body = by_key.json()
    assert body["state"] == "Valid" and body["contents"][0]["validation_status"] == "valid"

    rows = client.get(f"{P}/derived-rows/{derived.key}", params={"offset": 1}).json()
    assert rows["total"] == 2 and [r["tag"] for r in rows["rows"]] == ["47-FV-1002"]
    report = client.get(f"{P}/derived-reports/{derived.key}").json()
    assert report["status"] == "valid"
    check = client.get(f"{P}/derived-validations/{derived.key}").json()
    assert check["status"] == "valid"
    preview = client.get(f"{P}/derived-publish-previews/{derived.id}").json()
    assert preview["counts"]["create"] == 2 and preview["can_publish"] is True
    comp = client.get(f"{P}/derived-compensation-previews/{derived.id}").json()
    assert comp["can_compensate"] is False

    jobs = client.get(f"{P}/processing-jobs", params={"derived": derived.key}).json()
    assert [j["state"] for j in jobs] == ["succeeded"]
    assert client.get(f"{P}/processing-jobs/{jobs[0]['id']}").json()["kind"] == "extract"
    assert client.get(f"{P}/processing-jobs/01NOSUCH").json()["error"] == "job_not_found"
    assert (
        client.get(f"{P}/derived-documents/ISD-001@Z/none").json()["error"] == "derived_not_found"
    )


def test_the_diff_route_and_its_refusals(harness: Harness, world: DocumentsWorld) -> None:
    derived = world.valid_derived(ONE)
    client = harness.client
    refused = client.get(f"{P}/derived-diffs/{derived.key}")
    assert refused.status_code == 409 and refused.json()["error"] == "derived_state"
    world.upload_content(derived.id, index_csv(TWO), name="two.csv")
    world.start_extraction(derived_id=derived.id)
    world.run_jobs()
    diff = client.get(f"{P}/derived-diffs/{derived.key}").json()
    assert diff["added"] == ["47-HV-2001"] and diff["changed_count"] == 1
    assert (
        client.get(f"{P}/derived-diffs/{derived.key}", params={"against": "x"}).status_code == 422
    )


def test_an_agent_reads_but_nobody_without_a_token_does(
    harness: Harness, world: DocumentsWorld
) -> None:
    derived = world.valid_derived(ONE)
    assert harness.client_for(None).get(f"{P}/derived-documents").status_code == 401
    from fastapi.testclient import TestClient
    from tl_api.tokens import add_token

    agent = TestClient(harness.app, raise_server_exceptions=False)
    agent.headers.update(
        {"Authorization": f"Bearer {add_token(harness.settings.tokens_path, 'agent:triage')}"}
    )
    assert agent.get(f"{P}/derived-documents/{derived.id}").status_code == 200
    assert agent.get(f"{P}/derived-validations/{derived.id}").status_code == 200
